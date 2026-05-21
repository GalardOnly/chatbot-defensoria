import unittest

from triagem_fonar import (
    avaliar_triagem_fonar,
    avaliar_emergencia_obvia,
    historico_indica_modo_real,
    instrucao_llm_triagem,
)


class TriagemFonarTest(unittest.TestCase):
    def test_violencia_digital_sem_risco_imediato_acolhe_antes_de_emergencia(self):
        triagem = avaliar_triagem_fonar(
            "meu marido me expoe nas redes sociais sem meu consentimento"
        )

        self.assertEqual(triagem["nivel"], "violencia_sem_risco_imediato")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("digital", triagem["tipos_violencia"])
        self.assertIn("exposicao_sem_consentimento", triagem["sinais_fonar"])
        self.assertEqual(triagem["acao_resposta"], "acolher_e_perguntar_seguranca")

    def test_instrucao_llm_pede_acolhimento_sem_repeticao_literal(self):
        triagem = avaliar_triagem_fonar(
            "meu marido diz que eu devo ficar presa em casa"
        )

        instrucao = instrucao_llm_triagem(triagem).lower()

        self.assertIn("nao repita literalmente", instrucao)
        self.assertIn("significado", instrucao)
        self.assertIn("nao abra com telefones", instrucao)
        self.assertIn("uma pergunta", instrucao)

    def test_agressao_fisica_relato_sem_contexto_de_agora_nao_vira_extremo(self):
        triagem = avaliar_triagem_fonar("quando peco para ele nao postar ele me bate")

        self.assertEqual(triagem["nivel"], "violencia_sem_risco_imediato")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("fisica", triagem["tipos_violencia"])
        self.assertIn("agressao_fisica", triagem["sinais_fonar"])

    def test_arma_com_agressor_presente_vira_risco_extremo(self):
        triagem = avaliar_triagem_fonar("ele esta aqui com uma faca")

        self.assertEqual(triagem["nivel"], "risco_extremo")
        self.assertTrue(triagem["risco_imediato"])
        self.assertIn("arma", triagem["sinais_fonar"])
        self.assertIn("agressor_presente", triagem["sinais_fonar"])
        self.assertEqual(triagem["acao_resposta"], "emergencia_imediata")

    def test_falsa_segura_com_ameaca_futura_vira_risco_grave(self):
        triagem = avaliar_triagem_fonar(
            "nao estou em risco hoje, mas ele disse que vai me matar amanha"
        )

        self.assertEqual(triagem["nivel"], "risco_grave")
        self.assertTrue(triagem["risco_imediato"])
        self.assertIn("falsa_segura", triagem["sinais_fonar"])
        self.assertIn("ameaca_morte", triagem["sinais_fonar"])

    def test_pedido_generico_de_ajuda_fica_ambiguo(self):
        triagem = avaliar_triagem_fonar("preciso de ajuda, nao sei o que fazer")

        self.assertEqual(triagem["nivel"], "ambigua")
        self.assertFalse(triagem["risco_imediato"])
        self.assertEqual(triagem["acao_resposta"], "acolher_e_investigar")

    def test_fachada_continua_fachada(self):
        triagem = avaliar_triagem_fonar("como tirar mancha do sofa")

        self.assertEqual(triagem["nivel"], "fachada")
        self.assertFalse(triagem["risco_imediato"])
        self.assertEqual(triagem["tipos_violencia"], [])

    def test_contexto_de_marido_e_ambiente_nao_vira_fachada_por_conter_casa(self):
        triagem = avaliar_triagem_fonar(
            "meu marido nunca abre a janela de casa, sempre ficou no escuro"
        )

        self.assertEqual(triagem["nivel"], "ambigua")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("possivel_controle_domestico", triagem["sinais_fonar"])
        self.assertEqual(triagem["acao_resposta"], "acolher_e_investigar")

    def test_marido_impoe_limpeza_da_casa_nao_vira_fachada(self):
        triagem = avaliar_triagem_fonar(
            "meu marido diz que eu devo limpar a casa sozinha"
        )

        self.assertEqual(triagem["nivel"], "ambigua")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("possivel_controle_domestico", triagem["sinais_fonar"])

    def test_controle_para_ficar_trancada_em_casa_nao_vira_fachada(self):
        triagem = avaliar_triagem_fonar(
            "ele sempre me diz que eu devo ficar trancada em casa"
        )

        self.assertEqual(triagem["nivel"], "violencia_sem_risco_imediato")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("psicologica", triagem["tipos_violencia"])
        self.assertIn("restricao_liberdade", triagem["sinais_fonar"])

    def test_trancar_portao_para_impedir_saida_vira_restricao_liberdade(self):
        triagem = avaliar_triagem_fonar(
            "meu marido tranca o portao de casa quando sai"
        )

        self.assertEqual(triagem["nivel"], "violencia_sem_risco_imediato")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("psicologica", triagem["tipos_violencia"])
        self.assertIn("restricao_liberdade", triagem["sinais_fonar"])

    def test_ordem_para_ficar_presa_em_casa_nao_vira_emergencia_automatica(self):
        triagem = avaliar_triagem_fonar(
            "meu marido diz que eu devo ficar presa em casa"
        )

        self.assertEqual(triagem["nivel"], "violencia_sem_risco_imediato")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("psicologica", triagem["tipos_violencia"])
        self.assertIn("restricao_liberdade", triagem["sinais_fonar"])
        self.assertFalse(
            avaliar_emergencia_obvia("meu marido diz que eu devo ficar presa em casa")
        )

    def test_estou_presa_em_casa_agora_continua_emergencia(self):
        triagem = avaliar_triagem_fonar("estou presa em casa e nao consigo sair")

        self.assertEqual(triagem["nivel"], "risco_grave")
        self.assertTrue(triagem["risco_imediato"])
        self.assertIn("restricao_ou_comunicacao_insegura", triagem["sinais_fonar"])
        self.assertTrue(avaliar_emergencia_obvia("estou presa em casa e nao consigo sair"))

    def test_ameaca_de_prender_vira_violencia_psicologica_sem_emergencia_automatica(self):
        triagem = avaliar_triagem_fonar(
            "diz que se eu nao obedecer ele vai me prender"
        )

        self.assertEqual(triagem["nivel"], "violencia_sem_risco_imediato")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("psicologica", triagem["tipos_violencia"])
        self.assertIn("ameaca_carcere", triagem["sinais_fonar"])

    def test_controle_financeiro_vira_violencia_patrimonial(self):
        triagem = avaliar_triagem_fonar(
            "ele controla meu dinheiro e pegou meu cartao"
        )

        self.assertEqual(triagem["nivel"], "violencia_sem_risco_imediato")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("patrimonial", triagem["tipos_violencia"])

    def test_estado_da_sessao_usa_triagem_fonar_mesmo_sem_classificador_rf(self):
        historico = [
            {
                "role": "user",
                "mensagem": "meu marido diz que eu devo limpar a casa sozinha",
                "tipo_violencia": None,
                "nivel_risco": "ambigua",
                "risco_imediato": False,
                "tipos_violencia_fonar": [],
                "sinais_fonar": ["possivel_controle_domestico"],
            },
            {
                "role": "user",
                "mensagem": "boa noite",
                "tipo_violencia": None,
                "nivel_risco": "fachada",
                "risco_imediato": False,
                "tipos_violencia_fonar": [],
                "sinais_fonar": [],
            },
        ]

        self.assertTrue(historico_indica_modo_real(historico))

    def test_marido_deixando_trancada_sem_luz_vira_restricao_liberdade(self):
        triagem = avaliar_triagem_fonar(
            "boa noite, meu marido esta me deixando trancada em casa, sem ver a luz do sol"
        )

        self.assertEqual(triagem["nivel"], "violencia_sem_risco_imediato")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("psicologica", triagem["tipos_violencia"])
        self.assertIn("restricao_liberdade", triagem["sinais_fonar"])

    def test_estou_segura_e_preciso_informacoes_com_celular_vira_orientacao_nao_digital(self):
        historico = [
            {
                "role": "user",
                "content": "meu marido esta me deixando trancada em casa",
            },
        ]

        triagem = avaliar_triagem_fonar(
            "estou segura, mas preciso de informacoes, ele nao me deixa pegar o celular sempre",
            historico=historico,
        )

        self.assertEqual(triagem["nivel"], "pedido_orientacao")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("pedido_orientacao_com_contexto", triagem["sinais_fonar"])
        self.assertNotIn("digital", triagem["tipos_violencia"])

    def test_pedido_de_direitos_usa_contexto_recente_de_abuso(self):
        historico = [
            {
                "role": "user",
                "content": "meu marido nunca abre a janela de casa, sempre fico no escuro",
            },
            {
                "role": "assistant",
                "content": "Estou aqui com voce. Voce esta segura agora para conversar?",
            },
            {
                "role": "user",
                "content": "ele sempre me diz que eu devo ficar trancada em casa",
            },
        ]

        triagem = avaliar_triagem_fonar(
            "eu posso conversar, quais sao os meus direitos?",
            historico=historico,
        )

        self.assertEqual(triagem["nivel"], "pedido_orientacao")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("pedido_orientacao_com_contexto", triagem["sinais_fonar"])
        self.assertEqual(triagem["acao_resposta"], "orientar_com_passos")

    def test_estou_segura_e_quero_direitos_usa_contexto_recente_de_abuso(self):
        historico = [
            {
                "role": "user",
                "content": "meu marido me expoe nas redes sociais sem meu consentimento",
            },
            {
                "role": "user",
                "content": "ele sempre me diz que eu devo ficar trancada em casa",
            },
        ]

        triagem = avaliar_triagem_fonar(
            "estou segura agora, e gostaria de saber dos meus direitos o que eu posso fazer contra ele",
            historico=historico,
        )

        self.assertEqual(triagem["nivel"], "pedido_orientacao")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("pedido_orientacao_com_contexto", triagem["sinais_fonar"])

    def test_pedido_de_direitos_sem_contexto_sensivel_continua_ambiguo(self):
        triagem = avaliar_triagem_fonar("quais sao os meus direitos?")

        self.assertEqual(triagem["nivel"], "ambigua")
        self.assertFalse(triagem["risco_imediato"])

    def test_pedido_de_direitos_trans_vira_orientacao_lgbtqia_sem_risco_imediato(self):
        triagem = avaliar_triagem_fonar("por eu ser trans, eu tenho direitos?")

        self.assertEqual(triagem["nivel"], "pedido_orientacao")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("identidade_genero_trans", triagem["sinais_fonar"])
        self.assertIn("direitos_lgbtqia", triagem["sinais_fonar"])
        self.assertEqual(triagem["acao_resposta"], "orientar_direitos_lgbtqia")

    def test_relato_de_mulher_trans_com_marido_acolhe_antes_de_orientar(self):
        triagem = avaliar_triagem_fonar(
            "por eu ser trans, meu marido diz que eu nao tenho os mesmos direitos das mulheres"
        )

        self.assertEqual(triagem["nivel"], "violencia_sem_risco_imediato")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("psicologica", triagem["tipos_violencia"])
        self.assertIn("identidade_genero_trans", triagem["sinais_fonar"])
        self.assertIn("direitos_lgbtqia", triagem["sinais_fonar"])
        self.assertIn("negacao_direitos_por_genero", triagem["sinais_fonar"])
        self.assertEqual(triagem["acao_resposta"], "acolher_e_perguntar_seguranca")

    def test_pedido_de_direitos_usa_contexto_recente_de_mulher_trans(self):
        historico = [
            {
                "role": "user",
                "content": "por eu ser trans, meu marido diz que eu nao tenho os mesmos direitos das mulheres",
            }
        ]

        triagem = avaliar_triagem_fonar(
            "queria conversar sobre os meus direitos",
            historico=historico,
        )

        self.assertEqual(triagem["nivel"], "pedido_orientacao")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("identidade_genero_trans", triagem["sinais_fonar"])
        self.assertIn("direitos_lgbtqia", triagem["sinais_fonar"])
        self.assertIn("pedido_orientacao_com_contexto", triagem["sinais_fonar"])
        self.assertEqual(triagem["acao_resposta"], "orientar_direitos_lgbtqia")

    def test_trans_com_erro_de_digitacao_preserva_intencao_de_direitos(self):
        historico = []
        primeira = avaliar_triagem_fonar(
            "por eu ser trans, meu marido diz que eu nao tenhos os mesmo direitos das mulheres",
            historico=historico,
        )
        historico.append({
            "role": "user",
            "content": "por eu ser trans, meu marido diz que eu nao tenhos os mesmo direitos das mulheres",
        })
        segunda = avaliar_triagem_fonar("quais sao meus direitos ?", historico=historico)

        self.assertEqual(primeira["nivel"], "violencia_sem_risco_imediato")
        self.assertIn("negacao_direitos_por_genero", primeira["sinais_fonar"])
        self.assertEqual(primeira["acao_resposta"], "acolher_e_perguntar_seguranca")
        self.assertEqual(segunda["nivel"], "pedido_orientacao")
        self.assertIn("identidade_genero_trans", segunda["sinais_fonar"])
        self.assertEqual(segunda["acao_resposta"], "orientar_direitos_lgbtqia")

    def test_pedidos_especificos_nao_caem_na_orientacao_generica(self):
        casos = {
            "como funciona o boletim de ocorrencia eletronico ?": ("orientar_bo_online", "pedido_bo_online"),
            "quais as medidas protetivas eu posso ter ?": ("orientar_medida_protetiva", "pedido_medida_protetiva"),
            "e se ele vier atras de mim ?": ("orientar_plano_seguranca", "perseguicao_ou_retorno_agressor"),
        }

        for mensagem, (acao, sinal) in casos.items():
            with self.subTest(mensagem=mensagem):
                triagem = avaliar_triagem_fonar(mensagem, historico=[
                    {"role": "user", "content": "meu marido diz que se eu sair ele vai bater nas minhas criancas"}
                ])

                self.assertEqual(triagem["nivel"], "pedido_orientacao")
                self.assertFalse(triagem["risco_imediato"])
                self.assertIn(sinal, triagem["sinais_fonar"])
                self.assertEqual(triagem["acao_resposta"], acao)

    def test_pedido_de_convivencia_com_frase_informal_nao_vira_generico(self):
        triagem = avaliar_triagem_fonar(
            "eu posso direito de ver meus filhos ?",
            historico=[
                {"role": "user", "content": "meu marido nao me deixar ver meus filhos"},
            ],
        )

        self.assertEqual(triagem["nivel"], "pedido_orientacao")
        self.assertIn("pedido_convivencia_filhos", triagem["sinais_fonar"])
        self.assertEqual(triagem["acao_resposta"], "orientar_convivencia_filhos")

    def test_relato_trans_com_nome_antigo_acolhe_como_violencia_psicologica(self):
        triagem = avaliar_triagem_fonar(
            "sou homem trans e meu parceiro usa meu nome antigo para me humilhar"
        )

        self.assertEqual(triagem["nivel"], "violencia_sem_risco_imediato")
        self.assertIn("psicologica", triagem["tipos_violencia"])
        self.assertIn("identidade_genero_trans", triagem["sinais_fonar"])
        self.assertIn("violencia_psicologica_transfobica", triagem["sinais_fonar"])
        self.assertEqual(triagem["acao_resposta"], "acolher_e_perguntar_seguranca")

    def test_controle_sobre_filhos_e_pedido_de_convivencia_tem_fluxo_proprio(self):
        primeira = avaliar_triagem_fonar("meu marido nao me deixar ver meus filhos")
        historico = [
            {"role": "user", "content": "meu marido nao me deixar ver meus filhos"}
        ]
        segunda = avaliar_triagem_fonar(
            "eu possuo direito de ver meus filhos ?",
            historico=historico,
        )

        self.assertEqual(primeira["nivel"], "violencia_sem_risco_imediato")
        self.assertIn("psicologica", primeira["tipos_violencia"])
        self.assertIn("controle_sobre_filhos", primeira["sinais_fonar"])
        self.assertEqual(primeira["acao_resposta"], "acolher_e_perguntar_seguranca")

        self.assertEqual(segunda["nivel"], "pedido_orientacao")
        self.assertIn("pedido_convivencia_filhos", segunda["sinais_fonar"])
        self.assertIn("pedido_orientacao_com_contexto", segunda["sinais_fonar"])
        self.assertEqual(segunda["acao_resposta"], "orientar_convivencia_filhos")

    def test_emergencia_obvia_local_e_minima(self):
        self.assertTrue(avaliar_emergencia_obvia("ele esta aqui com uma faca"))
        self.assertTrue(avaliar_emergencia_obvia("nao posso falar, ele pode ouvir"))
        self.assertTrue(avaliar_emergencia_obvia("ele disse que vai me matar amanha"))

        self.assertFalse(avaliar_emergencia_obvia("ele sempre me diz que devo ficar trancada em casa"))
        self.assertFalse(avaliar_emergencia_obvia("meu marido nunca abre a janela de casa"))
        self.assertFalse(avaliar_emergencia_obvia("meu marido me expoe nas redes sociais"))

    def test_frases_criticas_da_bateria_recebem_triagem_segura(self):
        casos = {
            "ele esta aqui": ("risco_grave", True, "agressor_presente"),
            "tenho medo de morrer": ("risco_grave", True, "ameaca_morte"),
            "fui agredida": ("violencia_sem_risco_imediato", False, "agressao_fisica"),
            "tenho filhos comigo": ("risco_moderado", False, "filhos_comigo"),
            "nao tenho para onde ir": ("pedido_orientacao", False, "sem_abrigo"),
        }

        for mensagem, (nivel, risco_imediato, sinal) in casos.items():
            with self.subTest(mensagem=mensagem):
                triagem = avaliar_triagem_fonar(mensagem)

                self.assertEqual(triagem["nivel"], nivel)
                self.assertEqual(triagem["risco_imediato"], risco_imediato)
                self.assertIn(sinal, triagem["sinais_fonar"])


if __name__ == "__main__":
    unittest.main()
