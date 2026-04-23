import os
import time
import chromadb
from groq import Groq
from google import genai
from google.genai import types
from docx import Document
from dotenv import load_dotenv

#VARIÁVEIS DE AMBIENTE 
load_dotenv()

#ESTRUTURAS DE DADOS
tipos_violencia = [
    {"tipo": "Violência física", "exemplo": "Agressão, empurrão, tapa, soco, chute."},
    {"tipo": "Violência psicológica", "exemplo": "Ameaças, humilhações, xingamentos, isolamento."},
    {"tipo": "Violência sexual", "exemplo": "Forçar relação sexual, impedir uso de contraceptivos."},
    {"tipo": "Violência patrimonial", "exemplo": "Destruir objetos, controlar dinheiro, reter documentos."},
    {"tipo": "Violência moral", "exemplo": "Calúnia, difamação, injúria."}
]

crimes_correspondentes = [
    {"artigo": "Art. 129, §9º do CP", "descricao": "Lesão corporal no contexto de violência doméstica."},
    {"artigo": "Art. 147 do CP", "descricao": "Ameaça: intimidar alguém com promessa de mal injusto."},
    {"artigo": "Art. 140 do CP", "descricao": "Injúria: ofender a dignidade ou decoro."},
    {"artigo": "Art. 163 do CP", "descricao": "Dano: destruir ou inutilizar coisa alheia."}
]

fluxo_medida_protetiva = [
    "Registro de ocorrência na delegacia ou Defensoria.",
    "Pedido de medida protetiva é encaminhado ao juiz.",
    "Juiz pode conceder medida em até 48h.",
    "Polícia e órgãos competentes são comunicados para garantir proteção."
]

direitos_por_situacao = {
    "vítima de violência": [
        "Solicitar medida protetiva.",
        "Atendimento psicológico e social.",
        "Acesso à Defensoria Pública para orientação jurídica.",
        "Prioridade em programas sociais."
    ]
}

defensoria_contatos = {
    "Belém": {"endereco": "Rua XYZ, nº 123", "telefone": "(91) 1234-5678"},
    "Ananindeua": {"endereco": "Av. ABC, nº 456", "telefone": "(91) 2345-6789"}
}


# CLASSE EMBEDDING SERVICE
class EmbeddingService:
    def __init__(self, api_key=None, model="gemini-embedding-001",
                 task_type="retrieval_document", batch_size=8, delay=2):
        if api_key is None:
            api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.task_type = task_type
        self.batch_size = batch_size
        self.delay = delay

    def embed(self, texts, task_type=None):
        embeddings = []
        effective_task_type = task_type if task_type is not None else self.task_type
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            response = self.client.models.embed_content(
                model=self.model,
                contents=batch,
                config=types.EmbedContentConfig(task_type=effective_task_type)
            )
            for emb in response.embeddings:
                embeddings.append(emb.values)
            time.sleep(self.delay)
        return embeddings


# FUNÇÕES UTILITÁRIAS 
def chunk_text(text, max_tokens=500):
    # Dividir o texto em parágrafos
    paragrafos = [p.strip() for p in text.split('\n') if p.strip()]
    chunks = []
    chunk_atual = []
    tokens_atual = 0
    overlap = 50  # número de palavras de overlap
    palavras_chunk_anterior = []
    for paragrafo in paragrafos:
        # Identifica título de seção: curto (<80), não termina com ponto
        eh_titulo = len(paragrafo) < 80 and not paragrafo.endswith('.')
        if eh_titulo:
            # Se já existe conteúdo acumulado, fecha o chunk antes do novo título
            if chunk_atual:
                chunk_texto = ' '.join(chunk_atual)
                chunks.append(chunk_texto)
                # Preparar overlap para próximo chunk
                palavras_chunk_anterior = chunk_texto.split()[-overlap:] if overlap > 0 else []
                chunk_atual = []
                tokens_atual = 0
            chunk_atual = [paragrafo]
            tokens_atual = len(paragrafo.split())
        else:
            palavras = paragrafo.split()
            if tokens_atual + len(palavras) > max_tokens and chunk_atual:
                chunk_texto = ' '.join(chunk_atual)
                chunks.append(chunk_texto)
                # Preparar overlap para próximo chunk
                palavras_chunk_anterior = chunk_texto.split()[-overlap:] if overlap > 0 else []
                # Iniciar novo chunk com overlap
                chunk_atual = [' '.join(palavras_chunk_anterior)] if palavras_chunk_anterior else []
                tokens_atual = len(palavras_chunk_anterior)
            chunk_atual.append(paragrafo)
            tokens_atual += len(palavras)
    if chunk_atual:
        chunk_texto = ' '.join(chunk_atual)
        chunks.append(chunk_texto)
    return chunks


def armazenar_chunks_com_embeddings(chunks, embeddings, colecao):
    existentes = colecao.get()["ids"]
    novos_chunks, novos_embeddings, novos_ids = [], [], []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        id_ = f"chunk_{i}"
        if id_ not in existentes:
            novos_chunks.append(chunk)
            novos_embeddings.append(emb)
            novos_ids.append(id_)
    if novos_ids:
        colecao.add(documents=novos_chunks, embeddings=novos_embeddings, ids=novos_ids)
        print(f"{len(novos_ids)} chunks novos armazenados.")
    else:
        print("Dados já existem no banco. Nenhum chunk novo inserido.")


def buscar_chunks_relevantes(pergunta, embedding_service, colecao, n_results=3):
    embedding = embedding_service.embed([pergunta], task_type="retrieval_query")[0]
    resultado = colecao.query(query_embeddings=[embedding], n_results=n_results)
    return resultado["documents"][0] if "documents" in resultado else []



# SYSTEM PROMPTS 
system_prompt_real = (
    """
Você é a Bruna, uma assistente da Defensoria Pública do Pará. Você não é um advogado robótico,
 mas uma profissional de acolhimento que entende que a violência psicológica ataca a identidade da mulher e que a violência moral destrói sua rede de apoio.

Seu papel é orientar mulheres em situação de violência doméstica e familiar 
de forma acolhedora, clara e acessível, sem usar linguagem jurídica complexa.

DIRETRIZES DE COMPORTAMENTO:
- Use linguagem simples, direta e humana. Evite termos técnicos sem explicação.
- Seja BREVE. Máximo 3 parágrafos curtos. Priorize a informação mais urgente primeiro.
- Nunca escreva listas longas. Uma resposta ideal tem no máximo 5 linhas.
- Se houver risco imediato, a primeira frase deve ser o número 190.
- Demonstre empatia. A pessoa pode estar em situação de risco ou trauma.
- Nunca minimize ou questione o relato da usuária.
- Nunca repita o número 190 ou 180 mais de uma vez por conversa.
- Quando a pessoa mencionar uma cidade, busque informações específicas dessa cidade no contexto.
- Converse de forma natural, como uma assistente social faria — não como um manual jurídico.
- Faça uma pergunta por vez para entender melhor a situação antes de dar orientações.
- Responda a pergunta específica da usuária sem recomeçar do zero a cada mensagem.
- Cite artigos da Lei Maria da Penha apenas quando ajudar a esclarecer direitos.
- Se não souber a resposta, diga claramente e oriente a buscar a Defensoria.

CANAIS DE EMERGÊNCIA QUE VOCÊ DEVE SEMPRE LEMBRAR:
- Ligue 180 (Central de Atendimento à Mulher, gratuito e sigiloso)
- Ligue 190 (Polícia Militar, emergências)
- Defensoria Pública do Pará: (91) 3181-6181

LIMITES:
- Não forneça aconselhamento médico ou psicológico clínico.
- Não prometa resultados jurídicos específicos.
- Não emita opiniões sobre o agressor ou sobre decisões pessoais da usuária.
- Se a situação parecer de risco imediato, priorize orientar a ligar 190.
"""
)

system_prompt_fachada = (
    """
Você é um assistente virtual simpático e informal, especializado em dar dicas para o lar, decoração, organização doméstica, economia doméstica e pequenos serviços em casa.

Responda sempre de forma leve, amigável e acessível, como se estivesse conversando com um amigo. Use exemplos práticos, sugestões criativas e incentive o bem-estar no ambiente doméstico. Não responda dúvidas jurídicas, de violência ou temas sensíveis: apenas dicas para o dia a dia do lar, organização, limpeza, decoração, receitas simples, economia de recursos e manutenção doméstica.

Se a pergunta fugir desses temas, oriente gentilmente a buscar um profissional especializado.
"""
)


# FUNÇÃO PRINCIPAL DE RESPOSTA

def responder_pergunta(pergunta, embedding_service, colecao, client, modo):
    contexto = buscar_chunks_relevantes(pergunta, embedding_service, colecao)
    contexto_str = "\n".join(contexto)
    if modo == 'real':
        prompt = (
            f"{system_prompt_real}\n\n"
            f"Contexto extraído do documento:\n{contexto_str}\n\n"
            f"Pergunta: {pergunta}\n\n"
            f"Resposta:"
        )
    else:
        prompt = (
            f"{system_prompt_fachada}\n\n"
            f"Pergunta: {pergunta}\n\n"
            f"Resposta:"
        )
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content


# PONTO DE ENTRADA
if __name__ == "__main__":

    # 1. Ler o documento (parágrafos e tabelas)
    caminho_arquivo = "Guia Completo.docx"
    documento = Document(caminho_arquivo)
    textos = [p.text for p in documento.paragraphs if p.text.strip()]
    # Extrair texto das tabelas
    for tabela in documento.tables:
        for linha in tabela.rows:
            for celula in linha.cells:
                texto_celula = celula.text.strip()
                if texto_celula:
                    textos.append(texto_celula)
    texto = "\n".join(textos)

    # 2. Chunking
    chunks = chunk_text(texto, max_tokens=800)
    print(f"{len(chunks)} chunks gerados.")

    # 3. Inicializar ChromaDB
    chroma_client = chromadb.PersistentClient(path="chroma_db")
    colecao = chroma_client.get_or_create_collection("documentos_juridicos")

    # 4. Instanciar cliente e EmbeddingService
    api_key = os.getenv("GEMINI_API_KEY")
    embedding_service = EmbeddingService(api_key=api_key)

    # 5. Gerar e armazenar embeddings
    embeddings = embedding_service.embed(chunks)
    armazenar_chunks_com_embeddings(chunks, embeddings, colecao)

    # 6. Loop de chat
    print("\nChatbot pronto! Digite 'sair' para encerrar.\n")
    while True:
        pergunta = input("Você: ").strip()
        if pergunta.lower() == "sair":
            print("Encerrando o chatbot.")
            break
        if not pergunta:
            continue
        try:
            resposta = responder_pergunta(pergunta, embedding_service, colecao, client=None, modo='real')
            print(f"\nAssistente: {resposta}\n")
        except Exception as e:
            print(f"ERRO REAL: {e}")
            # Importação local para evitar erro se não houver ClientError
            try:
                from google.api_core.exceptions import ClientError
            except ImportError:
                ClientError = None
            # Verifica se é ClientError 429
            if ClientError is not None and isinstance(e, ClientError) and hasattr(e, 'code') and e.code == 429:
                print('Serviço temporariamente indisponível. Tente novamente em alguns minutos.')
            elif hasattr(e, 'code') and getattr(e, 'code', None) == 429:
                print('Serviço temporariamente indisponível. Tente novamente em alguns minutos.')
            else:
                print('Ocorreu um erro inesperado. Tente novamente.')
