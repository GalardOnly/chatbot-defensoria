from flask import Flask, request, jsonify, send_from_directory
import threading
import requests
import secrets
import hashlib
import hmac
import re
import base64
from functools import wraps
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_limiter.errors import RateLimitExceeded
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from conteudo_chat import (
    responder_pergunta,
    resposta_contingencia,
    criar_chat_groq,
    EmbeddingService,
    buscar_chunks_relevantes,
    ClassificadorViolencia,
    garantir_base_conhecimento,
    sanitizar_mensagem,
)
import chromadb
import os
import sqlite3
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "historico.db")


# ── CRIPTOGRAFIA DE CAMPOS SENSÍVEIS ────────────────────────────────────────
#
# Por que criptografia no nível da aplicação (não SQLCipher)?
#   SQLCipher exige compilação nativa de extensões C — incompatível com o
#   plano gratuito do Render e difícil de manter. A alternativa é cifrar
#   os campos sensíveis ANTES de gravar no banco, usando Fernet (AES-128-CBC
#   + HMAC-SHA256). O SQLite continua padrão, mas os dados ficam ilegíveis
#   sem a chave — mesmo com acesso direto ao arquivo .db.
#
# Campos criptografados:
#   historico.mensagem        — relato da vítima
#   identificacao.nome        — nome fornecido voluntariamente
#
# Campos NÃO criptografados (necessários para queries):
#   session_id, role, timestamp, tipo_violencia, gravidade
#   (nenhum desses identifica diretamente a vítima)
#
# Gerenciamento da chave:
#   A chave e derivada de DB_ENCRYPTION_KEY (variável de ambiente) via
#   PBKDF2-SHA256 com 600.000 iteracoes e salt fixo por instalacao.
#   O salt e armazenado em .db_salt (fora do banco). Faca backup de ambos.
#
# Rotacao de chave:
#   Para rotacionar: exporte dados com a chave antiga, troque
#   DB_ENCRYPTION_KEY + apague .db_salt, reimporte com nova chave.

_SALT_FILE = os.path.join(BASE_DIR, ".db_salt")
_FERNET = None          # Fernet | None — inicializado em _inicializar_cripto()
_CRIPTO_ATIVA = False   # False = modo degradado sem chave


def _inicializar_cripto():
    """
    Deriva a chave Fernet a partir de DB_ENCRYPTION_KEY + salt persistente.
    Chamada uma vez no boot. Se DB_ENCRYPTION_KEY nao estiver definida,
    entra em modo degradado: dados gravados em texto plano com aviso claro.

    Salt: gerado uma unica vez e gravado em .db_salt. Deve ser incluido
    no backup junto com DB_ENCRYPTION_KEY. Sem ambos, dados sao perdidos.
    """
    global _FERNET, _CRIPTO_ATIVA

    senha = os.getenv("DB_ENCRYPTION_KEY", "").strip().encode()
    if not senha:
        print(
            "\n[SEGURANÇA] AVISO: DB_ENCRYPTION_KEY não definida. "
            "Dados sensiveis serao gravados em TEXTO PLANO.\n"
            "Gere uma chave: python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "e adicione ao .env como DB_ENCRYPTION_KEY=<valor>\n"
        )
        _CRIPTO_ATIVA = False
        return

    if os.path.exists(_SALT_FILE):
        with open(_SALT_FILE, "rb") as f:
            salt = f.read()
    else:
        salt = secrets.token_bytes(32)
        with open(_SALT_FILE, "wb") as f:
            f.write(salt)
        print(f"[Cripto] Salt gerado e salvo em {_SALT_FILE}. Inclua no backup!")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    chave = base64.urlsafe_b64encode(kdf.derive(senha))
    _FERNET = Fernet(chave)
    _CRIPTO_ATIVA = True
    print("[Cripto] Criptografia ATIVA — Fernet/AES-128-CBC + HMAC-SHA256")


def cifrar(texto):
    """
    Cifra texto com Fernet. Retorna token cifrado como string UTF-8.
    Se criptografia inativa, devolve texto original (modo degradado).
    None e tratado como string vazia.
    """
    if texto is None:
        texto = ""
    if not _CRIPTO_ATIVA or _FERNET is None:
        return texto
    return _FERNET.encrypt(texto.encode("utf-8")).decode("utf-8")


def decifrar(token):
    """
    Decifra um token Fernet. Retorna o texto original.
    Trata dados legados (texto plano anterior a criptografia) devolvendo
    o valor original sem excecao — evita quebrar historico existente.
    """
    if not token:
        return ""
    if not _CRIPTO_ATIVA or _FERNET is None:
        return token
    try:
        return _FERNET.decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        # Dado legado em texto plano ou corrompido
        print("[Cripto] AVISO: token nao decifrado — pode ser dado legado.")
        return token


# ── AUTENTICAÇÃO ADMINISTRATIVA ──────────────────────────────────────────────
#
# Como funciona:
#   1. Defina ADMIN_TOKEN no seu .env com um valor longo e aleatório.
#      Gere com: python -c "import secrets; print(secrets.token_hex(32))"
#   2. Toda requisição a endpoints admin deve enviar o header:
#      Authorization: Bearer <seu-token>
#   3. A comparação usa hmac.compare_digest para evitar timing attacks.
#   4. Se ADMIN_TOKEN não estiver definido no ambiente, o servidor recusa
#      iniciar — endpoints admin nunca ficam acessíveis sem token.

def _obter_token_admin() -> str:
    """
    Lê ADMIN_TOKEN do ambiente. Aborta se ausente ou muito curto.
    Chamado uma única vez no boot — falha rápida e explícita.
    """
    token = os.getenv("ADMIN_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "[SEGURANÇA] ADMIN_TOKEN não está definido no ambiente. "
            "Gere um token com: python -c \"import secrets; print(secrets.token_hex(32))\" "
            "e adicione ao .env antes de iniciar o servidor."
        )
    if len(token) < 32:
        raise RuntimeError(
            "[SEGURANÇA] ADMIN_TOKEN muito curto (mínimo 32 caracteres). "
            "Gere um novo com: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return token


# Carregado uma vez no boot. Se falhar, o processo encerra.
ADMIN_TOKEN: str = _obter_token_admin()

# Hash do token armazenado em memória — nunca comparamos o token em texto plano
# em hot path; usamos o digest para que um eventual core dump não exponha o segredo.
_ADMIN_TOKEN_DIGEST: bytes = hashlib.sha256(ADMIN_TOKEN.encode()).digest()


def _token_valido(token_recebido: str) -> bool:
    """
    Compara o token recebido com o configurado de forma resistente a timing attack.
    Ambos os lados são hasheados antes da comparação para equalizar o tamanho,
    tornando hmac.compare_digest eficaz independentemente do comprimento do input.
    """
    digest_recebido = hashlib.sha256(token_recebido.encode()).digest()
    return hmac.compare_digest(_ADMIN_TOKEN_DIGEST, digest_recebido)


def _extrair_bearer(auth_header: str | None) -> str:
    """
    Extrai o token do header 'Authorization: Bearer <token>'.
    Retorna string vazia se o header estiver ausente ou malformado.
    """
    if not auth_header:
        return ""
    partes = auth_header.strip().split(" ", 1)
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return ""
    return partes[1].strip()


def requer_admin(f):
    """
    Decorator que protege um endpoint com autenticação Bearer.

    Uso:
        @app.route("/sessoes")
        @requer_admin
        def sessoes(): ...

    Retorna 401 se o header estiver ausente.
    Retorna 403 se o token for inválido.
    Registra toda tentativa de acesso com IP e timestamp para auditoria.
    """
    @wraps(f)
    def decorado(*args, **kwargs):
        ip        = request.remote_addr or "desconhecido"
        endpoint  = request.path
        timestamp = datetime.now(timezone.utc).isoformat()

        auth_header  = request.headers.get("Authorization")
        token_enviado = _extrair_bearer(auth_header)

        if not token_enviado:
            # Log de tentativa sem token
            print(
                f"[AUDIT] {timestamp} | ACESSO NEGADO (sem token) | "
                f"endpoint={endpoint} | ip={ip}"
            )
            return jsonify({
                "erro": "Autenticação obrigatória.",
                "detalhe": "Envie o header: Authorization: Bearer <token>"
            }), 401

        if not _token_valido(token_enviado):
            # Log de tentativa com token errado — potencial ataque
            print(
                f"[AUDIT] {timestamp} | ACESSO NEGADO (token inválido) | "
                f"endpoint={endpoint} | ip={ip}"
            )
            return jsonify({"erro": "Token inválido ou expirado."}), 403

        # Acesso autorizado — log de auditoria positivo
        print(
            f"[AUDIT] {timestamp} | ACESSO ADMIN AUTORIZADO | "
            f"endpoint={endpoint} | ip={ip}"
        )
        return f(*args, **kwargs)

    return decorado


# ── VALIDAÇÃO DE session_id ──────────────────────────────────────────────────
# session_id vem do frontend e é usado em queries SQL parametrizadas (seguro),
# mas ainda assim limitamos o formato para evitar IDs absurdos em logs e no banco.
_SESSION_ID_RE = re.compile(r'^[a-zA-Z0-9_\-]{8,128}$')


def session_id_valido(session_id: str) -> bool:
    return bool(session_id and _SESSION_ID_RE.match(session_id))


def obter_conexao_db():
    """
    Abre uma conexão SQLite configurada para acesso concorrente moderado.

    WAL melhora a convivência entre leituras e escritas; busy_timeout reduz
    erros transitórios de "database is locked" em bursts de requisições.
    """
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


# ── BANCO DE DADOS ───────────────────────────────────────────────────────────
def init_db():
    conn = obter_conexao_db()
    c    = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS historico (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id           TEXT    NOT NULL,
            role                 TEXT    NOT NULL,
            mensagem             TEXT    NOT NULL,
            timestamp            TEXT    NOT NULL,
            tipo_violencia       TEXT,
            gravidade            TEXT,
            -- Features booleanas anonimizadas (extraidas ANTES de cifrar a mensagem)
            -- Permitem analises de tendencia sem expor o conteudo da mensagem cifrada.
            -- Nunca contem texto original — apenas indicadores 0/1.
            feat_menciona_arma   INTEGER DEFAULT 0,
            feat_menciona_menor  INTEGER DEFAULT 0,
            feat_menciona_saida  INTEGER DEFAULT 0,
            feat_risco_imediato  INTEGER DEFAULT 0,
            feat_primeiro_relato INTEGER DEFAULT 0
        )
    """)
    # Tabela de identificação criada aqui — não mais no endpoint /identificar
    c.execute("""
        CREATE TABLE IF NOT EXISTS identificacao (
            session_id   TEXT PRIMARY KEY,
            nome         TEXT,
            consentimento INTEGER DEFAULT 1,
            timestamp    TEXT
        )
    """)
    # Migracoes seguras de schema — novas colunas adicionadas sem quebrar instalacoes antigas
    colunas_novas = [
        ("tipo_violencia",       "TEXT"),
        ("gravidade",            "TEXT"),
        ("feat_menciona_arma",   "INTEGER DEFAULT 0"),
        ("feat_menciona_menor",  "INTEGER DEFAULT 0"),
        ("feat_menciona_saida",  "INTEGER DEFAULT 0"),
        ("feat_risco_imediato",  "INTEGER DEFAULT 0"),
        ("feat_primeiro_relato", "INTEGER DEFAULT 0"),
    ]
    for coluna, tipo in colunas_novas:
        try:
            c.execute(f"ALTER TABLE historico ADD COLUMN {coluna} {tipo}")
        except sqlite3.OperationalError:
            pass   # coluna ja existe
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_historico_session_id
        ON historico(session_id, id)
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_historico_session_role_id
        ON historico(session_id, role, id)
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_historico_session_timestamp
        ON historico(session_id, timestamp)
    """)
    conn.commit()
    conn.close()


def extrair_features(mensagem: str, session_id: str) -> dict:
    """
    Extrai features booleanas anonimizadas da mensagem ANTES de cifrar.

    Por que extrair antes de cifrar?
      Criptografar a mensagem impede queries analiticas no banco (nao e possivel
      fazer SELECT WHERE mensagem LIKE '%arma%' em texto cifrado).
      Ao extrair features booleanas antes, preservamos capacidade de analise
      de tendencias e auditoria sem expor o conteudo original.

    As features sao indicadores 0/1 — nunca armazenam texto, apenas presenca/ausencia
    de padroes. Sao seguras para ficar em colunas nao cifradas.
    """
    t = (mensagem or "").lower()

    # Mencao a arma ou instrumento de agressao fisica
    feat_arma = int(any(p in t for p in [
        "faca", "fak", "arma", "pistola", "revolver", "espingarda",
        "tiro", "bala", "pau", "cinto", "chute", "soco", "estrangul",
        "enforc", "queimou", "queimad",
    ]))

    # Mencao a criancas ou adolescentes no relato
    feat_menor = int(any(p in t for p in [
        "filho", "filha", "crianca", "bebe", "bebê", "nenê", "nenê",
        "menor", "adolescente", "escola", "guardiao", "guarda",
    ]))

    # Indica que a vitima quer ou tentou sair da situacao
    feat_saida = int(any(p in t for p in [
        "quero sair", "quer sair", "foi embora", "saiu de casa", "fugir",
        "fui embora", "largar", "separar", "divorcio", "divorciar",
        "abandonar", "ir embora", "deixar ele", "deixa ele",
    ]))

    # Indicadores de risco iminente ou emergencia
    feat_risco = int(any(p in t for p in [
        "socorro", "me mata", "vai me matar", "ameacou matar", "ameaca de morte",
        "estou com medo", "risco de vida", "me bate todo dia", "nao consigo sair",
        "trancada", "presa em casa", "me sequestrou",
    ]))

    # Heuristica de primeiro relato na sessao
    conn = obter_conexao_db()
    c    = conn.cursor()
    c.execute("SELECT COUNT(*) FROM historico WHERE session_id = ? AND role = 'user'", (session_id,))
    total_user = c.fetchone()[0]
    conn.close()
    feat_primeiro = int(total_user == 0)

    return {
        "feat_menciona_arma":   feat_arma,
        "feat_menciona_menor":  feat_menor,
        "feat_menciona_saida":  feat_saida,
        "feat_risco_imediato":  feat_risco,
        "feat_primeiro_relato": feat_primeiro,
    }


def salvar_mensagem(session_id, role, mensagem, tipo_violencia=None, gravidade=None):
    # 1. Extrair features ANTES de cifrar (so para mensagens do usuario)
    feats = extrair_features(mensagem, session_id) if role == "user" else {
        "feat_menciona_arma":   0, "feat_menciona_menor":  0,
        "feat_menciona_saida":  0, "feat_risco_imediato":  0,
        "feat_primeiro_relato": 0,
    }

    # 2. Cifrar mensagem
    conn           = obter_conexao_db()
    c              = conn.cursor()
    timestamp      = datetime.now(timezone.utc).isoformat()
    mensagem_salva = cifrar(mensagem)

    # 3. Gravar com features em colunas abertas (nao cifradas)
    c.execute(
        """INSERT INTO historico
           (session_id, role, mensagem, timestamp, tipo_violencia, gravidade,
            feat_menciona_arma, feat_menciona_menor, feat_menciona_saida,
            feat_risco_imediato, feat_primeiro_relato)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id, role, mensagem_salva, timestamp, tipo_violencia, gravidade,
            feats["feat_menciona_arma"],   feats["feat_menciona_menor"],
            feats["feat_menciona_saida"],  feats["feat_risco_imediato"],
            feats["feat_primeiro_relato"],
        ),
    )
    conn.commit()
    conn.close()


def carregar_historico(session_id):
    conn = obter_conexao_db()
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
            "mensagem":       decifrar(row[1]),   # decifrado ao sair do banco
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
        "socorro", "agred", "violenc", "ameac", "medo", "abuso",
        "bater", "espanc", "marido", "namorado", "companheiro", "agressor",
        "protetiva", "delegacia", "denuncia", "machuc", "feriu", "risco",
        "humilha", "xing", "controla", "persegu", "tranca", "suficiente",
    ]
    termos_fachada = [
        "receita", "bolo", "cozinha", "decoracao", "limpeza", "faxina",
        "casa", "lar", "organizacao", "mofo", "encanamento", "jardim",
        "planta", "quintal", "lavar roupa", "detergente", "sabao",
        "fogao", "geladeira", "sofa", "mancha", "varrer", "passar pano",
    ]

    if any(termo in texto for termo in termos_reais):
        return "real"
    if any(termo in texto for termo in termos_fachada):
        return "fachada"
    return "indefinido"


def historico_indica_fachada(historico):
    termos_fachada = [
        "receita", "bolo", "cozinha", "decoracao", "limpeza", "faxina",
        "casa", "lar", "organizacao", "mofo", "encanamento", "jardim",
        "sofa", "sofá", "roupa", "fogao", "fogão", "geladeira",
        "mancha", "lavar", "detergente", "sabao", "planta", "quintal",
        "varrer", "passar pano",
    ]
    for msg in historico[-6:]:
        texto = (msg.get("mensagem") or msg.get("content") or "").lower()
        if any(termo in texto for termo in termos_fachada):
            return True
    return False


def detectar_modo(mensagem, historico=None):
    historico = historico or []
    modo_local = detectar_modo_local(mensagem)
    if modo_local == "indefinido" and historico_indica_fachada(historico):
        modo_local = "fachada"
    if modo_local == "real":
        return "real"

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        return "real" if any(
            m.get("tipo_violencia") and m["tipo_violencia"] != "nao_violencia"
            for m in historico if m["role"] == "user"
        ) else modo_local

    contexto = "\n".join([f"{m['role']}: {m['mensagem']}" for m in historico[-4:]])
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

# ── CORS ─────────────────────────────────────────────────────────────────────
# Permitimos apenas a origem configurada em ALLOWED_ORIGIN.
# Em desenvolvimento, defina ALLOWED_ORIGIN=http://localhost:5000 no .env.
# Em produção, defina ALLOWED_ORIGIN=https://seu-dominio.com
#
# Se ALLOWED_ORIGIN não estiver definida, logamos um aviso mas permitimos
# qualquer origem para não travar o ambiente de desenvolvimento local.
# NUNCA deixe ALLOWED_ORIGIN indefinida em produção.
_ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "").strip()
if _ALLOWED_ORIGIN:
    CORS(app, origins=[_ALLOWED_ORIGIN], supports_credentials=False)
    print(f"[CORS] Origem permitida: {_ALLOWED_ORIGIN}")
else:
    CORS(app)
    print(
        "[CORS] AVISO: ALLOWED_ORIGIN não definida — aceitando qualquer origem.\n"
        "       Defina ALLOWED_ORIGIN=https://seu-dominio.com no .env para produção."
    )

# ── RATE LIMITING ─────────────────────────────────────────────────────────────
# Proteção contra abuso do endpoint /chat em duas camadas:
#
#   Camada 1 — por IP global:
#     30 requisições/minuto  — impede burst rápido de um único IP
#     200 requisições/hora   — impede abuso sustentado ao longo do tempo
#
#   Camada 2 — por session_id (chave customizada):
#     20 requisições/minuto  — uma conversa real não precisa de mais
#     100 requisições/hora
#
# Storage: memory:// funciona para uma instância única (Render free tier).
# Para múltiplas instâncias, troque por redis://... e adicione REDIS_URL ao .env.
#
# Endpoints administrativos têm limite próprio mais restritivo (5/minuto)
# para dificultar enumeração de sessões e força bruta no token.
# /health e / são isentos — chamados por monitores e pelo próprio keep-alive.

def _chave_session_ou_ip() -> str:
    """
    Usa session_id como chave de rate limit quando disponível,
    caindo de volta para IP quando ausente (ex: requisições malformadas).
    Isso evita que um atacante que muda de IP constantemente contorne o limite.
    """
    try:
        data = request.get_json(silent=True) or {}
        sid  = (data.get("session_id") or "").strip()
        if sid and _SESSION_ID_RE.match(sid):
            return f"session:{sid}"
    except Exception:
        pass
    return f"ip:{get_remote_address()}"


limiter = Limiter(
    key_func=get_remote_address,      # chave padrão para rotas sem decorator
    app=app,
    default_limits=[],                # sem limite global — aplicamos por rota
    storage_uri="memory://",
    strategy="fixed-window",
)


@app.errorhandler(RateLimitExceeded)
def _handle_rate_limit(e):
    """Retorna JSON consistente em vez do HTML padrão do flask-limiter."""
    return jsonify({
        "erro":    "Muitas requisições. Aguarde um momento antes de tentar novamente.",
        "retry_after": getattr(e, "retry_after", 60),
    }), 429

_inicializar_cripto()   # deve rodar antes de init_db()
init_db()

chroma_client = chromadb.PersistentClient(path="chroma_db")
colecao       = chroma_client.get_or_create_collection("documentos_juridicos")

embedding_service  = None
classificador      = None
_init_lock         = threading.Lock()
_servicos_prontos  = False
_ultimo_erro_chat  = None

# Event sinalizado pela thread de boot quando todos os serviços estiverem prontos.
# Qualquer thread de request que chegar antes do boot terminar chama
# _boot_event.wait(timeout) — libera imediatamente quando o boot conclui,
# sem ocupar CPU e sem criar objetos descartáveis a cada iteração.
_boot_event = threading.Event()


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
            os.path.exists("modelos/rf_tipo.joblib")
            and os.path.exists("modelos/rf_gravidade.joblib")
            and os.path.exists("modelos/modelos.manifest.json")
        ):
            print("[boot] Carregando ClassificadorViolencia (TF-IDF + RF, verificação de hash)...")
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
            print("[boot] Modelos RF ou manifesto não encontrados — pré-classificação desativada.")

        _servicos_prontos = True
        _boot_event.set()   # libera todas as threads esperando em garantir_servicos()
        print("[boot] Todos os serviços prontos.")


def garantir_servicos(timeout: float = 60.0) -> bool:
    """
    Bloqueia até os serviços de boot estarem prontos ou o timeout expirar.

    Usa um threading.Event compartilhado sinalizado pela thread de boot.
    Diferente do busy-wait anterior (que criava um Event descartável a cada
    iteração e bloqueava a thread de request por até 60s em fatias de 0.5s),
    esta implementação:
      - Libera IMEDIATAMENTE quando o boot conclui (sem esperar a próxima fatia)
      - Não cria objetos descartáveis em loop
      - Não ocupa CPU durante a espera
      - Retorna False se o timeout expirar — o caller decide como reagir

    Returns:
        True  — serviços prontos
        False — timeout expirado (boot ainda em andamento)
    """
    if _servicos_prontos:
        return True                        # caminho rápido: já prontos
    pronto = _boot_event.wait(timeout=timeout)
    if not pronto:
        print(
            f"[garantir_servicos] AVISO: timeout de {timeout}s expirado. "
            "Boot ainda em andamento — resposta pode usar fallback."
        )
    return pronto


# ── ENDPOINTS PÚBLICOS ───────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
@limiter.exempt
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/painel", methods=["GET"])
def painel():
    """
    Painel administrativo.
    O HTML é público, mas os dados só carregam com ADMIN_TOKEN via fetch.
    Isso permite abrir a interface no navegador sem depender de headers
    customizados na navegação inicial.
    """
    return send_from_directory(BASE_DIR, "painel.html")


@app.route("/chat", methods=["POST"])
@limiter.limit("30 per minute", key_func=get_remote_address)
@limiter.limit("200 per hour",  key_func=get_remote_address)
@limiter.limit("20 per minute", key_func=_chave_session_ou_ip)
@limiter.limit("100 per hour",  key_func=_chave_session_ou_ip)
def chat():
    global _ultimo_erro_chat
    data       = request.get_json(silent=True) or {}
    mensagem   = (data.get("mensagem") or "").strip()
    session_id = (data.get("session_id") or "").strip()

    if not mensagem:
        return jsonify({"erro": "Campo mensagem obrigatório."}), 400

    # Validação do session_id — rejeita IDs malformados
    if not session_id_valido(session_id):
        return jsonify({
            "erro": "session_id inválido.",
            "detalhe": "Use entre 8 e 128 caracteres alfanuméricos, hífen ou underscore."
        }), 400

    # Limite de tamanho da mensagem — rejeita payloads absurdamente grandes
    # antes de qualquer processamento (classificação, LLM, banco).
    # 2000 chars ≈ ~500 tokens, suficiente para qualquer relato real.
    if len(mensagem) > 2_000:
        return jsonify({
            "erro": "Mensagem muito longa.",
            "detalhe": "Máximo de 2000 caracteres por mensagem."
        }), 400

    # Sanitização prévia — detecta injection antes de salvar no banco.
    # Salvamos a mensagem original no banco (para auditoria humana),
    # mas usamos a versão limpa em todas as operações subsequentes.
    mensagem_limpa, alertas = sanitizar_mensagem(mensagem, session_id)

    salvar_mensagem(session_id, "user", mensagem)   # banco recebe original
    historico_sessao = carregar_historico(session_id)

    # garantir_servicos() retorna False se o boot ainda não terminou após 60s.
    # Nesse caso continuamos — classificador e embedding_service podem ser None,
    # e o código downstream já trata ambos os casos graciosamente.
    _boot_ok = garantir_servicos()
    if not _boot_ok:
        print(
            f"[chat] Boot ainda em andamento para session={session_id}. "
            "Prosseguindo sem classificador/embeddings."
        )

    # ── Pré-classificação ─────────────────────────────────────────────────────
    # Classifica a mensagem limpa — padrões de injection não devem influenciar
    # o classificador de violência.
    classificacao = None
    if classificador:
        try:
            classificacao = classificador.classificar(mensagem_limpa)
            conn = obter_conexao_db()
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
    teve_real_recente = any(
        m.get("tipo_violencia") and m["tipo_violencia"] != "nao_violencia"
        for m in historico_sessao[-8:] if m["role"] == "user"
    )
    classificacao_indica_real = classificacao is not None and classificacao["eh_violencia"]
    modo_local = detectar_modo_local(mensagem_limpa)
    try:
        modo_llm = detectar_modo(mensagem_limpa, historico=historico_sessao)
    except Exception as e:
        print(f"[chat] Aviso ao detectar modo: {e}")
        modo_llm = "real" if (teve_real_recente or classificacao_indica_real) else "fachada"

    if classificacao_indica_real or modo_local == "real":
        modo_final = "real"
    elif modo_local == "fachada":
        modo_final = "fachada"
    elif modo_llm == "real":
        modo_final = "real"
    elif modo_llm == "fachada":
        modo_final = "fachada"
    elif teve_real_recente or teve_real_no_historico:
        modo_final = "real"
    else:
        modo_final = "fachada"

    # ── Resposta da LLM ───────────────────────────────────────────────────────
    historico_api = [
        {"role": m["role"], "content": m["mensagem"]} for m in historico_sessao
    ]
    try:
        resposta = responder_pergunta(
            pergunta=mensagem_limpa,          # versão sanitizada
            embedding_service=embedding_service,
            colecao=colecao,
            historico=historico_api,
            modo=modo_final,
            classificacao=classificacao,
            session_id=session_id,            # para log de auditoria
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

    # Retornamos apenas o necessário para o frontend — dados internos de
    # classificação (tipo_prob, gravidade_prob) ficam de fora da resposta pública.
    return jsonify({
        "resposta": resposta,
        "modo":     modo_final,
    })


# ── ENDPOINTS ADMINISTRATIVOS (todos protegidos por @requer_admin) ────────────

@app.route("/sessoes", methods=["GET"])
@requer_admin
@limiter.limit("5 per minute")
def sessoes():
    conn = obter_conexao_db()
    c    = conn.cursor()
    c.execute("SELECT session_id, COUNT(*) as total FROM historico GROUP BY session_id")
    rows = c.fetchall()
    identificacoes = {}
    try:
        c.execute("SELECT session_id, nome FROM identificacao")
        for row in c.fetchall():
            identificacoes[row[0]] = decifrar(row[1])   # decifrado ao sair do banco
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
            "ultima_msg":       hist[-1]["timestamp"] if hist else None,
        }
    return jsonify({"sessoes": resumo})


@app.route("/historico/<session_id>", methods=["GET"])
@requer_admin
@limiter.limit("5 per minute")
def historico(session_id):
    if not session_id_valido(session_id):
        return jsonify({"erro": "session_id inválido."}), 400
    return jsonify({"session_id": session_id, "historico": carregar_historico(session_id)})


def _salvar_identificacao():
    data       = request.get_json(silent=True) or {}
    session_id = (data.get("session_id") or "").strip()
    nome       = (data.get("nome") or "").strip()

    if not session_id or not nome:
        return jsonify({"erro": "Dados incompletos."}), 400
    if not session_id_valido(session_id):
        return jsonify({"erro": "session_id inválido."}), 400
    # Limite de tamanho no nome para evitar entradas abusivas
    if len(nome) > 200:
        return jsonify({"erro": "Nome muito longo (máximo 200 caracteres)."}), 400

    conn = obter_conexao_db()
    c    = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO identificacao VALUES (?, ?, 1, ?)",
        (session_id, cifrar(nome), datetime.now(timezone.utc).isoformat()),   # nome cifrado
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


def _apagar_sessao(session_id: str):
    if not session_id_valido(session_id):
        return jsonify({"erro": "session_id inválido."}), 400

    conn = obter_conexao_db()
    c    = conn.cursor()
    c.execute("DELETE FROM historico     WHERE session_id = ?", (session_id,))
    c.execute("DELETE FROM identificacao WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

    print(
        f"[AUDIT] {datetime.now(timezone.utc).isoformat()} | "
        f"SESSÃO APAGADA | session_id={session_id} | ip={request.remote_addr}"
    )
    return jsonify({"status": "apagado"})


@app.route("/identificar", methods=["POST"])
@requer_admin
@limiter.limit("5 per minute")
def identificar_admin():
    return _salvar_identificacao()


@app.route("/apagar/<session_id>", methods=["DELETE"])
@requer_admin
@limiter.limit("5 per minute")
def apagar_admin(session_id):
    return _apagar_sessao(session_id)


@app.route("/conversa/identificar", methods=["POST"])
@limiter.limit("10 per minute", key_func=_chave_session_ou_ip)
def identificar_publico():
    return _salvar_identificacao()


@app.route("/conversa/<session_id>", methods=["DELETE"])
@limiter.limit("10 per minute", key_func=get_remote_address)
def apagar_publico(session_id):
    return _apagar_sessao(session_id)


@app.route("/health", methods=["GET"])
@limiter.exempt
def health():
    """
    Health check público — retorna apenas status operacional.
    Detalhes internos (chaves de API, erros) só com token de admin.
    """
    return jsonify({
        "status":           "ok",
        "servicos_prontos": _servicos_prontos,
    })


@app.route("/health/admin", methods=["GET"])
@requer_admin
@limiter.limit("10 per minute")
def health_admin():
    """Health check detalhado — apenas para administradores."""
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
# O Render encerra instâncias gratuitas após ~15min sem tráfego.
# Uma thread daemon faz um GET em /health a cada 10 minutos para evitar isso.
#
# Por que thread + loop em vez de threading.Timer recursivo?
#   - Timer recursivo cria um objeto novo a cada ciclo, mesmo em falha.
#     Se o servidor externo ficar offline por horas, centenas de Timers
#     acumulam em memória sem nunca serem coletados.
#   - Não há como parar ou inspecionar Timers já agendados.
#   - Uma thread daemon com loop + Event.wait() usa um único objeto,
#     pode ser interrompida imediatamente via _ping_stop.set(),
#     e limita falhas consecutivas antes de desistir.

_ping_stop = threading.Event()   # sinalizar para parar o loop de ping

_PING_INTERVALO   = 600    # segundos entre pings (10 min)
_PING_MAX_FALHAS  = 10     # para de tentar após N falhas consecutivas


def _loop_ping():
    """
    Thread daemon que mantém o servidor ativo no Render free tier.

    Comportamento:
      - Aguarda _PING_INTERVALO segundos entre cada ping usando Event.wait()
        (liberado imediatamente se _ping_stop for sinalizado).
      - Conta falhas consecutivas. Após _PING_MAX_FALHAS seguidas, encerra
        a thread com aviso — evita loop infinito em caso de má configuração.
      - Falha isolada não incrementa contador (reseta em sucesso).
      - Não cria nenhum objeto novo por ciclo — usa a mesma thread e o
        mesmo Event durante toda a vida do processo.
    """
    url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
    if not url:
        print("[ping] RENDER_EXTERNAL_URL não definida — keep-alive desativado.")
        return

    falhas_consecutivas = 0
    print(f"[ping] Keep-alive iniciado → {url}/health a cada {_PING_INTERVALO}s")

    while not _ping_stop.wait(timeout=_PING_INTERVALO):
        try:
            resp = requests.get(f"{url}/health", timeout=5)
            resp.raise_for_status()
            falhas_consecutivas = 0
            print(f"[ping] OK ({resp.status_code})")
        except Exception as e:
            falhas_consecutivas += 1
            print(f"[ping] Falhou ({falhas_consecutivas}/{_PING_MAX_FALHAS}): {e}")
            if falhas_consecutivas >= _PING_MAX_FALHAS:
                print(
                    f"[ping] {_PING_MAX_FALHAS} falhas consecutivas — "
                    "encerrando keep-alive. Verifique RENDER_EXTERNAL_URL."
                )
                return

    print("[ping] Keep-alive encerrado.")


# ── BOOT — serviços pesados em background, servidor sobe imediatamente ────────
threading.Thread(target=_carregar_servicos_background, daemon=True).start()
threading.Thread(target=_loop_ping, daemon=True, name="keep-alive").start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
