import unittest

from triagem_fonar import avaliar_triagem_fonar, avaliar_emergencia_obvia


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

    def test_controle_para_ficar_trancada_em_casa_nao_vira_fachada(self):
        triagem = avaliar_triagem_fonar(
            "ele sempre me diz que eu devo ficar trancada em casa"
        )

        self.assertEqual(triagem["nivel"], "violencia_sem_risco_imediato")
        self.assertFalse(triagem["risco_imediato"])
        self.assertIn("psicologica", triagem["tipos_violencia"])
        self.assertIn("restricao_liberdade", triagem["sinais_fonar"])

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

    def test_pedido_de_direitos_sem_contexto_sensivel_continua_ambiguo(self):
        triagem = avaliar_triagem_fonar("quais sao os meus direitos?")

        self.assertEqual(triagem["nivel"], "ambigua")
        self.assertFalse(triagem["risco_imediato"])

    def test_emergencia_obvia_local_e_minima(self):
        self.assertTrue(avaliar_emergencia_obvia("ele esta aqui com uma faca"))
        self.assertTrue(avaliar_emergencia_obvia("nao posso falar, ele pode ouvir"))
        self.assertTrue(avaliar_emergencia_obvia("ele disse que vai me matar amanha"))

        self.assertFalse(avaliar_emergencia_obvia("ele sempre me diz que devo ficar trancada em casa"))
        self.assertFalse(avaliar_emergencia_obvia("meu marido nunca abre a janela de casa"))
        self.assertFalse(avaliar_emergencia_obvia("meu marido me expoe nas redes sociais"))


if __name__ == "__main__":
    unittest.main()
