import re
import unicodedata


NIVEL_FACHADA = "fachada"
NIVEL_AMBIGUA = "ambigua"
NIVEL_ORIENTACAO = "pedido_orientacao"
NIVEL_VIOLENCIA = "violencia_sem_risco_imediato"
NIVEL_MODERADO = "risco_moderado"
NIVEL_GRAVE = "risco_grave"
NIVEL_EXTREMO = "risco_extremo"


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto or "")
    texto = "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")
    texto = texto.lower()
    return re.sub(r"\s+", " ", texto).strip()


def _tem(texto: str, padroes: list[str]) -> bool:
    return any(padrao in texto for padrao in padroes)


def _resultado(
    *,
    nivel: str,
    risco_imediato: bool,
    tipos_violencia: list[str] | None = None,
    sinais_fonar: list[str] | None = None,
    acao_resposta: str,
) -> dict:
    return {
        "nivel": nivel,
        "risco_imediato": risco_imediato,
        "tipos_violencia": sorted(set(tipos_violencia or [])),
        "sinais_fonar": sorted(set(sinais_fonar or [])),
        "acao_resposta": acao_resposta,
    }


def avaliar_triagem_fonar(texto: str, historico: list[dict] | None = None) -> dict:
    """
    Triagem inspirada nos fatores do FONAR para calibrar resposta e estatisticas.

    Nao substitui a aplicacao oficial do FONAR por profissional habilitado. No chat,
    esta camada serve para separar acolhimento, orientacao e emergencia imediata.
    """
    t = _normalizar(texto)
    historico = historico or []
    historico_usuaria = " ".join(
        _normalizar(msg.get("content") or msg.get("mensagem") or "")
        for msg in historico[-8:]
        if msg.get("role") == "user"
    )

    if not t:
        return _resultado(
            nivel=NIVEL_AMBIGUA,
            risco_imediato=False,
            acao_resposta="acolher_e_investigar",
        )

    if t in {"oi", "ola", "bom dia", "boa tarde", "boa noite"}:
        return _resultado(
            nivel=NIVEL_FACHADA,
            risco_imediato=False,
            acao_resposta="fachada",
        )

    tipos: list[str] = []
    sinais: list[str] = []

    sinais_fachada = [
        "sofa", "mancha", "limpeza", "organizacao", "casa", "lar",
        "fogao", "geladeira", "roupa", "jardim", "detergente", "sabao",
        "decoracao", "economia domestica", "quintal", "varrer",
    ]
    pedidos_ajuda = [
        "preciso de ajuda", "nao sei o que fazer", "me ajuda",
        "pode me ajudar", "estou com medo", "tenho medo",
    ]
    pedidos_orientacao = [
        "denunciar", "denuncia", "boletim de ocorrencia", "b.o", "bo ",
        "medida protetiva", "defensoria", "separacao", "divorcio",
        "guarda dos filhos", "pensao", "processo",
    ]
    pedidos_orientacao_contextual = [
        "direitos", "meus direitos", "quais sao meus direitos",
        "quais sao os meus direitos", "posso conversar", "posso falar",
        "o que eu faco", "o que posso fazer", "como proceder",
        "me orienta", "orientacao", "informacoes", "preciso de informacoes",
    ]
    relacao_intima = [
        "marido", "companheiro", "namorado", "ex marido", "ex-marido",
        "meu ex", "meu esposo", "esposo", "ele sempre", "ele me",
    ]
    controle_domestico_ambiguo = [
        "escuro", "janela", "nao abre", "nunca abre", "ficar em casa",
        "me deixa no escuro", "no escuro", "me prende", "trancada em casa",
    ]
    restricao_liberdade = [
        "ficar trancada", "devo ficar trancada", "mandou ficar trancada",
        "manda eu ficar em casa", "nao deixa eu sair", "proibe sair",
        "proibiu sair", "me impede de sair", "me prende em casa",
        "me deixando trancada", "me deixa trancada", "deixando trancada",
        "trancada em casa", "sem ver a luz do sol", "nao me deixa pegar o celular",
        "nao deixa pegar o celular",
    ]

    digitais = [
        "expoe", "expor", "exposicao", "redes sociais", "postar", "postou",
        "publicou", "foto intima", "fotos intimas", "nude", "nudes",
        "sem meu consentimento", "sem consentimento", "invadiu meu celular",
        "mexeu no meu celular", "pegou minha senha", "senha",
        "whatsapp", "instagram", "facebook", "stalking", "persegue online",
    ]
    fisicas = [
        "me bate", "me bateu", "me batendo", "me agride", "me agrediu",
        "agressao", "soco", "chute", "empurrou", "tapa", "espancou",
        "enforcou", "estrangulou", "machucou",
    ]
    psicologicas = [
        "me humilha", "humilha", "me xinga", "xinga", "me controla",
        "controla", "me isola", "nao deixa eu sair", "ciume", "ameaca",
        "ameacou", "chantagem", "medo dele",
    ]
    sexuais = [
        "estupro", "abusou sexualmente", "me obriga a transar",
        "obriga sexo", "sexo sem consentimento", "me toca sem consentimento",
    ]
    patrimoniais = [
        "pegou meu dinheiro", "controla meu dinheiro", "quebrou minhas coisas",
        "rasgou meus documentos", "tomou meus documentos", "nao deixa trabalhar",
    ]
    ameaca_morte = [
        "vai me matar", "disse que vai me matar", "ameacou me matar",
        "ameaca de morte", "matar amanha", "matar hoje", "me matar",
    ]
    armas = [
        "arma", "faca", "revolver", "pistola", "espingarda", "facao",
        "canivete",
    ]
    agressor_presente = [
        "ele esta aqui", "ele ta aqui", "ele esta perto", "ele ta perto",
        "ele pode ouvir", "esta me ouvindo", "no outro quarto", "no banho",
        "ele chegou", "ele vai chegar", "quando chegar", "quando voltar",
    ]
    carcere_ou_silencio = [
        "nao posso falar", "nao posso digitar", "estou trancada",
        "me trancou", "presa em casa", "nao consigo sair", "socorro",
    ]
    perigo_declarado = [
        "estou em perigo", "perigo agora", "risco agora", "risco imediato",
        "urgente", "risco de vida",
    ]
    seguranca_negada = [
        "nao estou em risco", "estou segura", "estou bem agora",
        "hoje estou segura", "agora estou segura",
    ]
    futuro_perigoso = [
        "amanha", "mais tarde", "quando voltar", "quando chegar",
        "vai me matar", "ameaca", "ameacou", "me procurar",
    ]

    if _tem(t, digitais):
        tipos.append("digital")
        sinais.append("exposicao_sem_consentimento")
    if _tem(t, fisicas):
        tipos.append("fisica")
        sinais.append("agressao_fisica")
    if _tem(t, psicologicas):
        tipos.append("psicologica")
        sinais.append("violencia_psicologica")
    if _tem(t, restricao_liberdade):
        tipos.append("psicologica")
        sinais.append("restricao_liberdade")
        sinais.append("violencia_psicologica")
    if _tem(t, sexuais):
        tipos.append("sexual")
        sinais.append("violencia_sexual")
    if _tem(t, patrimoniais):
        tipos.append("patrimonial")
        sinais.append("violencia_patrimonial")
    if _tem(t, ameaca_morte):
        tipos.append("ameaca")
        sinais.append("ameaca_morte")
    if _tem(t, armas):
        sinais.append("arma")
    if _tem(t, agressor_presente):
        sinais.append("agressor_presente")
    if _tem(t, carcere_ou_silencio):
        sinais.append("restricao_ou_comunicacao_insegura")
    if _tem(t, seguranca_negada) and _tem(t, futuro_perigoso):
        sinais.append("falsa_segura")
    if _tem(t, pedidos_orientacao):
        sinais.append("pedido_orientacao")
    if _tem(t, relacao_intima) and _tem(t, controle_domestico_ambiguo):
        sinais.append("possivel_controle_domestico")

    historico_tem_abuso_ou_controle = bool(historico_usuaria) and (
        _tem(historico_usuaria, digitais)
        or _tem(historico_usuaria, fisicas)
        or _tem(historico_usuaria, psicologicas)
        or _tem(historico_usuaria, sexuais)
        or _tem(historico_usuaria, patrimoniais)
        or _tem(historico_usuaria, ameaca_morte)
        or _tem(historico_usuaria, restricao_liberdade)
        or (
            _tem(historico_usuaria, relacao_intima)
            and _tem(historico_usuaria, controle_domestico_ambiguo)
        )
    )
    if _tem(t, pedidos_orientacao_contextual) and historico_tem_abuso_ou_controle:
        sinais.append("pedido_orientacao")
        sinais.append("pedido_orientacao_com_contexto")

    if "arma" in sinais and (
        "agressor_presente" in sinais or "ameaca_morte" in sinais or _tem(t, perigo_declarado)
    ):
        return _resultado(
            nivel=NIVEL_EXTREMO,
            risco_imediato=True,
            tipos_violencia=tipos or ["ameaca"],
            sinais_fonar=sinais,
            acao_resposta="emergencia_imediata",
        )

    if (
        _tem(t, perigo_declarado)
        or "restricao_ou_comunicacao_insegura" in sinais
        or "falsa_segura" in sinais
        or ("ameaca_morte" in sinais and _tem(t, futuro_perigoso + agressor_presente))
    ):
        return _resultado(
            nivel=NIVEL_GRAVE,
            risco_imediato=True,
            tipos_violencia=tipos or ["ameaca"],
            sinais_fonar=sinais,
            acao_resposta="emergencia_imediata",
        )

    if "agressor_presente" in sinais and tipos:
        return _resultado(
            nivel=NIVEL_MODERADO,
            risco_imediato=False,
            tipos_violencia=tipos,
            sinais_fonar=sinais,
            acao_resposta="acolher_com_discricao",
        )

    if "pedido_orientacao" in sinais:
        return _resultado(
            nivel=NIVEL_ORIENTACAO,
            risco_imediato=False,
            tipos_violencia=tipos,
            sinais_fonar=sinais,
            acao_resposta="orientar_com_passos",
        )

    if tipos:
        return _resultado(
            nivel=NIVEL_VIOLENCIA,
            risco_imediato=False,
            tipos_violencia=tipos,
            sinais_fonar=sinais,
            acao_resposta="acolher_e_perguntar_seguranca",
        )

    if "possivel_controle_domestico" in sinais:
        return _resultado(
            nivel=NIVEL_AMBIGUA,
            risco_imediato=False,
            sinais_fonar=sinais,
            acao_resposta="acolher_e_investigar",
        )

    if _tem(t, pedidos_ajuda):
        return _resultado(
            nivel=NIVEL_AMBIGUA,
            risco_imediato=False,
            sinais_fonar=["pedido_ajuda_ambiguo"],
            acao_resposta="acolher_e_investigar",
        )

    if _tem(t, sinais_fachada):
        return _resultado(
            nivel=NIVEL_FACHADA,
            risco_imediato=False,
            acao_resposta="fachada",
        )

    return _resultado(
        nivel=NIVEL_AMBIGUA,
        risco_imediato=False,
        acao_resposta="acolher_e_investigar",
    )


def avaliar_emergencia_obvia(texto: str) -> bool:
    """Cinto de seguranca local: apenas casos que nao podem esperar LLM."""
    t = _normalizar(texto)

    perigo_declarado = _tem(t, [
        "estou em perigo", "perigo agora", "risco agora", "risco imediato",
        "risco de vida", "socorro",
    ])
    arma = _tem(t, [
        "arma", "faca", "revolver", "pistola", "espingarda", "facao", "canivete",
    ])
    agressor_presente = _tem(t, [
        "ele esta aqui", "ele ta aqui", "ele esta perto", "ele ta perto",
        "ele pode ouvir", "esta me ouvindo", "ele chegou",
    ])
    comunicacao_insegura = _tem(t, [
        "nao posso falar", "nao posso digitar", "ele pode ouvir",
        "estou trancada", "me trancou", "presa em casa", "nao consigo sair",
    ])
    ameaca_morte = _tem(t, [
        "vai me matar", "disse que vai me matar", "ameacou me matar",
        "ameaca de morte", "matar amanha", "matar hoje",
    ])

    return (
        perigo_declarado
        or comunicacao_insegura
        or (arma and agressor_presente)
        or ameaca_morte
    )


def triagem_indica_modo_real(triagem: dict) -> bool:
    nivel = triagem.get("nivel")
    if nivel in {NIVEL_AMBIGUA, NIVEL_ORIENTACAO, NIVEL_VIOLENCIA, NIVEL_MODERADO, NIVEL_GRAVE, NIVEL_EXTREMO}:
        return True
    return False


def instrucao_llm_triagem(triagem: dict) -> str:
    nivel = triagem.get("nivel", NIVEL_AMBIGUA)
    tipos = ", ".join(triagem.get("tipos_violencia") or ["nao identificado"])
    sinais = ", ".join(triagem.get("sinais_fonar") or ["nenhum"])

    if triagem.get("risco_imediato"):
        prioridade = (
            "Prioridade: resposta curta de seguranca. Acolha em uma frase, "
            "oriente 190/180 e caminhos oficiais. Nao faca investigacao longa."
        )
    elif nivel == NIVEL_VIOLENCIA:
        prioridade = (
            "Prioridade: acolhimento antes de informacao. Nao abra com telefones. "
            "Valide a experiencia, diga que nao e culpa dela e pergunte se ela esta segura agora."
        )
    elif nivel == NIVEL_ORIENTACAO:
        prioridade = (
            "Prioridade: orientar com passos simples, mantendo tom acolhedor e sem pressionar denuncia."
        )
    elif nivel == NIVEL_AMBIGUA:
        prioridade = (
            "Prioridade: acolher e fazer uma pergunta curta para entender o que esta acontecendo."
        )
    else:
        prioridade = "Prioridade: manter modo fachada."

    return (
        "[TRIAGEM FONAR INTERNA - NAO DIVULGAR]\n"
        f"Nivel: {nivel}\n"
        f"Risco imediato: {bool(triagem.get('risco_imediato'))}\n"
        f"Tipos de violencia: {tipos}\n"
        f"Sinais observados: {sinais}\n"
        f"{prioridade}\n"
    )
