
from flask import Flask, request, jsonify
from flask_cors import CORS
from conteudo_chat import responder_pergunta, EmbeddingService, buscar_chunks_relevantes
import chromadb
import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
def init_db():
    conn = sqlite3.connect('historico.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            mensagem TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def salvar_mensagem(session_id, role, mensagem):
    conn = sqlite3.connect('historico.db')
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute('INSERT INTO historico (session_id, role, mensagem, timestamp) VALUES (?, ?, ?, ?)',
              (session_id, role, mensagem, timestamp))
    conn.commit()
    conn.close()

def carregar_historico(session_id):
    conn = sqlite3.connect('historico.db')
    c = conn.cursor()
    c.execute('SELECT role, mensagem, timestamp FROM historico WHERE session_id = ? ORDER BY id ASC', (session_id,))
    rows = c.fetchall()
    conn.close()
    return [{'role': row[0], 'mensagem': row[1], 'timestamp': row[2]} for row in rows]

def detectar_modo(mensagem, historico=[]):
    from groq import Groq
    import os
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    contexto = "\n".join([f"{m['role']}: {m['mensagem']}" for m in historico[-4:]])
    
    prompt = f"""Analise a mensagem abaixo e responda apenas com uma palavra: REAL ou FACHADA.

REAL = a pessoa pode estar em situação de violência doméstica, risco, medo, controle, abuso ou precisando de ajuda urgente. Em caso de dúvida, classifique como REAL — é melhor oferecer ajuda a quem não precisa do que ignorar quem precisa.
FACHADA = apenas perguntas claramente sobre casa, culinária, decoração ou limpeza, sem nenhuma ambiguidade.

Histórico recente:
{contexto}

Mensagem atual: {mensagem}

Responda apenas: REAL ou FACHADA"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10
    )
    resultado = response.choices[0].message.content.strip().upper()
    return 'real' if 'REAL' in resultado else 'fachada'


app = Flask(__name__)
CORS(app)

chroma_client = chromadb.PersistentClient(path='chroma_db')
colecao = chroma_client.get_or_create_collection('documentos_juridicos')
embedding_service = None

def init_services():
    global embedding_service
    if embedding_service is None:
        embedding_service = EmbeddingService()


@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    mensagem = data.get('mensagem', '')
    session_id = data.get('session_id', '')
    if not mensagem:
        return jsonify({'erro': 'Campo mensagem obrigatorio.'}), 400
    salvar_mensagem(session_id, 'user', mensagem)
    # Verifica se a sessão já teve modo real antes
    historico_sessao = carregar_historico(session_id)
    teve_modo_real = any(detectar_modo(m['mensagem'], historico=historico_sessao) == 'real' 
                     for m in historico_sessao 
                     if m['role'] == 'user')

    modo = 'real' if teve_modo_real or detectar_modo(mensagem, historico=historico_sessao) == 'real' else 'fachada'
    init_services()
    try:
        resposta = responder_pergunta(mensagem, embedding_service, colecao, client=None, modo=modo)
    except Exception as e:
        print(f'ERRO: {e}')
        resposta = 'Servico temporariamente indisponivel. Tente novamente.'
    salvar_mensagem(session_id, 'assistant', resposta)
    return jsonify({'resposta': resposta, 'modo': modo})


@app.route('/sessoes', methods=['GET'])
def sessoes():
    palavras_chave = ['violencia','medo','ajuda','agressao','marido','ameaca',
        'delegacia','machucou','bater','controlar','socorro','fugir','protetiva',
        'presa','trancada','agredida','perigo','ferida','machucada','batendo']
    conn = sqlite3.connect('historico.db')
    c = conn.cursor()
    c.execute('SELECT session_id, COUNT(*) as total FROM historico GROUP BY session_id')
    rows = c.fetchall()
    identificacoes = {}
    try:
        c.execute('SELECT session_id, nome FROM identificacao')
        for row in c.fetchall():
            identificacoes[row[0]] = row[1]
    except:
        pass
    conn.close()
    resumo = {}
    for row in rows:
        sid = row[0]
        hist = carregar_historico(sid)
        msgs_usuario = [m['mensagem'].lower() for m in hist if m['role'] == 'user']
        modo_detectado = 'real' if any(
            any(p in msg for p in palavras_chave) for msg in msgs_usuario
        ) else 'fachada'
        resumo[sid] = {
            'total_msgs': row[1],
            'modo_detectado': modo_detectado,
            'nome': identificacoes.get(sid, None)
        }
    return jsonify({'sessoes': resumo})


@app.route('/historico/<session_id>', methods=['GET'])
def historico(session_id):
    hist = carregar_historico(session_id)
    return jsonify({'session_id': session_id, 'historico': hist})

@app.route('/identificar', methods=['POST'])
def identificar():
    data = request.get_json()
    session_id = data.get('session_id', '')
    nome = data.get('nome', '')
    if not session_id or not nome:
        return jsonify({'erro': 'Dados incompletos.'}), 400
    conn = sqlite3.connect('historico.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS identificacao (
            session_id TEXT PRIMARY KEY,
            nome TEXT,
            consentimento INTEGER DEFAULT 1,
            timestamp TEXT
        )
    ''')
    c.execute('INSERT OR REPLACE INTO identificacao (session_id, nome, consentimento, timestamp) VALUES (?, ?, 1, ?)',
              (session_id, nome, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})

@app.route('/apagar/<session_id>', methods=['DELETE'])
def apagar(session_id):
    conn = sqlite3.connect('historico.db')
    c = conn.cursor()
    c.execute('DELETE FROM historico WHERE session_id = ?', (session_id,))
    c.execute('DELETE FROM identificacao WHERE session_id = ?', (session_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'apagado'})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
