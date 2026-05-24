from dotenv import load_dotenv
load_dotenv()

import os
from google import genai
from google.genai import types
from conteudo_chat import carregar_texto_documento, chunk_text

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Carrega e chunka exatamente como a Bruna faz
texto = carregar_texto_documento("Guia Completo.docx")
chunks = chunk_text(texto, max_tokens=280)
print(f"Total de chunks: {len(chunks)}\n")

# Análise rápida dos chunks
print("=== Análise dos chunks ===")
for i, c in enumerate(chunks):
    n_palavras = len(c.split())
    n_chars = len(c)
    if n_chars > 10000 or n_chars < 10 or n_palavras < 3:
        print(f"  ⚠ Chunk {i+1}: {n_chars} chars, {n_palavras} palavras")

# Testa o LOTE 1 REAL (primeiros 50 chunks do guia)
print("\n=== Testando lote 1 (chunks 1-50) ===")
try:
    resp = client.models.embed_content(
        model="gemini-embedding-001",
        contents=chunks[:50],
        config=types.EmbedContentConfig(task_type="retrieval_document"),
    )
    print(f"✅ Sucesso! {len(resp.embeddings)} embeddings")
except Exception as e:
    print(f"❌ Lote 1 falhou: {type(e).__name__}")
    print(f"Mensagem: {e}\n")
    
    # Bissecta para achar o chunk problemático
    print("=== Bisseccionando para encontrar o chunk problemático ===")
    
    def tenta(inicio, fim):
        try:
            client.models.embed_content(
                model="gemini-embedding-001",
                contents=chunks[inicio:fim],
                config=types.EmbedContentConfig(task_type="retrieval_document"),
            )
            return True
        except Exception:
            return False
    
    # Busca binária
    lo, hi = 0, 50
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if tenta(lo, mid):
            lo = mid
        else:
            hi = mid
    
    print(f"\nChunk problemático: índice {lo} (ou {lo+1} contando do 1)")
    print(f"Tamanho: {len(chunks[lo])} chars, {len(chunks[lo].split())} palavras")
    print(f"\nConteúdo do chunk:")
    print("─" * 60)
    print(chunks[lo])
    print("─" * 60)