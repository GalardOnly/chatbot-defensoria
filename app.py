from flask import Flask, request, jsonify, send_from_directory
import threading
import requests
from flask_cors import CORS
from conteudo_chat import (
    responder_pergunta,
    resposta_contingencia,
    criar_chat_groq,
    EmbeddingService,
    buscar_chunks_relevantes,
    ClassificadorViolencia,
    garantir_base_conhecimento,
)
import chromadb
import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ── BANCO DE DADOS ───────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect("historico.db")
    c    = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS historico (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT    NOT NULL,
            role            TEXT    NOT NULL,
            mensagem        TEXT    NOT NULL,
            timestamp       TEXT    NOT NULL,
            tipo_violencia  TEXT,
            gravidade       TEXT
        )
    """)
    for coluna, tipo in [("tipo_violencia", "TEXT"), ("gravidade", "TEXT")]:
        try:
            c.execute(f"ALTER TABLE historico ADD COLUMN {coluna} {tipo}")
        except sqlite3.OperationalError:
            pass
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


# ── DETECÇÃO DE MODO ─────────────────────────────────────────────────────────
def detectar_modo_local(mensagem):
    texto = (mensagem or "").lower()
    if texto.strip() in {"oi", "ola", "olá", "bom dia", "boa tarde", "boa noite"}:
        return "fachada"

    termos_reais = [
        "ajuda", "socorro", "agred", "violenc", "ameac", "medo", "abuso",
        "bater", "espanc", "marido", "namorado", "companheiro", "agressor",
        "protetiva", "delegacia", "denuncia", "machuc", "feriu", "risco",
    ]
    termos_fachada = [
        "receita", "bolo", "cozinha", "decoracao", "limpeza", "faxina",
        "casa", "lar", "organizacao", "mofo", "encanamento", "jardim",
    ]

    if any(termo in texto for termo in termos_reais):
        return "real"
    if any(termo in texto for termo in termos_fachada):
        return "fachada"
    return "real"


def detectar_modo(mensagem, historico=None):
    historico = historico or []
    modo_local = detectar_modo_local(mensagem)
    if modo_local == "real":
        return "real"

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        return "real" if any(
            m.get("tipo_violencia") and m["tipo_violencia"] != "nao_violencia"
            for m in historico if m["role"] == "user"
        ) else modo_local

    contexto    = "\n".join([f"{m['role']}: {m['mensagem']}" for m in historico[-4:]])
    prompt = f"""Analise a mensagem abaixo e responda apenas com uma palavra: REAL ou FACHADA.

REAL = a pessoa pode estar em situação de violência doméstica, risco, medo, controle, abuso ou precisando de ajuda urgente. Em caso de dúvida, classifique como REAL.
FACHADA = apenas perguntas claramente sobre casa, culinária, decoração ou limpeza, sem nenhuma ambiguidade.

Histórico recente:
{contexto}

Mensagem atual: {mensagem}

Responda apenas: REAL ou FACHADA"""

    try:
        resultado = criar_chat_groq(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            max_tokens=10,
            temperature=0,
        )
        resultado = resultado.strip().upper()
        return "real" if "REAL" in resultado else "fachada"
    except Exception as e:
        print(f"[detectar_modo] Aviso: {e}")
        return modo_local


# ── FLASK APP ────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

init_db()

chroma_client = chromadb.PersistentClient(path="chroma_db")
colecao       = chroma_client.get_or_create_collection("documentos_juridicos")

embedding_service = None
classificador     = None
_init_lock        = threading.Lock()
_servicos_prontos = False
_ultimo_erro_chat = None


def _carregar_servicos_background():
    """
    Carrega EmbeddingService + ClassificadorViolencia em thread separada.
    O servidor Flask sobe ANTES disso terminar — Render detecta a porta sem timeout.
    """
    global embedding_service, classificador, _servicos_prontos

    with _init_lock:
        if _servicos_prontos:
            return

        print("[boot] Carregando EmbeddingService...")
        try:
            embedding_service = EmbeddingService()
            print("[boot] EmbeddingService pronto.")
            try:
                garantir_base_conhecimento(embedding_service, colecao)
            except Exception as e:
                print(f"[boot] ERRO ao popular base de conhecimento: {e}")
        except Exception as e:
            print(f"[boot] ERRO EmbeddingService: {e}")

        if (
            os.path.exists("modelos/rf_tipo.pkl")
            and os.path.exists("modelos/rf_gravidade.pkl")
        ):
            print("[boot] Carregando ClassificadorViolencia (BERT + RF)...")
            try:
                classificador = ClassificadorViolencia(
                    pasta_modelos="modelos",
                    classe_neutra="nao_violencia",
                    limiar_confianca=0.60,
                )
                print("[boot] ClassificadorViolencia pronto.")
            except Exception as e:
                print(f"[boot] ERRO ClassificadorViolencia: {e}")
        else:
            print("[boot] Modelos RF nao encontrados — pre-classificacao desativada.")

        _servicos_prontos = True
        print("[boot] Todos os servicos prontos.")


def garantir_servicos():
    """Aguarda até 60s para os serviços ficarem prontos."""
    if not _servicos_prontos:
        for _ in range(120):
            if _servicos_prontos:
                break
            threading.Event().wait(0.5)


# ── ENDPOINTS ────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/painel", methods=["GET"])
def painel():
    return send_from_directory(BASE_DIR, "painel.html")


@app.route("/chat", methods=["POST"])
def chat():
    global _ultimo_erro_chat
    data = request.get_json(silent=True) or {}
    mensagem   = data.get("mensagem", "")
    session_id = data.get("session_id", "")

    if not mensagem:
        return jsonify({"erro": "Campo mensagem obrigatorio."}), 400

    salvar_mensagem(session_id, "user", mensagem)
    historico_sessao = carregar_historico(session_id)

    garantir_servicos()

    # ── Pré-classificação ─────────────────────────────────────────────────────
    classificacao = None
    if classificador:
        try:
            classificacao = classificador.classificar(mensagem)
            conn = sqlite3.connect("historico.db")
            c    = conn.cursor()
            c.execute(
                """UPDATE historico SET tipo_violencia = ?, gravidade = ?
                   WHERE session_id = ? AND role = 'user'
                   AND id = (SELECT MAX(id) FROM historico
                             WHERE session_id = ? AND role = 'user')""",
                (classificacao["tipo"], classificacao["gravidade"], session_id, session_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Classificador] Aviso: {e}")

    # ── Detecção de modo ──────────────────────────────────────────────────────
    teve_real_no_historico = any(
        m.get("tipo_violencia") and m["tipo_violencia"] != "nao_violencia"
        for m in historico_sessao if m["role"] == "user"
    )
    classificacao_indica_real = classificacao is not None and classificacao["eh_violencia"]
    try:
        modo_llm = detectar_modo(mensagem, historico=historico_sessao)
    except Exception as e:
        print(f"[chat] Aviso ao detectar modo: {e}")
        modo_llm = "real" if (teve_real_no_historico or classificacao_indica_real) else "fachada"
    modo_final = (
        "real"
        if (teve_real_no_historico or classificacao_indica_real or modo_llm == "real")
        else "fachada"
    )

    # ── Resposta da LLM ───────────────────────────────────────────────────────
    historico_api = [
        {"role": m["role"], "content": m["mensagem"]} for m in historico_sessao
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
        _ultimo_erro_chat = None
    except Exception as e:
        print(f"[chat] ERRO: {e}")
        _ultimo_erro_chat = str(e)
        resposta = resposta_contingencia(
            pergunta=mensagem,
            modo=modo_final,
            classificacao=classificacao,
        )

    salvar_mensagem(session_id, "assistant", resposta)

    return jsonify({
        "resposta":      resposta,
        "modo":          modo_final,
        "classificacao": classificacao,
    })


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
        teve_violencia = any(
            m.get("tipo_violencia") and m["tipo_violencia"] != "nao_violencia"
            for m in hist if m["role"] == "user"
        )
        tipos_detectados = list({
            m["tipo_violencia"] for m in hist
            if m["role"] == "user"
            and m.get("tipo_violencia")
            and m["tipo_violencia"] != "nao_violencia"
        })
        resumo[sid] = {
            "total_msgs":       row[1],
            "modo_detectado":   "real" if teve_violencia else "fachada",
            "nome":             identificacoes.get(sid),
            "tipos_detectados": tipos_detectados,
        }
    return jsonify({"sessoes": resumo})


@app.route("/historico/<session_id>", methods=["GET"])
def historico(session_id):
    return jsonify({"session_id": session_id, "historico": carregar_historico(session_id)})


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
            session_id TEXT PRIMARY KEY, nome TEXT,
            consentimento INTEGER DEFAULT 1, timestamp TEXT
        )
    """)
    c.execute(
        "INSERT OR REPLACE INTO identificacao VALUES (?, ?, 1, ?)",
        (session_id, nome, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/apagar/<session_id>", methods=["DELETE"])
def apagar(session_id):
    conn = sqlite3.connect("historico.db")
    c    = conn.cursor()
    c.execute("DELETE FROM historico     WHERE session_id = ?", (session_id,))
    c.execute("DELETE FROM identificacao WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "apagado"})


@app.route("/health", methods=["GET"])
def health():
    try:
        colecao_count = colecao.count()
    except Exception:
        colecao_count = None

    return jsonify({
        "status":              "ok",
        "servicos_prontos":    _servicos_prontos,
        "classificador_ativo": classificador is not None,
        "embedding_ativo":     embedding_service is not None,
        "groq_configurado":    bool(os.getenv("GROQ_API_KEY")),
        "gemini_configurado":  bool(os.getenv("GEMINI_API_KEY")),
        "colecao_count":       colecao_count,
        "ultimo_erro_chat":    _ultimo_erro_chat,
    })


# ── KEEP-ALIVE ───────────────────────────────────────────────────────────────
def ping_health():
    try:
        url = os.getenv("RENDER_EXTERNAL_URL")
        if url:
            requests.get(f"{url}/health", timeout=5)
            print(f"[ping] {url}/health")
    except Exception as e:
        print(f"[ping] Falhou: {e}")
    threading.Timer(600, ping_health).start()


# ── BOOT — serviços pesados em background, servidor sobe imediatamente ────────
threading.Thread(target=_carregar_servicos_background, daemon=True).start()
ping_health()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
