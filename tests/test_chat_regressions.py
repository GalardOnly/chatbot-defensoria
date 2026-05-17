import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ChatLatencyRegressionsTest(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("ADMIN_TOKEN", "x" * 64)
        os.environ.setdefault("DB_ENCRYPTION_KEY", "y" * 64)

    def test_chat_does_not_block_waiting_for_background_boot(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()

            def fail_if_called(*args, **kwargs):
                raise AssertionError("chat request waited for background boot")

            with (
                patch.object(app, "_servicos_prontos", False),
                patch.object(app, "garantir_servicos", side_effect=fail_if_called),
                patch.object(app, "classificador", None),
                patch.object(app, "detectar_modo", return_value="fachada"),
                patch.object(app, "responder_pergunta", return_value="ok"),
            ):
                response = app.app.test_client().post(
                    "/chat",
                    json={"mensagem": "como tirar mancha do sofa", "session_id": session_id},
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["resposta"], "ok")

    def test_local_fachada_detection_does_not_call_groq(self):
        import app

        def fail_if_called(*args, **kwargs):
            raise AssertionError("local fachada detection called Groq")

        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}),
            patch.object(app, "criar_chat_groq", side_effect=fail_if_called) as groq,
        ):
            modo = app.detectar_modo("ola", historico=[], session_id="sess_test")

        self.assertEqual(modo, "fachada")
        groq.assert_not_called()

    def test_explicit_danger_is_detected_locally(self):
        import app

        self.assertEqual(app.detectar_modo_local("estou em perigo"), "real")
        self.assertEqual(app.detectar_modo_local("ele me bate"), "real")
        self.assertEqual(app.detectar_modo_local("ele disse que vai me matar amanha"), "real")

    def test_chat_responds_to_greeting_without_llm(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()

            def fail_if_called(*args, **kwargs):
                raise AssertionError("greeting should not wait for LLM")

            with (
                patch.object(app, "_servicos_prontos", False),
                patch.object(app, "classificador", None),
                patch.object(app, "detectar_modo", side_effect=fail_if_called) as modo_mock,
                patch.object(app, "responder_pergunta", side_effect=fail_if_called) as responder_mock,
            ):
                response = app.app.test_client().post(
                    "/chat",
                    json={"mensagem": "ola", "session_id": session_id},
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )
                modo_mock.assert_not_called()
                responder_mock.assert_not_called()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["modo"], "fachada")
        self.assertIn("ajudar", response.get_json()["resposta"].lower())

    def test_chat_responds_to_immediate_risk_without_llm(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()

            def fail_if_called(*args, **kwargs):
                raise AssertionError("immediate risk should not wait for LLM")

            with (
                patch.object(app, "_servicos_prontos", False),
                patch.object(app, "classificador", None),
                patch.object(app, "detectar_modo", side_effect=fail_if_called) as modo_mock,
                patch.object(app, "responder_pergunta", side_effect=fail_if_called) as responder_mock,
            ):
                response = app.app.test_client().post(
                    "/chat",
                    json={"mensagem": "ele disse que vai me matar amanha", "session_id": session_id},
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )
                modo_mock.assert_not_called()
                responder_mock.assert_not_called()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["modo"], "real")
        self.assertIn("190", data["resposta"])
        self.assertIn("180", data["resposta"])

    def test_rag_indexing_is_disabled_by_default(self):
        import app

        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(app._rag_indexacao_habilitada())

        with patch.dict(os.environ, {"ENABLE_RAG_INDEXING": "true"}, clear=True):
            self.assertTrue(app._rag_indexacao_habilitada())

    def test_missing_rag_collection_does_not_block_or_embed(self):
        import conteudo_chat

        class FailIfEmbedded:
            def embed(self, *args, **kwargs):
                raise AssertionError("RAG disabled should not generate embeddings")

        self.assertEqual(
            conteudo_chat.buscar_chunks_relevantes(
                "ola",
                embedding_service=FailIfEmbedded(),
                colecao=None,
            ),
            [],
        )


class GroqTimeoutRegressionsTest(unittest.TestCase):
    def test_groq_uses_short_timeout_and_two_attempts(self):
        import conteudo_chat

        calls = []

        def timeout_post(*args, **kwargs):
            calls.append(kwargs.get("timeout"))
            raise TimeoutError("simulated timeout")

        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}),
            patch.object(conteudo_chat.requests, "post", side_effect=timeout_post),
            patch.object(conteudo_chat.time, "sleep", return_value=None),
        ):
            with self.assertRaises(RuntimeError):
                conteudo_chat.criar_chat_groq([{"role": "user", "content": "oi"}])

        self.assertEqual(calls, [15, 15])


if __name__ == "__main__":
    unittest.main()
