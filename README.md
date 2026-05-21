# Chatbot Defensoria - MVP

MVP de chatbot de acolhimento inicial para mulheres e pessoas trans em situacao de vulnerabilidade, com fachada visual discreta, triagem de risco, encaminhamento para canais oficiais e cuidados de privacidade.

> Aviso importante: este chatbot e apenas apoio inicial. Ele nao substitui atendimento humano, psicologico, juridico, policial ou medico. Em risco imediato, ligue 190. Para orientacao sobre violencia contra a mulher, Ligue 180 quando for seguro.

## Como Rodar

1. Crie e ative o ambiente virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Instale as dependencias:

```powershell
pip install -r requirements.txt
```

3. Copie `.env.example` para `.env` e configure as variaveis.

4. Inicie a aplicacao:

```powershell
python app.py
```

5. Abra:

```text
http://127.0.0.1:5000
```

## Variaveis De Ambiente

- `GROQ_API_KEY`: chave da Groq usada para respostas LLM.
- `GEMINI_API_KEY`: chave Gemini usada para embeddings/RAG.
- `ADMIN_TOKEN`: token longo para acessar o painel administrativo.
- `DB_ENCRYPTION_KEY`: segredo usado para cifrar mensagens e identificacao no SQLite.
- `ALLOWED_ORIGIN`: origem permitida para CORS, como `http://localhost:5000`.
- `ENABLE_RAG_INDEXING`: use `true` apenas quando quiser reindexar a base de conhecimento.

Nunca versionar `.env`, `historico.db`, `.db_salt`, `chroma_db/` ou arquivos de modelo gerados.

## Testes

Rode a suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Para validar rapidamente o fluxo critico, teste as mensagens:

- `nao posso falar`
- `ele esta aqui`
- `tenho medo de morrer`
- `fui agredida`
- `tenho filhos comigo`
- `quero denunciar`
- `nao tenho para onde ir`
- `por eu ser trans, meu marido diz que eu nao tenho os mesmos direitos das mulheres`
- `sou homem trans e meu parceiro usa meu nome antigo para me humilhar`
- `eu possuo direito de ver meus filhos ?`

## Base Documental E Dataset

- `Guia Completo.docx` e a base usada pelo RAG. Depois de alterar esse arquivo, rode o deploy com `ENABLE_RAG_INDEXING=true` ao menos uma vez para reindexar o ChromaDB.
- `dataset_unificado.csv` e o dataset principal do classificador. Ele consolida exemplos de violencia contra mulheres, pessoas trans, stalking e mensagens de fachada.
- O treino usa TF-IDF + regressao logistica One-vs-Rest para tipo de violencia e TF-IDF + Random Forest para gravidade, mantendo limiar conservador para classe `alta`.
- Para atualizar o modelo local apos mudar datasets:

```powershell
.\.venv\Scripts\python.exe treinar_modelo.py
```

## Controles De Seguranca Da Usuaria

- Saida rapida para outro site.
- Botao para apagar conversa.
- Sessao publica com token de exclusao.
- Mensagens e nome opcional cifrados no banco.
- Redacao de PII antes de envio a provedores externos.
- Sanitizacao de prompt injection.
- Fallback deterministico para risco imediato.
- Aviso claro de limitacao do chatbot.

## Roteiro Seguro De Demonstracao

1. Abra a tela inicial e explique a fachada discreta.
2. Leia o aviso de limitacao: apoio inicial, nao substitui atendimento humano.
3. Envie `oi` para mostrar modo fachada.
4. Envie `ele controla meu dinheiro e nao deixa trabalhar` para demonstrar acolhimento.
5. Envie `quero denunciar` para mostrar canais oficiais, Ligue 180, BO e medida protetiva.
6. Envie `nao posso falar` para mostrar resposta curta, discreta e com 190/180.
7. Mostre `Apagar` para excluir a conversa.
8. Mostre `Sair` para saida rapida.

Evite usar dados reais de nome, telefone, endereco, localizacao ou relatos privados durante a demo.

## Prontidao Para Banca

Este MVP deve ser apresentado como prototipo de apoio inicial e triagem, nao como servico autonomo de emergencia. A demonstracao deve reforcar que decisoes juridicas, medicas, policiais e psicologicas exigem atendimento profissional.
