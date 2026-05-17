import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class HorizonteFlowTest(unittest.TestCase):
    def test_official_horizonte_contacts_are_available(self):
        import conteudo_chat

        contatos = conteudo_chat.formatar_contatos("Horizonte")

        self.assertIn("Policia Militar: 190", contatos)
        self.assertIn("Central de Atendimento a Mulher: 180", contatos)
        self.assertIn("Rua Juvenal de Castro, 477, Centro", contatos)
        self.assertIn("Rua Ernani Martins, 45, Diadema", contatos)
        self.assertIn("https://mulher.policiacivil.ce.gov.br", contatos)
        self.assertIn("https://www.delegaciaeletronica.ce.gov.br/beo/", contatos)
        self.assertNotIn("Defensoria Publica do Para", contatos)
        self.assertNotIn("(91) 3181-6181", contatos)
        self.assertNotIn("www.pc.pa.gov.br", contatos)

    def test_real_prompt_uses_horizonte_and_not_para(self):
        import conteudo_chat

        self.assertIn("Horizonte", conteudo_chat.system_prompt_real)
        self.assertIn("fonte oficial", conteudo_chat.system_prompt_real.lower())
        self.assertNotIn("Defensoria Publica do Para", conteudo_chat.system_prompt_real)
        self.assertNotIn("(91) 3181-6181", conteudo_chat.system_prompt_real)

    def test_false_safety_is_immediate_risk_in_fallback(self):
        import conteudo_chat

        resposta = conteudo_chat.resposta_contingencia(
            "Nao estou em risco hoje, mas ele disse que vai me matar amanha",
            modo="real",
        )

        self.assertIn("190", resposta)
        self.assertIn("180", resposta)
        self.assertIn("medida protetiva", resposta.lower())
        self.assertIn("https://mulher.policiacivil.ce.gov.br", resposta)

    def test_llm_context_injects_official_links(self):
        import conteudo_chat

        captured = {}

        def fake_groq(messages, **kwargs):
            captured["messages"] = messages
            return "ok"

        with patch.object(conteudo_chat, "criar_chat_groq", side_effect=fake_groq):
            conteudo_chat.responder_pergunta(
                pergunta="estou em Horizonte e preciso de ajuda",
                embedding_service=None,
                colecao=None,
                historico=[],
                modo="real",
                session_id="sess_test",
            )

        contexto = "\n".join(m["content"] for m in captured["messages"])
        self.assertIn("https://mulher.policiacivil.ce.gov.br", contexto)
        self.assertIn("https://www.delegaciaeletronica.ce.gov.br/beo/", contexto)
        self.assertIn("Rua Ernani Martins, 45, Diadema", contexto)


if __name__ == "__main__":
    unittest.main()
