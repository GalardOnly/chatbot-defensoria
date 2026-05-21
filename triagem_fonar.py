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
        "medida protetiva", "medidas protetivas", "defensoria", "separacao", "divorcio",
        "guarda dos filhos", "pensao", "processo",
    ]
    pedidos_convivencia_filhos = [
        "direito de ver meus filhos", "direito de ver meu filho",
        "direito de ver minha filha", "direito de ver minhas filhas",
        "direito a ver meus filhos", "posso ver meus filhos",
        "posso ver meu filho", "posso ver minha filha",
        "posso visitar meus filhos", "visitar meus filhos",
        "convivencia com meus filhos", "convivencia dos filhos",
        "guarda dos filhos", "visita aos filhos", "direito de visita",
        "direito a convivencia", "meus direitos com meus filhos",
    ]
    marcadores_direitos_filhos = [
        "direito", "direitos", "meus direitos", "perante",
        "em relacao", "em relação", "sobre", "guarda", "convivencia",
        "convivência", "visita", "visitas", "pensao", "pensão",
    ]
    pedidos_bo_online = [
        "boletim de ocorrencia eletronico", "boletim eletronico",
        "bo eletronico", "bo online", "b.o eletronico", "b.o. eletronico",
        "delegacia eletronica", "como funciona o boletim",
        "como funciona o bo", "registrar bo online", "fazer bo online",
    ]
    pedidos_medida_protetiva = [
        "medida protetiva", "medidas protetivas", "protetiva",
        "protetivas", "quais medidas", "que medidas eu posso",
        "medida de protecao", "medidas de protecao",
    ]
    pedidos_plano_seguranca = [
        "vier atras de mim", "vir atras de mim", "ir atras de mim",
        "for atras de mim", "vier me procurar", "vir me procurar",
        "me procurar", "me perseguir", "me seguir", "for na minha casa",
        "aparecer na minha casa", "ele vier", "ele vir",
    ]
    pedidos_orientacao_contextual = [
        "direitos", "meus direitos", "quais sao meus direitos",
        "quais sao os meus direitos", "posso conversar", "posso falar",
        "o que eu faco", "o que posso fazer", "como proceder",
        "me orienta", "orientacao", "informacoes", "preciso de informacoes",
    ]
    pedidos_lei_contextual = [
        "lei fala", "a lei fala", "o que a lei fala", "oque a lei fala",
        "entender o que a lei", "entender oque a lei", "pela lei",
        "legalmente", "lei diz", "a lei diz", "o que a lei diz",
        "meus direitos sobre isso", "direitos sobre isso",
    ]
    identidade_genero_trans = [
        "sou trans", "ser trans", "pessoa trans", "pessoas trans",
        "mulher trans", "homem trans", "transgenero", "transgênero",
        "transexual", "travesti", "nome social", "lgbt", "lgbtqia",
        "identidade de genero", "identidade de gênero",
    ]
    direitos_lgbtqia = [
        "tenho direitos", "meus direitos", "quais sao meus direitos",
        "quais sao os meus direitos", "nome social", "discriminacao",
        "discrimina", "preconceito", "transfobia", "lgbtfobia",
    ]
    violencias_transfobicas = [
        "nome antigo", "nome de registro", "nome morto", "deadname",
        "nome errado", "me chama pelo nome errado", "me chama pelo nome antigo",
        "usa meu nome antigo", "usa meu nome de registro",
        "me trata como homem", "me trata como mulher",
        "nao e mulher de verdade", "nao e homem de verdade",
        "ser trans e doenca", "ser trans é doença",
        "travesti nao e mulher", "travesti não é mulher",
        "minha identidade", "minha transicao", "minha transição",
    ]
    invalidacao_genero = [
        "nao sou mulher de verdade", "não sou mulher de verdade",
        "nao e mulher de verdade", "não é mulher de verdade",
        "nao sou homem de verdade", "não sou homem de verdade",
        "nao e homem de verdade", "não é homem de verdade",
        "mulher de verdade", "homem de verdade",
    ]
    invisibilizacao_identidade = [
        "nao me assume", "não me assume", "me esconde",
        "nao reconhece minha identidade", "não reconhece minha identidade",
        "nao respeita minha identidade", "não respeita minha identidade",
        "nao respeita meu genero", "não respeita meu gênero",
    ]
    negacao_direitos_genero = [
        "nao tenho os mesmos direitos", "nao tenho os mesmo direitos",
        "nao tenho direitos", "sem direitos", "menos direitos",
        "direitos das mulheres", "nao sou mulher", "nao e mulher",
        "nao e uma mulher", "nao tenho os direitos das mulheres",
    ]
    sem_abrigo = [
        "nao tenho para onde ir", "nao tenho onde ficar", "sem lugar para ir",
        "sem lugar para ficar", "estou sem casa", "preciso de abrigo",
        "preciso de acolhimento", "onde posso ficar", "para onde eu vou",
    ]
    filhos_comigo = [
        "tenho filhos comigo", "meus filhos estao comigo", "minhas filhas estao comigo",
        "estou com meus filhos", "estou com minhas filhas", "criancas comigo",
        "meu filho esta comigo", "minha filha esta comigo",
    ]
    termos_filhos = [
        "filhos", "filhas", "criancas", "crianca", "meu filho", "minha filha",
        "minhas criancas", "meus filhos", "minhas filhas",
    ]
    relacao_intima = [
        "marido", "companheiro", "namorado", "ex marido", "ex-marido",
        "meu ex", "meu esposo", "esposo", "ele sempre", "ele me",
    ]
    controle_domestico_ambiguo = [
        "escuro", "janela", "nao abre", "nunca abre", "ficar em casa",
        "me deixa no escuro", "no escuro", "me prende", "trancada em casa",
        "devo limpar", "tenho que limpar", "limpar a casa sozinha",
        "limpar toda a casa", "homem da casa",
    ]
    controle_sobre_filhos = [
        "nao me deixa ver meus filhos", "nao me deixar ver meus filhos",
        "nao deixa eu ver meus filhos", "nao deixa ver meus filhos",
        "nao me deixa ver meu filho", "nao me deixa ver minha filha",
        "nao me deixa ver minhas filhas", "me impede de ver meus filhos",
        "impede de ver meus filhos", "impede eu de ver meus filhos",
        "proibe eu de ver meus filhos", "proibiu eu de ver meus filhos",
        "proibe ver meus filhos", "afasta meus filhos de mim",
        "tirou meus filhos de mim", "quer tirar meus filhos de mim",
        "ameaca tirar meus filhos", "ameacou tirar meus filhos",
        "usa meus filhos contra mim", "usa as criancas contra mim",
        "usa as criancas para me controlar",
    ]
    restricao_liberdade = [
        "ficar trancada", "devo ficar trancada", "mandou ficar trancada",
        "manda eu ficar em casa", "nao deixa eu sair", "proibe sair",
        "proibiu sair", "me impede de sair", "me prende em casa",
        "me deixando trancada", "me deixa trancada", "deixando trancada",
        "trancada em casa", "sem ver a luz do sol", "nao me deixa pegar o celular",
        "nao deixa pegar o celular", "ficar presa em casa",
        "devo ficar presa em casa", "mandou ficar presa em casa",
        "me deixa presa em casa", "me deixando presa em casa",
        "deixando presa em casa", "tranca o portao", "tranca o portao de casa",
        "trancou o portao", "trancou o portao de casa", "fecha o portao",
        "fecha o portao de casa", "portao trancado",
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
        "fui agredida", "fui agredido", "agredida", "agredido",
        "agressao", "soco", "chute", "empurrou", "tapa", "espancou",
        "enforcou", "estrangulou", "machucou",
    ]
    psicologicas = [
        "me humilha", "humilha", "me xinga", "xinga", "me controla",
        "controla", "me isola", "nao deixa eu sair", "ciume", "ameaca",
        "ameacou", "chantagem", "medo dele",
    ]
    ameacas_carcere = [
        "vai me prender", "vai me trancar", "ameaca me prender",
        "ameacou me prender", "se eu nao obedecer ele vai me prender",
        "se eu nao obedecer vai me prender",
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
        "medo de morrer", "tenho medo de morrer", "risco de morrer",
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
        "me trancou", "estou presa em casa", "to presa em casa",
        "estou presa dentro de casa", "nao consigo sair", "socorro",
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
    ameaca_agressao_terceiros = [
        "vai bater", "vai machucar", "vai agredir", "ameacou bater",
        "ameacou machucar", "ameaca bater", "ameaca machucar",
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
    if _tem(t, ameacas_carcere):
        tipos.append("psicologica")
        sinais.append("ameaca_carcere")
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
    if _tem(t, pedidos_bo_online):
        sinais.append("pedido_bo_online")
        sinais.append("pedido_orientacao")
    if _tem(t, pedidos_medida_protetiva):
        sinais.append("pedido_medida_protetiva")
        sinais.append("pedido_orientacao")
    if _tem(t, pedidos_plano_seguranca):
        sinais.append("perseguicao_ou_retorno_agressor")
        sinais.append("pedido_orientacao")
    if _tem(t, pedidos_convivencia_filhos) or (
        _tem(t, termos_filhos)
        and _tem(t, ["direito de ver", "direito a ver", "direito de visita", "posso ver", "posso visitar", "convivencia"])
    ) or (
        _tem(t, termos_filhos)
        and _tem(t, marcadores_direitos_filhos)
    ):
        sinais.append("pedido_convivencia_filhos")
        sinais.append("pedido_orientacao")
    if _tem(t, pedidos_orientacao):
        sinais.append("pedido_orientacao")
    if _tem(t, identidade_genero_trans):
        sinais.append("identidade_genero_trans")
        if _tem(t, direitos_lgbtqia) or _tem(t, negacao_direitos_genero):
            sinais.append("direitos_lgbtqia")
        if _tem(t, direitos_lgbtqia):
            sinais.append("pedido_orientacao")
        if _tem(t, violencias_transfobicas) or _tem(t, invalidacao_genero) or _tem(t, invisibilizacao_identidade):
            tipos.append("psicologica")
            sinais.append("direitos_lgbtqia")
            sinais.append("violencia_psicologica")
            sinais.append("violencia_psicologica_transfobica")
    if _tem(t, invalidacao_genero):
        tipos.append("psicologica")
        sinais.append("invalidacao_genero")
        sinais.append("violencia_psicologica")
    if (
        _tem(t, identidade_genero_trans)
        and _tem(t, relacao_intima)
        and _tem(t, negacao_direitos_genero)
    ):
        tipos.append("psicologica")
        sinais.append("identidade_genero_trans")
        sinais.append("direitos_lgbtqia")
        sinais.append("negacao_direitos_por_genero")
        sinais.append("violencia_psicologica")
    if _tem(t, sem_abrigo):
        sinais.append("sem_abrigo")
        sinais.append("pedido_orientacao")
    if _tem(t, filhos_comigo):
        sinais.append("filhos_comigo")
    if _tem(t, termos_filhos) and _tem(t, ameaca_agressao_terceiros):
        tipos.append("fisica")
        tipos.append("psicologica")
        sinais.append("filhos_comigo")
        sinais.append("ameaca_contra_filhos")
        sinais.append("violencia_psicologica")
    if _tem(t, controle_sobre_filhos) or (
        _tem(t, relacao_intima)
        and _tem(t, termos_filhos)
        and _tem(t, ["nao me deixa ver", "nao me deixar ver", "nao deixa eu ver", "me impede de ver", "impede de ver"])
    ):
        tipos.append("psicologica")
        sinais.append("controle_sobre_filhos")
        sinais.append("violencia_psicologica")
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
        or _tem(historico_usuaria, controle_sobre_filhos)
        or _tem(historico_usuaria, invalidacao_genero)
        or _tem(historico_usuaria, invisibilizacao_identidade)
        or (
            _tem(historico_usuaria, relacao_intima)
            and _tem(historico_usuaria, controle_domestico_ambiguo)
        )
    )
    historico_tem_contexto_trans = bool(historico_usuaria) and (
        _tem(historico_usuaria, identidade_genero_trans)
        or _tem(historico_usuaria, direitos_lgbtqia)
        or _tem(historico_usuaria, negacao_direitos_genero)
        or _tem(historico_usuaria, violencias_transfobicas)
        or _tem(historico_usuaria, invalidacao_genero)
        or _tem(historico_usuaria, invisibilizacao_identidade)
    )

    if historico_tem_contexto_trans and (_tem(t, invalidacao_genero) or _tem(t, invisibilizacao_identidade)):
        tipos.append("psicologica")
        sinais.append("identidade_genero_trans")
        sinais.append("direitos_lgbtqia")
        sinais.append("violencia_psicologica")
        sinais.append("violencia_psicologica_transfobica")

    if _tem(t, pedidos_lei_contextual) and (historico_tem_abuso_ou_controle or historico_tem_contexto_trans):
        sinais.append("pedido_orientacao")
        sinais.append("pedido_orientacao_com_contexto")
        sinais.append("pedido_lei_contextual")
        if historico_tem_contexto_trans:
            sinais.append("identidade_genero_trans")
            sinais.append("direitos_lgbtqia")

    if _tem(t, pedidos_orientacao_contextual) and historico_tem_abuso_ou_controle:
        sinais.append("pedido_orientacao")
        sinais.append("pedido_orientacao_com_contexto")
    if "pedido_convivencia_filhos" in sinais and historico_tem_abuso_ou_controle:
        sinais.append("pedido_orientacao_com_contexto")
    if _tem(t, pedidos_orientacao_contextual) and historico_tem_contexto_trans:
        sinais.append("pedido_orientacao")
        sinais.append("pedido_orientacao_com_contexto")
        sinais.append("identidade_genero_trans")
        sinais.append("direitos_lgbtqia")

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
        or (
            "agressor_presente" in sinais
            and not _tem(t, ["ele vai chegar", "quando chegar", "quando voltar"])
        )
        or "falsa_segura" in sinais
        or "ameaca_morte" in sinais
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

    if "pedido_bo_online" in sinais:
        return _resultado(
            nivel=NIVEL_ORIENTACAO,
            risco_imediato=False,
            tipos_violencia=tipos,
            sinais_fonar=sinais,
            acao_resposta="orientar_bo_online",
        )

    if "pedido_medida_protetiva" in sinais:
        return _resultado(
            nivel=NIVEL_ORIENTACAO,
            risco_imediato=False,
            tipos_violencia=tipos,
            sinais_fonar=sinais,
            acao_resposta="orientar_medida_protetiva",
        )

    if "perseguicao_ou_retorno_agressor" in sinais:
        return _resultado(
            nivel=NIVEL_ORIENTACAO,
            risco_imediato=False,
            tipos_violencia=tipos,
            sinais_fonar=sinais,
            acao_resposta="orientar_plano_seguranca",
        )

    if "pedido_convivencia_filhos" in sinais:
        return _resultado(
            nivel=NIVEL_ORIENTACAO,
            risco_imediato=False,
            tipos_violencia=tipos,
            sinais_fonar=sinais,
            acao_resposta="orientar_convivencia_filhos",
        )

    if "pedido_lei_contextual" in sinais:
        return _resultado(
            nivel=NIVEL_ORIENTACAO,
            risco_imediato=False,
            tipos_violencia=tipos,
            sinais_fonar=sinais,
            acao_resposta="orientar_direitos_contextuais",
        )

    if "filhos_comigo" in sinais:
        return _resultado(
            nivel=NIVEL_MODERADO,
            risco_imediato=False,
            tipos_violencia=tipos,
            sinais_fonar=sinais,
            acao_resposta="acolher_e_perguntar_seguranca",
        )

    if "violencia_psicologica_transfobica" in sinais:
        return _resultado(
            nivel=NIVEL_VIOLENCIA,
            risco_imediato=False,
            tipos_violencia=tipos or ["psicologica"],
            sinais_fonar=sinais,
            acao_resposta="acolher_e_perguntar_seguranca",
        )

    if "negacao_direitos_por_genero" in sinais:
        return _resultado(
            nivel=NIVEL_VIOLENCIA,
            risco_imediato=False,
            tipos_violencia=tipos or ["psicologica"],
            sinais_fonar=sinais,
            acao_resposta="acolher_e_perguntar_seguranca",
        )

    if "direitos_lgbtqia" in sinais:
        return _resultado(
            nivel=NIVEL_ORIENTACAO,
            risco_imediato=False,
            tipos_violencia=tipos,
            sinais_fonar=sinais,
            acao_resposta="orientar_direitos_lgbtqia",
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
        "estou trancada", "me trancou", "estou presa em casa",
        "to presa em casa", "estou presa dentro de casa", "nao consigo sair",
    ])
    ameaca_morte = _tem(t, [
        "vai me matar", "disse que vai me matar", "ameacou me matar",
        "ameaca de morte", "matar amanha", "matar hoje",
        "tenho medo de morrer", "medo de morrer", "risco de morrer",
    ])

    return (
        perigo_declarado
        or comunicacao_insegura
        or agressor_presente
        or (arma and agressor_presente)
        or ameaca_morte
    )


def triagem_indica_modo_real(triagem: dict) -> bool:
    nivel = triagem.get("nivel")
    if nivel in {NIVEL_AMBIGUA, NIVEL_ORIENTACAO, NIVEL_VIOLENCIA, NIVEL_MODERADO, NIVEL_GRAVE, NIVEL_EXTREMO}:
        return True
    return False


def historico_indica_modo_real(historico: list[dict] | None) -> bool:
    """
    Decide se a sessao ja entrou em contexto sensivel usando metadados salvos.

    O classificador RF pode estar ausente ou nao reconhecer um relato sutil. Nesses
    casos, os campos FONAR gravados no banco precisam preservar o estado real da
    conversa para que uma saudacao ou termo domestico nao devolva o bot a fachada.
    """
    sinais_reais = {
        "possivel_controle_domestico",
        "restricao_liberdade",
        "restricao_ou_comunicacao_insegura",
        "violencia_psicologica",
        "agressao_fisica",
        "ameaca_carcere",
        "ameaca_morte",
        "controle_familiar",
        "exposicao_sem_consentimento",
        "violencia_sexual",
        "violencia_patrimonial",
        "identidade_genero_trans",
        "direitos_lgbtqia",
        "negacao_direitos_por_genero",
        "invalidacao_genero",
        "violencia_psicologica_transfobica",
        "controle_sobre_filhos",
        "pedido_convivencia_filhos",
        "pedido_lei_contextual",
    }
    niveis_reais = {
        NIVEL_ORIENTACAO,
        NIVEL_VIOLENCIA,
        NIVEL_MODERADO,
        NIVEL_GRAVE,
        NIVEL_EXTREMO,
    }

    for msg in historico or []:
        if msg.get("role") != "user":
            continue
        tipo_violencia = msg.get("tipo_violencia")
        if tipo_violencia and tipo_violencia != "nao_violencia":
            return True
        if msg.get("risco_imediato"):
            return True
        if msg.get("nivel_risco") in niveis_reais:
            return True
        if set(msg.get("sinais_fonar") or []) & sinais_reais:
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
            "Nao repita literalmente a fala da usuaria; acolha pelo significado "
            "do relato em uma frase curta, valide a experiencia, diga que nao e culpa dela e faca uma pergunta "
            "contextual de seguranca. Nao entregue lista de contatos neste primeiro acolhimento."
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
