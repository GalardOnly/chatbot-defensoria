import os
import time
import pickle
import numpy as np
import torch
import chromadb
from groq import Groq
from google import genai
from google.genai import types
from docx import Document
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModel

#VARIÁVEIS DE AMBIENTE
load_dotenv()

#ESTRUTURAS DE DADOS
tipos_violencia = [
    {"tipo": "Violência física",      "exemplo": "Agressão, empurrão, tapa, soco, chute."},
    {"tipo": "Violência psicológica", "exemplo": "Ameaças, humilhações, xingamentos, isolamento."},
    {"tipo": "Violência sexual",      "exemplo": "Forçar relação sexual, impedir uso de contraceptivos."},
    {"tipo": "Violência patrimonial", "exemplo": "Destruir objetos, controlar dinheiro, reter documentos."},
    {"tipo": "Violência moral",       "exemplo": "Calúnia, difamação, injúria."},
]

crimes_correspondentes = [
    {"artigo": "Art. 129, §9º do CP", "descricao": "Lesão corporal no contexto de violência doméstica."},
    {"artigo": "Art. 147 do CP",      "descricao": "Ameaça: intimidar alguém com promessa de mal injusto."},
    {"artigo": "Art. 140 do CP",      "descricao": "Injúria: ofender a dignidade ou decoro."},
    {"artigo": "Art. 163 do CP",      "descricao": "Dano: destruir ou inutilizar coisa alheia."},
]

fluxo_medida_protetiva = [
    "Registro de ocorrência na delegacia ou Defensoria.",
    "Pedido de medida protetiva é encaminhado ao juiz.",
    "Juiz pode conceder medida em até 48h.",
    "Polícia e órgãos competentes são comunicados para garantir proteção.",
]

direitos_por_situacao = {
    "vítima de violência": [
        "Solicitar medida protetiva.",
        "Atendimento psicológico e social.",
        "Acesso à Defensoria Pública para orientação jurídica.",
        "Prioridade em programas sociais.",
    ]
}

defensoria_contatos = {
    "Belém":       {"endereco": "Rua XYZ, nº 123", "telefone": "(91) 1234-5678"},
    "Ananindeua":  {"endereco": "Av. ABC, nº 456",  "telefone": "(91) 2345-6789"},
}


#PRÉ-CLASSIFICADOR (BERT + Random Forest)
# Ponto de atenção 1: BERT carregado uma única vez (singleton via init_services)
# Ponto de atenção 4: torch.inference_mode() no lugar de torch.no_grad()
# Ponto de atenção 3: classe nao_violencia configurável

class ClassificadorViolencia:
    """
    Wrapper em torno dos modelos treinados (rf_tipo + rf_gravidade) e do BERT
    português. Deve ser instanciado UMA VEZ e reutilizado (como EmbeddingService).

    Parâmetros
    ----------
    pasta_modelos : str
        Caminho para a pasta que contém rf_tipo.pkl e rf_gravidade.pkl.
    classe_neutra : str
        Nome da classe que representa ausência de violência no seu dataset.
        Padrão: "nao_violencia". Ajuste se usou outro nome (ex: "neutro").
    limiar_confianca : float
        Confiança mínima (0–1) para considerar a classificação válida.
        Abaixo disso, eh_violencia retorna False para evitar falsos positivos
        de baixa confiança forçarem o modo real.
    """

    MODEL_BERT = "neuralmind/bert-base-portuguese-cased"

    def __init__(
        self,
        pasta_modelos: str = "modelos",
        classe_neutra: str = "nao_violencia",
        limiar_confianca: float = 0.60,
    ):
        self.classe_neutra     = classe_neutra
        self.limiar_confianca  = limiar_confianca

        print("  [Classificador] Carregando BERT português...")
        self.tokenizer = AutoTokenizer.from_pretrained(self.MODEL_BERT)
        self.bert      = AutoModel.from_pretrained(self.MODEL_BERT)
        self.device    = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.bert      = self.bert.to(self.device)
        self.bert.eval()
        print(f"  [Classificador] BERT pronto — dispositivo: {self.device}")

        print("  [Classificador] Carregando Random Forests...")
        with open(f"{pasta_modelos}/rf_tipo.pkl", "rb") as f:
            self.rf_tipo = pickle.load(f)
        with open(f"{pasta_modelos}/rf_gravidade.pkl", "rb") as f:
            self.rf_gravidade = pickle.load(f)
        print("  [Classificador] Modelos prontos.")

    # Ponto de atenção 4: inference_mode (mais rápido que no_grad)
    def _embedding(self, texto: str) -> np.ndarray:
        encoded = self.tokenizer(
            texto,
            padding=True,
            truncation=True,
            max_length=128,
            return_tensors="pt",
        ).to(self.device)

        with torch.inference_mode():          # ← ganho de performance vs no_grad
            out = self.bert(**encoded)

        return out.last_hidden_state[:, 0, :].cpu().numpy()

    def classificar(self, texto: str) -> dict:
        """
        Retorna um dicionário com:
          tipo           – ex: "Violência física"
          gravidade      – ex: "alta"
          tipo_prob      – confiança 0-1 da predição de tipo
          gravidade_prob – confiança 0-1 da predição de gravidade
          eh_violencia   – True quando tipo != classe_neutra E prob >= limiar
          confianca_ok   – True quando tipo_prob >= limiar_confianca
        """
        emb = self._embedding(texto)

        tipo       = self.rf_tipo.predict(emb)[0]
        tipo_prob  = float(self.rf_tipo.predict_proba(emb).max())

        gravidade      = self.rf_gravidade.predict(emb)[0]
        grav_prob      = float(self.rf_gravidade.predict_proba(emb).max())

        # Ponto de atenção 3: classe neutra configurável 
        confianca_ok  = tipo_prob >= self.limiar_confianca
        eh_violencia  = (tipo != self.classe_neutra) and confianca_ok

        return {
            "tipo":           tipo,
            "gravidade":      gravidade,
            "tipo_prob":      round(tipo_prob, 4),
            "gravidade_prob": round(grav_prob, 4),
            "eh_violencia":   eh_violencia,
            "confianca_ok":   confianca_ok,
        }


#EMBEDDING SERVICE (Gemini) 
class EmbeddingService:
    def __init__(self, api_key=None, model="gemini-embedding-001"):
        if api_key is None:
            api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key)
        self.model  = model

    def embed(self, texts, task_type="retrieval_document"):
        embeddings = []
        batch_size = 90
        print(f"Iniciando geração de embeddings para {len(texts)} chunks...")

        for i in range(0, len(texts), batch_size):
            lote_atual = texts[i:i + batch_size]
            print(f"Processando lote {i // batch_size + 1} ({len(lote_atual)} chunks)...")
            try:
                response = self.client.models.embed_content(
                    model=self.model,
                    contents=lote_atual,
                    config=types.EmbedContentConfig(task_type=task_type),
                )
                for emb in response.embeddings:
                    embeddings.append(emb.values)
                if i + batch_size < len(texts):
                    time.sleep(2)
            except Exception as e:
                print(f"Erro no lote {i // batch_size + 1}: {e}")
                raise e

        print(f"Sucesso! {len(embeddings)} embeddings gerados.")
        return embeddings


#FUNÇÕES UTILITÁRIAS
def chunk_text(text, max_tokens=500):
    paragrafos   = [p.strip() for p in text.split("\n") if p.strip()]
    chunks       = []
    chunk_atual  = []
    tokens_atual = 0
    overlap      = 50
    palavras_chunk_anterior = []

    for paragrafo in paragrafos:
        eh_titulo = len(paragrafo) < 80 and not paragrafo.endswith(".")
        if eh_titulo:
            if chunk_atual:
                chunk_texto = " ".join(chunk_atual)
                chunks.append(chunk_texto)
                palavras_chunk_anterior = chunk_texto.split()[-overlap:] if overlap > 0 else []
                chunk_atual  = []
                tokens_atual = 0
            chunk_atual  = [paragrafo]
            tokens_atual = len(paragrafo.split())
        else:
            palavras = paragrafo.split()
            if tokens_atual + len(palavras) > max_tokens and chunk_atual:
                chunk_texto = " ".join(chunk_atual)
                chunks.append(chunk_texto)
                palavras_chunk_anterior = chunk_texto.split()[-overlap:] if overlap > 0 else []
                chunk_atual  = ([" ".join(palavras_chunk_anterior)] if palavras_chunk_anterior else [])
                tokens_atual = len(palavras_chunk_anterior)
            chunk_atual.append(paragrafo)
            tokens_atual += len(palavras)

    if chunk_atual:
        chunks.append(" ".join(chunk_atual))
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


# ── SYSTEM PROMPTS ───────────────────────────────────────────────────────────
system_prompt_real = """
Você é a Bruna, uma assistente da Defensoria Pública do Pará. Você não é um advogado robótico,
mas uma profissional de acolhimento que entende que a violência psicológica ataca a identidade
da mulher e que a violência moral destrói sua rede de apoio.

Seu papel é orientar mulheres em situação de violência doméstica e familiar de forma acolhedora,
clara e acessível, sem usar linguagem jurídica complexa.

DIRETRIZES DE COMPORTAMENTO:
- Use linguagem simples, direta e humana. Evite termos técnicos sem explicação.
- Seja BREVE. Máximo 3 parágrafos curtos. Priorize a informação mais urgente primeiro.
- Nunca escreva listas longas. Uma resposta ideal tem no máximo 5 linhas.
- Nunca repita o número 190 ou 180 mais de uma vez por conversa.
- Se houver risco imediato, a primeira frase deve ser o número 190.
- Demonstre empatia. A pessoa pode estar em situação de risco ou trauma.
- Nunca minimize ou questione o relato da usuária.
- Quando a pessoa mencionar uma cidade, busque informações específicas dessa cidade no contexto.
- Converse de forma natural, como uma assistente social faria — não como um manual jurídico.
- Faça uma pergunta por vez para entender melhor a situação antes de dar orientações.
- Responda a pergunta específica da usuária sem recomeçar do zero a cada mensagem.
- Cite artigos da Lei Maria da Penha apenas quando ajudar a esclarecer direitos.
- Se não souber a resposta, diga claramente e oriente a buscar a Defensoria.

CANAIS DE EMERGÊNCIA:
- Ligue 180 (Central de Atendimento à Mulher, gratuito e sigiloso)
- Ligue 190 (Polícia Militar, emergências)
- Defensoria Pública do Pará: (91) 3181-6181

LIMITES:
- Não forneça aconselhamento médico ou psicológico clínico.
- Não prometa resultados jurídicos específicos.
- Não emita opiniões sobre o agressor ou sobre decisões pessoais da usuária.
- Se a situação parecer de risco imediato, priorize orientar a ligar 190.
"""

system_prompt_fachada = """
Você é um assistente virtual simpático e informal, especializado em dicas para o lar, decoração,
organização doméstica, economia doméstica e pequenos serviços em casa.

Responda sempre de forma leve, amigável e acessível, como se estivesse conversando com um amigo.
Use exemplos práticos, sugestões criativas e incentive o bem-estar no ambiente doméstico.
Não responda dúvidas jurídicas, de violência ou temas sensíveis: apenas dicas para o dia a dia
do lar, organização, limpeza, decoração, receitas simples, economia de recursos e manutenção.

Se a pergunta fugir desses temas, oriente gentilmente a buscar um profissional especializado.
"""


#FUNÇÃO PRINCIPAL DE RESPOSTA
def responder_pergunta(
    pergunta,
    embedding_service,
    colecao,
    historico=[],
    modo="real",
    classificacao=None,   # ← recebe o resultado do pré-classificador
):
    contexto     = buscar_chunks_relevantes(pergunta, embedding_service, colecao)
    contexto_str = "\n".join(contexto)

    system_prompt = system_prompt_real if modo == "real" else system_prompt_fachada

    # Injeta a pré-classificação como contexto interno para a LLM
    # (o modelo usa essa info para calibrar tom e urgência, sem expor ao usuário)
    prefixo_classificacao = ""
    if classificacao and classificacao["eh_violencia"]:
        prefixo_classificacao = (
            f"[ANÁLISE AUTOMÁTICA — tipo detectado: {classificacao['tipo']} | "
            f"gravidade: {classificacao['gravidade']} | "
            f"confiança: {classificacao['tipo_prob']:.0%}]\n"
            f"Use essa informação para calibrar tom e urgência da resposta. "
            f"Não mencione essa análise à usuária.\n\n"
        )

    messages = [{"role": "system", "content": system_prompt}]
    for msg in historico[-5:]:
        messages.append(msg)

    prompt_final = (
        f"{prefixo_classificacao}"
        f"Contexto base: {contexto_str}\n\n"
        f"Pergunta atual: {pergunta}"
    )
    messages.append({"role": "user", "content": prompt_final})

    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response    = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.6,
        max_tokens=600,
    )
    return response.choices[0].message.content


#PONTO DE ENTRADA (teste local) 
if __name__ == "__main__":
    caminho_arquivo = "Guia Completo.docx"
    documento = Document(caminho_arquivo)
    textos = [p.text for p in documento.paragraphs if p.text.strip()]
    for tabela in documento.tables:
        for linha in tabela.rows:
            for celula in linha.cells:
                texto_celula = celula.text.strip()
                if texto_celula:
                    textos.append(texto_celula)
    texto = "\n".join(textos)

    chunks = chunk_text(texto, max_tokens=800)
    print(f"{len(chunks)} chunks gerados.")

    chroma_client = chromadb.PersistentClient(path="chroma_db")
    colecao = chroma_client.get_or_create_collection("documentos_juridicos")

    api_key          = os.getenv("GEMINI_API_KEY")
    embedding_service = EmbeddingService(api_key=api_key)

    embeddings = embedding_service.embed(chunks)
    armazenar_chunks_com_embeddings(chunks, embeddings, colecao)

    # Instancia o classificador se os modelos existirem
    classificador = None
    if os.path.exists("modelos/rf_tipo.pkl"):
        classificador = ClassificadorViolencia()

    print("\nChatbot pronto! Digite 'sair' para encerrar.\n")
    while True:
        pergunta = input("Você: ").strip()
        if pergunta.lower() == "sair":
            print("Encerrando o chatbot.")
            break
        if not pergunta:
            continue
        try:
            classificacao = classificador.classificar(pergunta) if classificador else None
            resposta = responder_pergunta(
                pergunta, embedding_service, colecao,
                modo="real", classificacao=classificacao
            )
            print(f"\nAssistente: {resposta}\n")
        except Exception as e:
            print(f"ERRO: {e}")
            print("Ocorreu um erro inesperado. Tente novamente.")