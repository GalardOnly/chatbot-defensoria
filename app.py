from flask import Flask, request, jsonify
import threading
import requests
from flask_cors import CORS
from conteudo_chat import (
    responder_pergunta,
    EmbeddingService,
    buscar_chunks_relevantes,
    ClassificadorViolencia,       # ← pré-classificador
)
import chromadb
import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


#BANCO DE DADOS
# Ponto de atenção 5: colunas tipo_violencia e gravidade adicionadas ao historico

def init_db():
    conn = sqlite3.connect("historico.db")
    c    = conn.cursor()

    # Tabela principal — inclui as duas colunas da pré-classificação
    c.execute("""
        CREATE TABLE IF NOT EXISTS historico (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT    NOT NULL,
            role            TEXT    NOT NULL,
            mensagem        TEXT    NOT NULL,
            timestamp       TEXT    NOT NULL,
            tipo_violencia  TEXT,        -- preenchido nas mensagens do usuário
            gravidade       TEXT         -- preenchido nas mensagens do usuário
        )
    """)

    # Migração segura: adiciona colunas se o banco já existia sem elas
    for coluna, tipo in [("tipo_violencia", "TEXT"), ("gravidade", "TEXT")]:
        try:
            c.execute(f"ALTER TABLE historico ADD COLUMN {coluna} {tipo}")
        except sqlite3.OperationalError:
            pass  # coluna já existe — tudo certo

    conn.commit()
    conn.close()


def salvar_mensagem(session_id, role, mensagem, tipo_violencia=None, gravidade=None):
    conn      = sqlite3.connect("historico.db")
    c         = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute(
        """INSERT INTO historico
           (session_id, role, mensagem, timestamp, tipo_violencia, gravidade)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (session_id, role, mensagem, timestamp, tipo_violencia, gravidade),
    )
    conn.commit()
    conn.close()


def carregar_historico(session_id):
    conn = sqlite3.connect("historico.db")
    c    = conn.cursor()
    c.execute(
        """SELECT role, mensagem, timestamp, tipo_violencia, gravidade
           FROM historico WHERE session_id = ? ORDER BY id ASC""",
        (session_id,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "role":           row[0],
            "mensagem":       row[1],
            "timestamp":      row[2],
            "tipo_violencia": row[3],
            "gravidade":      row[4],
        }
        for row in rows
    ]


#DETECÇÃO DE MODO (LLM) 
def detectar_modo(mensagem, historico=[]):
    from groq import Groq

    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    contexto    = "\n".join([f"{m['role']}: {m['mensagem']}" for m in historico[-4:]])

    prompt = f"""Analise a mensagem abaixo e responda apenas com uma palavra: REAL ou FACHADA.

REAL = a pessoa pode estar em situação de violência doméstica, risco, medo, controle, abuso ou precisando de ajuda urgente. Em caso de dúvida, classifique como REAL — é melhor oferecer ajuda a quem não precisa do que ignorar quem precisa.
FACHADA = apenas perguntas claramente sobre casa, culinária, decoração ou limpeza, sem nenhuma ambiguidade.

Histórico recente:
{contexto}

Mensagem atual: {mensagem}

Responda apenas: REAL ou FACHADA"""

    response  = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10,
    )
    resultado = response.choices[0].message.content.strip().upper()
    return "real" if "REAL" in resultado else "fachada"


# FLASK APP
app = Flask(__name__)
CORS(app)

chroma_client    = chromadb.PersistentClient(path="chroma_db")
colecao          = chroma_client.get_or_create_collection("documentos_juridicos")
embedding_service = None
classificador    = None   # instância única do ClassificadorViolencia


#Ponto de atenção 1: BERT carregado no boot, antes do app.run 
def init_services():
    global embedding_service, classificador

    if embedding_service is None:
        embedding_service = EmbeddingService()

    # Ponto de atenção 1: carrega o classificador se os modelos existirem,
    # evitando crash em ambientes onde o treino ainda não foi executado.
    if classificador is None:
        if os.path.exists("modelos/rf_tipo.pkl") and os.path.exists("modelos/rf_gravidade.pkl"):
            print("[init_services] Carregando ClassificadorViolencia...")
            classificador = ClassificadorViolencia(
                pasta_modelos="modelos",
                # Ponto de atenção 3: ajuste 'classe_neutra' se usou outro nome no dataset
                classe_neutra="nao_violencia",
                # Ponto de atenção 2: limiar de confiança — conservador por padrão
                limiar_confianca=0.60,
            )
            print("[init_services] ClassificadorViolencia pronto.")
        else:
            print("[init_services] ⚠️  Modelos RF não encontrados — pré-classificação desativada.")


# ENDPOINT /chat 
@app.route("/chat", methods=["POST"])
def chat():
    data       = request.get_json()
    mensagem   = data.get("mensagem", "")
    session_id = data.get("session_id", "")

    if not mensagem:
        return jsonify({"erro": "Campo mensagem obrigatorio."}), 400

    # 1. Salva mensagem do usuário (sem classificação ainda)
    salvar_mensagem(session_id, "user", mensagem)

    # 2. Carrega histórico completo
    historico_sessao = carregar_historico(session_id)

    # 3. Garante que os serviços estão prontos
    init_services()

    # Pré-classificação 
    classificacao = None
    if classificador:
        try:
            classificacao = classificador.classificar(mensagem)

            # Atualiza a linha recém-inserida com tipo e gravidade
            conn = sqlite3.connect("historico.db")
            c    = conn.cursor()
            c.execute(
                """UPDATE historico
                   SET tipo_violencia = ?, gravidade = ?
                   WHERE session_id = ? AND role = 'user'
                   AND id = (SELECT MAX(id) FROM historico WHERE session_id = ? AND role = 'user')""",
                (
                    classificacao["tipo"],
                    classificacao["gravidade"],
                    session_id,
                    session_id,
                ),
            )
            conn.commit()
            conn.close()

        except Exception as e:
            print(f"[Classificador] Aviso: falhou — {e}")

    # Detecção de modo (LLM + classificador como reforço)
    # Ponto de atenção 2: limiar 0.60 definido no ClassificadorViolencia.
    # Aqui verificamos se alguma mensagem anterior já foi classificada como real
    # (evita recalcular detectar_modo para cada msg do histórico — custo em tokens).
    teve_real_no_historico = any(
        m.get("tipo_violencia") and m["tipo_violencia"] != "nao_violencia"
        for m in historico_sessao
        if m["role"] == "user"
    )

    classificacao_indica_real = (
        classificacao is not None
        and classificacao["eh_violencia"]
    )

    modo_llm    = detectar_modo(mensagem, historico=historico_sessao)
    modo_final  = (
        "real"
        if (teve_real_no_historico or classificacao_indica_real or modo_llm == "real")
        else "fachada"
    )

    #Resposta da LLM 
    historico_api = [
        {"role": m["role"], "content": m["mensagem"]}
        for m in historico_sessao
    ]

    try:
        resposta = responder_pergunta(
            pergunta=mensagem,
            embedding_service=embedding_service,
            colecao=colecao,
            historico=historico_api,
            modo=modo_final,
            classificacao=classificacao,
        )
    except Exception as e:
        print(f"[chat] ERRO CRÍTICO NA RESPOSTA: {e}")
        resposta = "Serviço temporariamente indisponível. Tente novamente."

    #Salva resposta da Bruna 
    salvar_mensagem(session_id, "assistant", resposta)

    return jsonify({
        "resposta":      resposta,
        "modo":          modo_final,
        "classificacao": classificacao,   # útil para debug / dashboard
    })


#DEMAIS ENDPOINTS
@app.route("/sessoes", methods=["GET"])
def sessoes():
    conn = sqlite3.connect("historico.db")
    c    = conn.cursor()
    c.execute("SELECT session_id, COUNT(*) as total FROM historico GROUP BY session_id")
    rows = c.fetchall()

    identificacoes = {}
    try:
        c.execute("SELECT session_id, nome FROM identificacao")
        for row in c.fetchall():
            identificacoes[row[0]] = row[1]
    except Exception:
        pass
    conn.close()

    resumo = {}
    for row in rows:
        sid  = row[0]
        hist = carregar_historico(sid)

        # Usa tipo_violencia salvo no banco — sem precisar chamar LLM aqui
        teve_violencia = any(
            m.get("tipo_violencia") and m["tipo_violencia"] != "nao_violencia"
            for m in hist
            if m["role"] == "user"
        )
        modo_detectado = "real" if teve_violencia else "fachada"

        # Tipos detectados na sessão (para dashboard)
        tipos_detectados = list({
            m["tipo_violencia"]
            for m in hist
            if m["role"] == "user" and m.get("tipo_violencia")
            and m["tipo_violencia"] != "nao_violencia"
        })

        resumo[sid] = {
            "total_msgs":      row[1],
            "modo_detectado":  modo_detectado,
            "nome":            identificacoes.get(sid),
            "tipos_detectados": tipos_detectados,
        }

    return jsonify({"sessoes": resumo})


@app.route("/historico/<session_id>", methods=["GET"])
def historico(session_id):
    hist = carregar_historico(session_id)
    return jsonify({"session_id": session_id, "historico": hist})


@app.route("/identificar", methods=["POST"])
def identificar():
    data       = request.get_json()
    session_id = data.get("session_id", "")
    nome       = data.get("nome", "")
    if not session_id or not nome:
        return jsonify({"erro": "Dados incompletos."}), 400

    conn = sqlite3.connect("historico.db")
    c    = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS identificacao (
            session_id  TEXT PRIMARY KEY,
            nome        TEXT,
            consentimento INTEGER DEFAULT 1,
            timestamp   TEXT
        )
    """)
    c.execute(
        "INSERT OR REPLACE INTO identificacao (session_id, nome, consentimento, timestamp) VALUES (?, ?, 1, ?)",
        (session_id, nome, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/apagar/<session_id>", methods=["DELETE"])
def apagar(session_id):
    conn = sqlite3.connect("historico.db")
    c    = conn.cursor()
    c.execute("DELETE FROM historico       WHERE session_id = ?", (session_id,))
    c.execute("DELETE FROM identificacao   WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "apagado"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":               "ok",
        "classificador_ativo":  classificador is not None,
    })


# KEEP-ALIVE (Render)
def ping_health():
    try:
        url = os.getenv("RENDER_EXTERNAL_URL")
        if url:
            requests.get(f"{url}/health", timeout=5)
            print(f"[ping] {url}/health")
    except Exception as e:
        print(f"[ping] Falhou: {e}")
    threading.Timer(600, ping_health).start()


# BOOT 
if __name__ == "__main__":
    # 1. Banco de dados (com migração segura das novas colunas)
    init_db()

    # Ponto de atenção 1: carrega BERT + RF ANTES do app.run
    # Evita timeout na primeira requisição (cold-start do Render)
    print("[boot] Inicializando serviços...")
    init_services()
    print("[boot] Serviços prontos.")

    # 2. Keep-alive
    ping_health()

    # 3. Servidor
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)