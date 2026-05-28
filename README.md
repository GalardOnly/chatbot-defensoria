# Manuela — Chatbot de Apoio Psicossocial

Sistema de triagem e acolhimento inicial para mulheres e pessoas trans em situação de vulnerabilidade, com fachada visual discreta, classificador NLP de risco e encaminhamento para canais oficiais.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Flask](https://img.shields.io/badge/Flask-3.0-lightgrey) ![ChromaDB](https://img.shields.io/badge/ChromaDB-RAG-orange) ![Groq](https://img.shields.io/badge/LLM-Llama%203.3%2070B-purple) ![scikit--learn](https://img.shields.io/badge/scikit--learn-TF--IDF%20%2B%20RF-yellow) ![License](https://img.shields.io/badge/license-MIT-green)

🔗 **Aplicação no ar:** https://chatbot-defensoria.onrender.com/
📄 **Documentação completa:** [`docs/`](./docs)

> ⚠️ **Aviso ético**: este chatbot é apenas apoio inicial. Não substitui atendimento humano, psicológico, jurídico, policial ou médico. Em risco imediato, ligue **190**. Para orientação sobre violência contra a mulher, **Ligue 180** quando for seguro.

---

## Demonstração

A interface se apresenta como um chatbot de dicas domésticas. A transição para o modo de acolhimento acontece automaticamente quando o sistema detecta sinais de violência ou risco — sem que a usuária precise saber que existe um "modo escondido".

![Demonstração: relato sutil de violência psicológica em interface de fachada, reconhecido e acolhido pelo sistema](./docs/demo.png)

---

## O Problema

A maior parte das vítimas de violência doméstica não busca ajuda formal. Os motivos vão desde medo de retaliação até a presença do agressor no mesmo ambiente onde a vítima usaria o celular ou o computador. Canais públicos como o Ligue 180 dependem da vítima conseguir realizar uma ligação telefônica — frequentemente impossível.

Existe uma lacuna entre o momento em que a vítima reconhece a situação e o momento em que ela acessa um canal oficial. Esse projeto explora um caminho discreto para preencher essa lacuna: uma interface que **parece outra coisa**, mas que pode reconhecer relatos de violência psicológica, física, patrimonial, sexual, stalking ou violência institucional contra mulheres e pessoas trans, oferecendo acolhimento inicial e direcionando para canais oficiais.

O projeto foi motivado pelo contexto da Defensoria Pública e nasceu como exploração de viabilidade técnica para esse tipo de ferramenta de triagem.

---

## A Solução

Um chatbot web com **duplo modo de operação**:

1. **Modo fachada** — responde a perguntas sobre limpeza, organização e economia doméstica. É o que a usuária vê ao abrir o sistema.
2. **Modo acolhimento** — ativado automaticamente quando o classificador NLP detecta sinais de risco no que a usuária escreve. Oferece escuta, informações sobre direitos, e encaminhamento para canais oficiais (Ligue 180, BO online, medida protetiva).

A transição é silenciosa do ponto de vista da interface (sem botões, sem avisos), mantendo a discrição que protege a usuária caso o agressor esteja olhando a tela.

### Arquitetura

```
┌─────────────────┐     ┌──────────────────────────────────┐
│    Frontend     │────▶│           Flask Backend          │
│  (HTML/JS puro) │     │                                  │
└─────────────────┘     │  ┌────────────────────────────┐  │
                        │  │  Classificador NLP         │  │
                        │  │  TF-IDF + LogReg (tipo)    │  │
                        │  │  TF-IDF + RF (gravidade)   │  │
                        │  └────────────────────────────┘  │
                        │              │                   │
                        │              ▼                   │
                        │  ┌────────────────────────────┐  │
                        │  │  Roteador de modo          │  │
                        │  │  (fachada ↔ acolhimento)   │  │
                        │  └────────────────────────────┘  │
                        │              │                   │
                        │     ┌────────┴────────┐          │
                        │     ▼                 ▼          │
                        │  ┌────────┐      ┌─────────┐     │
                        │  │ ChromaDB│ ──▶ │  Groq   │     │
                        │  │  (RAG)  │     │ Llama   │     │
                        │  └────────┘      │ 3.3 70B │     │
                        │     ▲            └─────────┘     │
                        │     │  embeddings: Gemini        │
                        │     │                            │
                        │  ┌────────────────────────────┐  │
                        │  │  SQLite cifrado            │  │
                        │  │  (histórico + PII redacted)│  │
                        │  └────────────────────────────┘  │
                        └──────────────────────────────────┘
                                       │
                                       ▼
                              ┌────────────────┐
                              │  Render.com    │
                              │  (512MB RAM)   │
                              └────────────────┘
```

---

## Stack Técnica

| Camada | Tecnologia | Justificativa |
|---|---|---|
| Backend | Flask | Footprint pequeno cabe no plano free do Render (512MB) |
| LLM | Groq + Llama 3.3 70B | Latência baixíssima, free tier viável |
| Embeddings | Google Gemini (`gemini-embedding-001`) | Free tier generoso para projeto educacional |
| Vector store | ChromaDB | Embarcada no app, sem servidor adicional |
| Classificador | scikit-learn (TF-IDF + LogReg + RF) | Migração estratégica de BERT por restrição de memória |
| Persistência | SQLite com mensagens criptografadas | Sem dependência de banco externo |
| Servidor WSGI | gunicorn | Padrão de produção para Flask |
| Frontend | HTML + JS puro | Sem build pipeline, deploy direto |
| Hosting | Render (backend) + Netlify (frontend) | Free tier |
| Monitoramento | UptimeRobot pinging `/health` | Evita sleep do free tier do Render |

---

## Decisões Técnicas Notáveis

**Migração BERT → TF-IDF + scikit-learn**
A versão inicial do classificador usava embeddings BERT. Funcionava bem em desenvolvimento mas estourava o limite de 512MB de RAM do plano free do Render. A migração para um pipeline TF-IDF + Random Forest / Regressão Logística reduziu o footprint em ordem de magnitude, mantendo ~85% de acurácia. **Lição:** modelo certo é o que cabe no orçamento de infra disponível.

**Lógica conservadora na classificação de gravidade**
Em casos ambíguos, o classificador foi calibrado para errar do lado seguro — preferindo classificar como sinal de distress real do que ignorar. Em sistemas de apoio psicossocial, falso negativo custa muito mais que falso positivo. O limiar da classe `alta` foi mantido propositalmente conservador.

**Fachada visual como decisão de produto**
A fachada de "Dicas de Casa Fortaleza" não é gimmick — é parte da função de segurança. Se a usuária precisa fechar o app rapidamente ou se alguém olhar a tela por cima do ombro, a aparência genérica protege.

**Fallback determinístico para risco imediato**
Para gatilhos críticos (mensagens indicando risco de morte, presença do agressor, impossibilidade de falar), o sistema **não consulta a LLM** — usa respostas pré-escritas, rápidas e seguras, com os números 190 e 180 em destaque. LLM é ótima, mas em emergência, latência e previsibilidade importam mais que sofisticação.

**Criptografia das mensagens no SQLite**
Mensagens e nome opcional são cifrados em repouso usando uma chave (`DB_ENCRYPTION_KEY`) fora do código. Mesmo em vazamento do banco, o conteúdo permanece protegido. Há também redação de PII antes do envio para provedores externos (Groq/Gemini) e sanitização de prompt injection.

---

## Modelo de Classificação

- **Dataset**: 2.000 exemplos sintéticos cobrindo 6 tipos de violência (psicológica, física, patrimonial, sexual, stalking, institucional) em 3 níveis de gravidade (baixa, média, alta), incluindo violência contra mulheres trans e homens trans
- **Pipeline tipo de violência**: TF-IDF + Regressão Logística One-vs-Rest
- **Pipeline gravidade**: TF-IDF + Random Forest, com limiar conservador para classe `alta`
- **Acurácia agregada**: ~85% nos testes
- **Cobertura regional**: dataset inclui variações de vocabulário e expressões regionais brasileiras
- **Reproducibilidade**: treino completo via `python treinar_modelo.py`

---

## Como Rodar

1. Crie e ative o ambiente virtual:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1     # Windows
source .venv/bin/activate         # Linux/Mac
```

2. Instale as dependências:

```bash
pip install -r requirements.txt
```

3. Copie `.env.example` para `.env` e configure as variáveis.

4. Inicie a aplicação:

```bash
python app.py
```

5. Abra: http://127.0.0.1:5000

---

## Variáveis de Ambiente

| Variável | Descrição |
|---|---|
| `GROQ_API_KEY` | Chave da Groq usada para respostas LLM |
| `GEMINI_API_KEY` | Chave Gemini usada para embeddings/RAG |
| `ADMIN_TOKEN` | Token longo para acessar o painel administrativo |
| `DB_ENCRYPTION_KEY` | Segredo para cifrar mensagens e identificação no SQLite |
| `ALLOWED_ORIGIN` | Origem permitida para CORS (ex: `http://localhost:5000`) |
| `ENABLE_RAG_INDEXING` | Use `true` apenas quando quiser reindexar a base de conhecimento |

> Nunca versionar `.env`, `historico.db`, `.db_salt`, `chroma_db/` ou arquivos de modelo gerados. Verifique o `.gitignore`.

---

## Testes

Suíte de testes via `unittest`:

```bash
python -m unittest discover -s tests -v
```

Para validar rapidamente o fluxo crítico, teste as mensagens:

- `nao posso falar`
- `ele esta aqui`
- `tenho medo de morrer`
- `fui agredida`
- `tenho filhos comigo`
- `quero denunciar`
- `nao tenho para onde ir`
- `por eu ser trans, meu marido diz que eu nao tenho os mesmos direitos das mulheres`
- `sou homem trans e meu parceiro usa meu nome antigo para me humilhar`
- `eu possuo direito de ver meus filhos?`

---

## Controles de Segurança da Usuária

- **Saída rápida** para outro site
- **Botão para apagar conversa** com confirmação
- **Sessão pública** com token de exclusão
- **Mensagens e nome opcional cifrados** no banco
- **Redação de PII** antes de envio a provedores externos
- **Sanitização de prompt injection**
- **Fallback determinístico** para risco imediato
- **Aviso claro de limitação** do chatbot

---

## Roteiro Seguro de Demonstração

1. Abrir a tela inicial e mostrar a fachada discreta
2. Ler o aviso de limitação
3. Enviar `oi` para demonstrar modo fachada
4. Enviar `meu marido as vezes diz que eu estou gorda` para demonstrar o reconhecimento de violência psicológica em um relato sutil
5. Enviar `quero denunciar` para mostrar canais oficiais (Ligue 180, BO, medida protetiva)
6. Enviar `nao posso falar` para mostrar resposta curta e discreta com 190/180
7. Mostrar botão `Apagar` para excluir conversa
8. Mostrar botão `Sair` para saída rápida

> Evite usar dados reais de nome, telefone, endereço, localização ou relatos privados durante demos.

---

## Base Documental e Dataset

- `Guia Completo.docx` — base usada pelo RAG. Após alterar, rodar deploy com `ENABLE_RAG_INDEXING=true` ao menos uma vez para reindexar o ChromaDB.
- `dataset_unificado.csv` — dataset principal do classificador. Consolida exemplos de violência contra mulheres, pessoas trans, stalking e mensagens de fachada.

Atualizar o modelo local após mudar datasets:

```bash
python treinar_modelo.py
```

---

## Estrutura do Repositório

```
chatbot-defensoria/
├── app.py                    # Ponto de entrada Flask
├── conteudo_chat.py          # Roteador de modo e respostas
├── triagem_fonar.py          # Lógica de triagem por risco
├── treinar_modelo.py         # Treinamento do classificador
├── gerenciar_cripto.py       # Funções de criptografia do SQLite
├── debug.py                  # Utilitários de depuração
├── index.html                # Frontend principal
├── painel.html               # Painel administrativo
├── render.yaml               # Configuração de deploy no Render
├── requirements.txt          # Dependências Python
├── dataset_unificado.csv     # Dataset de treino do classificador
├── Guia Completo.docx        # Base de conhecimento do RAG
├── docs/                     # Documentação técnica adicional
├── tests/                    # Testes unitários
└── tools/                    # Scripts auxiliares
```

---

## Limitações Conhecidas

- **Cobertura do classificador**: 6 tipos × 3 níveis treinados. Casos fora dessa taxonomia podem ser mal classificados.
- **Dependência de free tier**: rate limits do Groq e Gemini podem causar latência em horários de pico. UptimeRobot mitiga sleep mas não rate limit.
- **Frontend simples**: HTML/JS puro sem framework. Suficiente pro MVP, mas não escalável para customizações avançadas.
- **Sem autenticação por usuária**: sessões públicas com token de exclusão. Adequado para um chatbot de triagem anônima, mas não para fluxos que exijam continuidade entre dispositivos.
- **Apresentação como protótipo**: este sistema é um MVP de exploração técnica, não um serviço público em operação. Decisões jurídicas, médicas, policiais e psicológicas exigem atendimento profissional humano.

---

## Roadmap

- [ ] Expandir dataset com colaboração de profissionais da área
- [ ] Implementar painel administrativo com métricas de uso agregadas e anônimas
- [ ] Avaliar migração para banco gerenciado conforme adoção cresce
- [ ] Internacionalização (espanhol como próximo idioma)

---

## Autor

**Gabriel Costuchenco**
Estudante de Ciência de Dados — FATEC Ourinhos (conclusão Dez/2026)

- 💼 [LinkedIn](https://www.linkedin.com/in/gabriel-costuchenco-656492282/)
- 📧 gabrielolivcos8@gmail.com
- 🐙 [GitHub](https://github.com/GalardOnly)

