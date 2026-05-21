"""
gerenciar_cripto.py — Utilitário de criptografia do banco de dados.

Comandos disponíveis:
    python gerenciar_cripto.py migrar       — cifra dados legados em texto plano
    python gerenciar_cripto.py verificar    — verifica se todos os campos estão cifrados
    python gerenciar_cripto.py rotacionar   — troca a chave de criptografia

Antes de qualquer operação, defina DB_ENCRYPTION_KEY no .env ou no ambiente.
Para rotacionar, defina também DB_ENCRYPTION_KEY_NOVA.
"""

import os
import sys
import base64
import hashlib
import secrets
import sqlite3
from dotenv import load_dotenv
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

load_dotenv()
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
SALT_FILE = os.path.join(BASE_DIR, ".db_salt")
DB_PATH   = os.path.join(BASE_DIR, "historico.db")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _derivar_fernet(senha_env: str, salt_file: str, criar_salt: bool = False) -> Fernet:
    senha = os.getenv(senha_env, "").strip().encode()
    if not senha:
        raise SystemExit(f"[ERRO] Variável de ambiente '{senha_env}' não definida.")

    if criar_salt or not os.path.exists(salt_file):
        salt = secrets.token_bytes(32)
        with open(salt_file, "wb") as f:
            f.write(salt)
        print(f"  Salt gerado e salvo em {salt_file}")
    else:
        with open(salt_file, "rb") as f:
            salt = f.read()

    kdf   = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000)
    chave = base64.urlsafe_b64encode(kdf.derive(senha))
    return Fernet(chave)


def _eh_cifrado(valor: str | None) -> bool:
    """Heurística: tokens Fernet começam com 'gAAAAA'."""
    return bool(valor and valor.startswith("gAAAAA"))


def _decifrar_seguro(fernet: Fernet, valor: str) -> str | None:
    """Decifra ou retorna None se inválido (dado legado)."""
    try:
        return fernet.decrypt(valor.encode()).decode()
    except (InvalidToken, Exception):
        return None


# ── Comando: migrar ───────────────────────────────────────────────────────────

def cmd_migrar():
    """
    Cifra todos os registros que ainda estão em texto plano.
    Seguro para rodar múltiplas vezes — registros já cifrados são ignorados.
    """
    print("\n── MIGRAÇÃO: cifrando dados legados ──────────────────────────────")
    fernet = _derivar_fernet("DB_ENCRYPTION_KEY", SALT_FILE)

    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    # historico.mensagem
    c.execute("SELECT id, mensagem FROM historico")
    rows     = c.fetchall()
    migrados = 0
    pulados  = 0

    for row_id, mensagem in rows:
        if _eh_cifrado(mensagem):
            pulados += 1
            continue
        cifrado = fernet.encrypt((mensagem or "").encode()).decode()
        c.execute("UPDATE historico SET mensagem = ? WHERE id = ?", (cifrado, row_id))
        migrados += 1

    print(f"  historico.mensagem   — {migrados} cifrados, {pulados} já cifrados")

    # identificacao.nome
    c.execute("SELECT session_id, nome FROM identificacao")
    rows     = c.fetchall()
    migrados = 0
    pulados  = 0

    for sid, nome in rows:
        if not nome or _eh_cifrado(nome):
            pulados += 1
            continue
        cifrado = fernet.encrypt(nome.encode()).decode()
        c.execute("UPDATE identificacao SET nome = ? WHERE session_id = ?", (cifrado, sid))
        migrados += 1

    print(f"  identificacao.nome   — {migrados} cifrados, {pulados} já cifrados")

    conn.commit()
    conn.close()
    print("\n  Migração concluída. Reinicie o servidor.")


# ── Comando: verificar ────────────────────────────────────────────────────────

def cmd_verificar():
    """
    Verifica quantos registros estão cifrados vs. texto plano.
    Não modifica dados.
    """
    print("\n── VERIFICAÇÃO do estado de criptografia ─────────────────────────")
    fernet = _derivar_fernet("DB_ENCRYPTION_KEY", SALT_FILE)

    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    # historico
    c.execute("SELECT COUNT(*) FROM historico")
    total_hist = c.fetchone()[0]
    c.execute("SELECT mensagem FROM historico")
    cifrados  = sum(1 for (m,) in c.fetchall() if _eh_cifrado(m))
    plano     = total_hist - cifrados
    print(f"\n  historico ({total_hist} registros)")
    print(f"    Cifrados    : {cifrados}")
    print(f"    Texto plano : {plano}  {'← rode migrar' if plano else '(ok)'}")

    # identificacao
    c.execute("SELECT COUNT(*) FROM identificacao")
    total_id = c.fetchone()[0]
    c.execute("SELECT nome FROM identificacao")
    cifrados = sum(1 for (n,) in c.fetchall() if _eh_cifrado(n or ""))
    plano    = total_id - cifrados
    print(f"\n  identificacao ({total_id} registros)")
    print(f"    Cifrados    : {cifrados}")
    print(f"    Texto plano : {plano}  {'← rode migrar' if plano else '(ok)'}")

    # Teste de decifracao com amostra sem expor conteudo sensivel.
    c.execute("SELECT mensagem FROM historico WHERE mensagem LIKE 'gAAAAA%' LIMIT 3")
    amostras = c.fetchall()
    if amostras:
        print("\n  Teste de decifracao (3 amostras, sem exibir conteudo):")
        for (token,) in amostras:
            texto = _decifrar_seguro(fernet, token)
            if texto is not None:
                resumo = hashlib.sha256(texto.encode("utf-8")).hexdigest()[:12]
                print(f"    OK  -> tamanho={len(texto)} hash={resumo}")
            else:
                print("    FALHA - token nao decifrado (chave errada?)")

    conn.close()
    print()


# ── Comando: rotacionar ───────────────────────────────────────────────────────

def cmd_rotacionar():
    """
    Re-cifra todos os registros da chave antiga para a nova.

    Requer:
      DB_ENCRYPTION_KEY      — chave ATUAL (para decifrar)
      DB_ENCRYPTION_KEY_NOVA — chave NOVA  (para cifrar)

    O salt antigo é mantido para a chave atual e um novo salt é gerado
    para a chave nova, salvo em .db_salt_nova. Após confirmar sucesso:
      1. Substitua .db_salt por .db_salt_nova
      2. Mude DB_ENCRYPTION_KEY para o valor de DB_ENCRYPTION_KEY_NOVA
      3. Reinicie o servidor
    """
    print("\n── ROTAÇÃO DE CHAVE ──────────────────────────────────────────────")

    if not os.getenv("DB_ENCRYPTION_KEY_NOVA", "").strip():
        raise SystemExit(
            "[ERRO] Defina DB_ENCRYPTION_KEY_NOVA no ambiente antes de rotacionar."
        )

    SALT_FILE_NOVA = os.path.join(BASE_DIR, ".db_salt_nova")

    fernet_ant = _derivar_fernet("DB_ENCRYPTION_KEY",      SALT_FILE,      criar_salt=False)
    fernet_nov = _derivar_fernet("DB_ENCRYPTION_KEY_NOVA", SALT_FILE_NOVA, criar_salt=True)

    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    def _recifrar(tabela, coluna, chave_pk):
        c.execute(f"SELECT {chave_pk}, {coluna} FROM {tabela}")
        rows = c.fetchall()
        ok   = 0
        erro = 0
        for pk, valor in rows:
            if not valor:
                continue
            # Decifrar com chave antiga (ou usar texto plano legado)
            if _eh_cifrado(valor):
                texto = _decifrar_seguro(fernet_ant, valor)
                if texto is None:
                    print(f"  AVISO: {tabela}.{coluna} pk={pk} — falha ao decifrar, mantendo")
                    erro += 1
                    continue
            else:
                texto = valor  # texto plano legado

            novo = fernet_nov.encrypt(texto.encode()).decode()
            c.execute(f"UPDATE {tabela} SET {coluna} = ? WHERE {chave_pk} = ?", (novo, pk))
            ok += 1

        return ok, erro

    ok_h, err_h = _recifrar("historico",     "mensagem", "id")
    ok_i, err_i = _recifrar("identificacao", "nome",     "session_id")

    conn.commit()
    conn.close()

    print(f"\n  historico.mensagem   — {ok_h} re-cifrados, {err_h} erros")
    print(f"  identificacao.nome   — {ok_i} re-cifrados, {err_i} erros")
    print(f"\n  Novo salt salvo em: {SALT_FILE_NOVA}")
    print(
        "\n  Para finalizar a rotação:"
        "\n    1. Pare o servidor"
        "\n    2. Substitua .db_salt por .db_salt_nova"
        "\n    3. Mude DB_ENCRYPTION_KEY para o valor de DB_ENCRYPTION_KEY_NOVA"
        "\n    4. Remova DB_ENCRYPTION_KEY_NOVA do .env"
        "\n    5. Reinicie o servidor"
    )


# ── Entry point ───────────────────────────────────────────────────────────────

COMANDOS = {
    "migrar":    cmd_migrar,
    "verificar": cmd_verificar,
    "rotacionar": cmd_rotacionar,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMANDOS:
        print(__doc__)
        print(f"Comandos: {', '.join(COMANDOS)}")
        sys.exit(1)

    COMANDOS[sys.argv[1]]()
