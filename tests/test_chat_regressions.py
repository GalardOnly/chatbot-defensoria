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
                patch.object(app, "classificar_triagem_llm", return_value={
                    "nivel": "fachada",
                    "risco_imediato": False,
                    "tipos_violencia": [],
                    "sinais_fonar": [],
                    "acao_resposta": "fachada",
                    "origem": "llm",
                }),
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
                patch.object(app, "classificar_triagem_llm", side_effect=fail_if_called) as triagem_mock,
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
                triagem_mock.assert_not_called()
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
                patch.object(app, "classificar_triagem_llm", side_effect=fail_if_called) as triagem_mock,
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
                triagem_mock.assert_not_called()
                modo_mock.assert_not_called()
                responder_mock.assert_not_called()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["modo"], "real")
        self.assertIn("190", data["resposta"])
        self.assertIn("180", data["resposta"])

    def test_declared_abuse_without_immediate_risk_uses_deterministic_first_acolhimento(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()

            def fail_if_called(*args, **kwargs):
                raise AssertionError("detector legado ou triagem LLM nao deve decidir este caso local")

            with (
                patch.object(app, "_servicos_prontos", True),
                patch.object(app, "classificador", None),
                patch.object(app, "classificar_triagem_llm", side_effect=fail_if_called) as triagem_mock,
                patch.object(app, "detectar_modo", side_effect=fail_if_called) as modo_mock,
                patch.object(app, "responder_pergunta", side_effect=AssertionError("primeiro acolhimento nao deve depender da LLM")) as responder_mock,
            ):
                response = app.app.test_client().post(
                    "/chat",
                    json={
                        "mensagem": "meu marido me expoe nas redes sociais sem meu consentimento",
                        "session_id": session_id,
                    },
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )
                triagem_mock.assert_not_called()
                modo_mock.assert_not_called()
                responder_mock.assert_not_called()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["modo"], "real")
        self.assertIn("privacidade", data["resposta"].lower())
        self.assertIn("não é culpa", data["resposta"].lower())
        self.assertIn("pode ver essa conversa", data["resposta"].lower())

    def test_local_triage_routes_control_context_to_real_without_legacy_detector(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()

            with (
                patch.object(app, "_servicos_prontos", True),
                patch.object(app, "classificador", None),
                patch.object(app, "classificar_triagem_llm", side_effect=AssertionError("triagem local deve cobrir este caso")) as triagem_mock,
                patch.object(app, "detectar_modo", side_effect=AssertionError("old detector should not decide")),
                patch.object(app, "responder_pergunta", return_value="acolhimento"),
            ):
                response = app.app.test_client().post(
                    "/chat",
                    json={
                        "mensagem": "meu marido nunca abre a janela de casa, sempre fico no escuro",
                        "session_id": session_id,
                    },
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["modo"], "real")
        triagem_mock.assert_not_called()

    def test_llm_failure_fallback_receives_history_for_context(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()
            app.salvar_mensagem(
                session_id,
                "user",
                "ele sempre me diz que eu devo ficar trancada em casa",
                triagem={
                    "nivel": "violencia_sem_risco_imediato",
                    "risco_imediato": False,
                    "tipos_violencia": ["psicologica"],
                    "sinais_fonar": ["restricao_liberdade"],
                    "acao_resposta": "acolher_e_perguntar_seguranca",
                },
            )

            captured = {}

            def fallback_fake(*args, **kwargs):
                captured["historico"] = kwargs.get("historico")
                return "fallback contextual"

            with (
                patch.object(app, "_servicos_prontos", True),
                patch.object(app, "classificador", None),
                patch.object(app, "classificar_triagem_llm", side_effect=AssertionError("triagem contextual local deve cobrir este caso")),
                patch.object(app, "detectar_modo", side_effect=AssertionError("old detector should not decide")),
                patch.object(app, "responder_pergunta", side_effect=RuntimeError("LLM off")),
                patch.object(app, "resposta_contingencia", side_effect=fallback_fake),
            ):
                client = app.app.test_client()
                response = client.post(
                    "/chat",
                    json={
                        "mensagem": "eu posso conversar, quais sao os meus direitos?",
                        "session_id": session_id,
                    },
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["resposta"], "fallback contextual")
        historico_texto = "\n".join(m.get("content", "") for m in captured["historico"])
        self.assertIn("trancada em casa", historico_texto)

    def test_contextual_rights_request_skips_triage_llm_but_uses_llm_response(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()
            app.salvar_mensagem(
                session_id,
                "user",
                "meu marido me expoe nas redes sociais sem meu consentimento",
            )
            app.salvar_mensagem(
                session_id,
                "user",
                "ele sempre me diz que eu devo ficar trancada em casa",
            )
            captured = {}

            def fail_if_called(*args, **kwargs):
                raise AssertionError("pedido de orientacao contextual nao deve esperar LLM de triagem")

            def responder_fake(*args, **kwargs):
                captured["triagem"] = kwargs.get("triagem")
                return "resposta acolhedora da LLM com direitos"

            with (
                patch.object(app, "_servicos_prontos", True),
                patch.object(app, "classificador", None),
                patch.object(app, "classificar_triagem_llm", side_effect=fail_if_called) as triagem_mock,
                patch.object(app, "responder_pergunta", side_effect=responder_fake) as responder_mock,
            ):
                response = app.app.test_client().post(
                    "/chat",
                    json={
                        "mensagem": "estou segura agora, e gostaria de saber dos meus direitos o que eu posso fazer contra ele",
                        "session_id": session_id,
                    },
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["modo"], "real")
        self.assertEqual(data["resposta"], "resposta acolhedora da LLM com direitos")
        self.assertEqual(captured["triagem"]["nivel"], "pedido_orientacao")
        triagem_mock.assert_not_called()
        responder_mock.assert_called_once()

    def test_safe_emotional_followup_after_trans_relato_uses_llm_conversation(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()
            app.salvar_mensagem(
                session_id,
                "user",
                "meu marido diz que nao sou suficiente por ser mulher trans",
                triagem={
                    "nivel": "violencia_sem_risco_imediato",
                    "risco_imediato": False,
                    "tipos_violencia": ["psicologica"],
                    "sinais_fonar": [
                        "identidade_genero_trans",
                        "violencia_psicologica_transfobica",
                        "desabafo_emocional",
                    ],
                    "acao_resposta": "acolher_e_perguntar_seguranca",
                },
            )
            app.salvar_mensagem(
                session_id,
                "assistant",
                "Sinto muito que isso esteja acontecendo. Voce esta segura para conversar?",
            )

            captured = {}

            def responder_fake(*args, **kwargs):
                captured["triagem"] = kwargs.get("triagem")
                captured["historico"] = kwargs.get("historico")
                return "Estou aqui com voce. Podemos conversar no seu tempo, sem pressa."

            with (
                patch.object(app, "_servicos_prontos", True),
                patch.object(app, "classificador", None),
                patch.object(app, "classificar_triagem_llm", return_value={
                    "nivel": "pedido_orientacao",
                    "risco_imediato": False,
                    "tipos_violencia": [],
                    "sinais_fonar": ["identidade_genero_trans", "direitos_lgbtqia"],
                    "acao_resposta": "orientar_direitos_lgbtqia",
                    "origem": "llm",
                }),
                patch.object(app, "responder_pergunta", side_effect=responder_fake) as responder_mock,
            ):
                response = app.app.test_client().post(
                    "/chat",
                    json={
                        "mensagem": "estou segura, queria apenas conversar pra me sentir melhor",
                        "session_id": session_id,
                    },
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["resposta"],
            "Estou aqui com voce. Podemos conversar no seu tempo, sem pressa.",
        )
        responder_mock.assert_called_once()
        self.assertEqual(captured["triagem"]["acao_resposta"], "orientar_direitos_lgbtqia")
        historico_texto = "\n".join(m.get("content", "") for m in captured["historico"])
        self.assertIn("mulher trans", historico_texto)

    def test_short_followups_continue_with_llm_not_deterministic_fallback(self):
        import app

        for mensagem in ["sim", "gostaria", "pode ser"]:
            with self.subTest(mensagem=mensagem):
                with tempfile.TemporaryDirectory() as tmp:
                    app.DB_PATH = os.path.join(tmp, "historico.db")
                    app.init_db()
                    session_id, delete_token = app.registrar_sessao()
                    app.salvar_mensagem(
                        session_id,
                        "user",
                        "por eu ser trans, meu marido diz que eu nao tenho os mesmos direitos das mulheres",
                        triagem={
                            "nivel": "violencia_sem_risco_imediato",
                            "risco_imediato": False,
                            "tipos_violencia": ["psicologica"],
                            "sinais_fonar": ["identidade_genero_trans", "direitos_lgbtqia"],
                            "acao_resposta": "acolher_e_perguntar_seguranca",
                        },
                    )
                    app.salvar_mensagem(
                        session_id,
                        "assistant",
                        "Posso te explicar seus direitos com calma, se voce quiser.",
                    )

                    captured = {}

                    def responder_fake(*args, **kwargs):
                        captured["historico"] = kwargs.get("historico")
                        captured["triagem"] = kwargs.get("triagem")
                        return "Claro. Vou continuar do ponto em que paramos, com calma."

                    with (
                        patch.object(app, "_servicos_prontos", True),
                        patch.object(app, "classificador", None),
                        patch.object(app, "classificar_triagem_llm", return_value={
                            "nivel": "pedido_orientacao",
                            "risco_imediato": False,
                            "tipos_violencia": [],
                            "sinais_fonar": ["identidade_genero_trans", "direitos_lgbtqia"],
                            "acao_resposta": "orientar_direitos_lgbtqia",
                            "origem": "llm",
                        }),
                        patch.object(app, "responder_pergunta", side_effect=responder_fake) as responder_mock,
                    ):
                        response = app.app.test_client().post(
                            "/chat",
                            json={"mensagem": mensagem, "session_id": session_id},
                            headers={
                                "X-Session-Id": session_id,
                                "X-Session-Token": delete_token,
                            },
                        )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.get_json()["resposta"],
                    "Claro. Vou continuar do ponto em que paramos, com calma.",
                )
                responder_mock.assert_called_once()
                self.assertEqual(captured["triagem"]["acao_resposta"], "orientar_direitos_lgbtqia")
                historico_texto = "\n".join(m.get("content", "") for m in captured["historico"])
                self.assertIn("Posso te explicar seus direitos", historico_texto)

    def test_explicit_law_request_uses_llm_not_fixed_channel_text(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()
            app.salvar_mensagem(
                session_id,
                "user",
                "meu marido me humilha todos os dias",
                triagem={
                    "nivel": "violencia_sem_risco_imediato",
                    "risco_imediato": False,
                    "tipos_violencia": ["psicologica"],
                    "sinais_fonar": ["violencia_psicologica"],
                    "acao_resposta": "acolher_e_perguntar_seguranca",
                },
            )

            captured = {}

            def responder_fake(*args, **kwargs):
                captured["triagem"] = kwargs.get("triagem")
                return "A LLM deve explicar as leis aplicaveis com linguagem simples."

            with (
                patch.object(app, "_servicos_prontos", True),
                patch.object(app, "classificador", None),
                patch.object(app, "classificar_triagem_llm", side_effect=AssertionError("pedido explicito de lei deve ser triagem local")),
                patch.object(app, "responder_pergunta", side_effect=responder_fake) as responder_mock,
            ):
                response = app.app.test_client().post(
                    "/chat",
                    json={"mensagem": "quais leis me protegem?", "session_id": session_id},
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["resposta"],
            "A LLM deve explicar as leis aplicaveis com linguagem simples.",
        )
        responder_mock.assert_called_once()
        self.assertEqual(captured["triagem"]["acao_resposta"], "orientar_direitos_contextuais")

    def test_long_sequence_with_lgbtqia_middle_signal_does_not_rewind_conversation(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()
            app.salvar_mensagem(
                session_id,
                "user",
                "meu marido diz que nao sou mulher de verdade",
                triagem={
                    "nivel": "violencia_sem_risco_imediato",
                    "risco_imediato": False,
                    "tipos_violencia": ["psicologica"],
                    "sinais_fonar": ["identidade_genero_trans", "violencia_psicologica_transfobica"],
                    "acao_resposta": "acolher_e_perguntar_seguranca",
                },
            )
            app.salvar_mensagem(session_id, "assistant", "Sinto muito. Voce esta segura para conversar?")
            app.salvar_mensagem(
                session_id,
                "user",
                "quais direitos eu tenho por ser trans?",
                triagem={
                    "nivel": "pedido_orientacao",
                    "risco_imediato": False,
                    "tipos_violencia": [],
                    "sinais_fonar": ["identidade_genero_trans", "direitos_lgbtqia"],
                    "acao_resposta": "orientar_direitos_lgbtqia",
                },
            )
            app.salvar_mensagem(session_id, "assistant", "Voce tem direito a respeito e nome social.")
            app.salvar_mensagem(session_id, "user", "entendi, obrigada")
            app.salvar_mensagem(session_id, "assistant", "Estou aqui se quiser continuar.")

            captured = {}

            def responder_fake(*args, **kwargs):
                captured["triagem"] = kwargs.get("triagem")
                captured["historico"] = kwargs.get("historico")
                return "Podemos ficar nessa conversa com calma. O que esta pesando mais agora?"

            with (
                patch.object(app, "_servicos_prontos", True),
                patch.object(app, "classificador", None),
                patch.object(app, "classificar_triagem_llm", return_value={
                    "nivel": "pedido_orientacao",
                    "risco_imediato": False,
                    "tipos_violencia": [],
                    "sinais_fonar": ["identidade_genero_trans", "direitos_lgbtqia"],
                    "acao_resposta": "orientar_direitos_lgbtqia",
                    "origem": "llm",
                }),
                patch.object(app, "responder_pergunta", side_effect=responder_fake) as responder_mock,
            ):
                response = app.app.test_client().post(
                    "/chat",
                    json={"mensagem": "queria so conversar um pouco", "session_id": session_id},
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["resposta"],
            "Podemos ficar nessa conversa com calma. O que esta pesando mais agora?",
        )
        responder_mock.assert_called_once()
        self.assertEqual(captured["triagem"]["acao_resposta"], "orientar_direitos_lgbtqia")
        historico_texto = "\n".join(m.get("content", "") for m in captured["historico"])
        self.assertIn("nome social", historico_texto)
        self.assertIn("Estou aqui se quiser continuar", historico_texto)

    def test_initial_denuncia_request_uses_deterministic_official_channels(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()

            with (
                patch.object(app, "_servicos_prontos", True),
                patch.object(app, "classificador", None),
                patch.object(app, "responder_pergunta", side_effect=AssertionError("denuncia inicial deve usar canais oficiais determinísticos")) as responder_mock,
            ):
                response = app.app.test_client().post(
                    "/chat",
                    json={"mensagem": "quero denunciar", "session_id": session_id},
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )
                responder_mock.assert_not_called()

        self.assertEqual(response.status_code, 200)
        resposta = response.get_json()["resposta"].lower()
        self.assertIn("180", resposta)
        self.assertIn("boletim de ocorrencia", resposta)
        self.assertIn("medida protetiva", resposta)

    def test_initial_shelter_request_uses_deterministic_local_network(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()

            with (
                patch.object(app, "_servicos_prontos", True),
                patch.object(app, "classificador", None),
                patch.object(app, "responder_pergunta", side_effect=AssertionError("pedido de abrigo deve usar fallback oficial")) as responder_mock,
            ):
                response = app.app.test_client().post(
                    "/chat",
                    json={"mensagem": "nao tenho para onde ir", "session_id": session_id},
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )
                responder_mock.assert_not_called()

        self.assertEqual(response.status_code, 200)
        resposta = response.get_json()["resposta"].lower()
        self.assertIn("casa da mulher", resposta)
        self.assertIn("defensoria", resposta)
        self.assertIn("180", resposta)

    def test_trans_rights_request_uses_inclusive_llm_response(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()

            captured = {}

            def responder_fake(*args, **kwargs):
                captured["triagem"] = kwargs.get("triagem")
                return (
                    "Pessoas trans, incluindo mulheres trans e travestis, tem direito a respeito, "
                    "nome social e protecao contra LGBTfobia. O Disque 100 tambem pode receber violacoes."
                )

            with (
                patch.object(app, "_servicos_prontos", True),
                patch.object(app, "classificador", None),
                patch.object(app, "classificar_triagem_llm", side_effect=AssertionError("direitos trans devem ser triagem local deterministica")),
                patch.object(app, "responder_pergunta", side_effect=responder_fake) as responder_mock,
            ):
                response = app.app.test_client().post(
                    "/chat",
                    json={"mensagem": "por eu ser trans, eu tenho direitos?", "session_id": session_id},
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["modo"], "real")
        responder_mock.assert_called_once()
        self.assertEqual(captured["triagem"]["acao_resposta"], "orientar_direitos_lgbtqia")
        resposta = data["resposta"].lower()
        self.assertIn("pessoas trans", resposta)
        self.assertIn("nome social", resposta)
        self.assertIn("disque 100", resposta)
        self.assertNotIn("boletim de ocorrencia", resposta)
        self.assertNotIn("formulario de medida protetiva", resposta)

    def test_trans_context_is_preserved_when_user_later_asks_about_rights(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()

            def responder_fake(*args, **kwargs):
                return (
                    "Mulheres trans tem direitos e devem ser respeitadas. "
                    "Voce pode pedir orientacao sobre nome social e o Disque 100 recebe LGBTfobia."
                )

            with (
                patch.object(app, "_servicos_prontos", True),
                patch.object(app, "classificador", None),
                patch.object(app, "classificar_triagem_llm", side_effect=AssertionError("contexto trans deve ser coberto pela triagem local")),
                patch.object(app, "responder_pergunta", side_effect=responder_fake) as responder_mock,
            ):
                client = app.app.test_client()
                primeira = client.post(
                    "/chat",
                    json={
                        "mensagem": "por eu ser trans, meu marido diz que eu nao tenho os mesmos direitos das mulheres",
                        "session_id": session_id,
                    },
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )
                segunda = client.post(
                    "/chat",
                    json={
                        "mensagem": "queria conversar sobre os meus direitos",
                        "session_id": session_id,
                    },
                    headers={
                        "X-Session-Id": session_id,
                        "X-Session-Token": delete_token,
                    },
                )

        self.assertEqual(primeira.status_code, 200)
        primeira_resposta = primeira.get_json()["resposta"].lower()
        self.assertIn("mulheres trans", primeira_resposta)
        self.assertIn("não é culpa", primeira_resposta)
        self.assertNotIn("boletim de ocorrencia", primeira_resposta)

        self.assertEqual(segunda.status_code, 200)
        responder_mock.assert_called_once()
        segunda_resposta = segunda.get_json()["resposta"].lower()
        self.assertIn("mulheres trans", segunda_resposta)
        self.assertIn("nome social", segunda_resposta)
        self.assertIn("disque 100", segunda_resposta)
        self.assertNotIn("boletim de ocorrencia", segunda_resposta)
        self.assertNotIn("formulario de medida protetiva", segunda_resposta)

    def test_specific_guidance_requests_do_not_use_generic_contact_wall(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()

            def responder_fake(*args, **kwargs):
                pergunta = (kwargs.get("pergunta") or "").lower()
                if "boletim" in pergunta:
                    return "O boletim de ocorrencia eletronico pode gerar um protocolo na Delegacia Eletronica, Delegacia Eletrônica."
                if "medidas protetivas" in pergunta:
                    return "Medidas protetivas podem incluir afastamento, proibicao de contato e protecao relacionada aos filhos."
                if "vier atras" in pergunta:
                    return "Se ele vier atras de voce, nao confronte, não confronte. Priorize um local seguro e ligue 190 se houver risco."
                return "orientacao contextual"

            with (
                patch.object(app, "_servicos_prontos", True),
                patch.object(app, "classificador", None),
                patch.object(app, "classificar_triagem_llm", side_effect=AssertionError("pedidos especificos devem ser triagem local")),
                patch.object(app, "responder_pergunta", side_effect=responder_fake) as responder_mock,
            ):
                client = app.app.test_client()
                primeira = client.post(
                    "/chat",
                    json={
                        "mensagem": "meu marido diz que se eu sair de casa ele vai bater nas minhas criancas",
                        "session_id": session_id,
                    },
                    headers={"X-Session-Id": session_id, "X-Session-Token": delete_token},
                )
                bo = client.post(
                    "/chat",
                    json={
                        "mensagem": "como funciona o boletim de ocorrencia eletronico ?",
                        "session_id": session_id,
                    },
                    headers={"X-Session-Id": session_id, "X-Session-Token": delete_token},
                )
                medidas = client.post(
                    "/chat",
                    json={
                        "mensagem": "quais as medidas protetivas eu posso ter ?",
                        "session_id": session_id,
                    },
                    headers={"X-Session-Id": session_id, "X-Session-Token": delete_token},
                )
                seguranca = client.post(
                    "/chat",
                    json={
                        "mensagem": "e se ele vier atras de mim ?",
                        "session_id": session_id,
                    },
                    headers={"X-Session-Id": session_id, "X-Session-Token": delete_token},
                )

        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(responder_mock.call_count, 3)
        self.assertEqual(bo.status_code, 200)
        bo_texto = bo.get_json()["resposta"].lower()
        self.assertIn("delegacia eletrônica", bo_texto)
        self.assertIn("delegacia eletronica", bo_texto)
        self.assertIn("protocolo", bo_texto)
        self.assertNotIn("canais oficiais - horizonte", bo_texto)

        self.assertEqual(medidas.status_code, 200)
        medidas_texto = medidas.get_json()["resposta"].lower()
        self.assertIn("afastamento", medidas_texto)
        self.assertIn("filhos", medidas_texto)
        self.assertNotIn("canais oficiais - horizonte", medidas_texto)

        self.assertEqual(seguranca.status_code, 200)
        seguranca_texto = seguranca.get_json()["resposta"].lower()
        self.assertIn("não confronte", seguranca_texto)
        self.assertIn("nao confronte", seguranca_texto)
        self.assertIn("190", seguranca_texto)
        self.assertNotIn("canais oficiais - horizonte", seguranca_texto)

    def test_children_contact_rights_request_does_not_use_generic_contact_wall(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, delete_token = app.registrar_sessao()

            def responder_fake(*args, **kwargs):
                return (
                    "Voce pode buscar orientacao sobre convivencia com seus filhos na Defensoria. "
                    "Nao confronte, não confronte se isso puder aumentar o risco."
                )

            with (
                patch.object(app, "_servicos_prontos", True),
                patch.object(app, "classificador", None),
                patch.object(app, "classificar_triagem_llm", side_effect=AssertionError("filhos deve ser triagem local")),
                patch.object(app, "responder_pergunta", side_effect=responder_fake) as responder_mock,
            ):
                client = app.app.test_client()
                primeira = client.post(
                    "/chat",
                    json={
                        "mensagem": "meu marido nao me deixar ver meus filhos",
                        "session_id": session_id,
                    },
                    headers={"X-Session-Id": session_id, "X-Session-Token": delete_token},
                )
                segunda = client.post(
                    "/chat",
                    json={
                        "mensagem": "eu possuo direito de ver meus filhos ?",
                        "session_id": session_id,
                    },
                    headers={"X-Session-Id": session_id, "X-Session-Token": delete_token},
                )

        self.assertEqual(primeira.status_code, 200)
        primeira_texto = primeira.get_json()["resposta"].lower()
        self.assertIn("filhos", primeira_texto)
        self.assertIn("segura", primeira_texto)
        self.assertNotIn("canais oficiais - horizonte", primeira_texto)

        self.assertEqual(segunda.status_code, 200)
        responder_mock.assert_called_once()
        segunda_texto = segunda.get_json()["resposta"].lower()
        self.assertIn("conviv", segunda_texto)
        self.assertIn("defensoria", segunda_texto)
        self.assertIn("não confronte", segunda_texto)
        self.assertNotIn("canais oficiais - horizonte", segunda_texto)

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

    def test_admin_sessions_use_fonar_summary_even_without_legacy_classifier(self):
        import app

        with tempfile.TemporaryDirectory() as tmp:
            app.DB_PATH = os.path.join(tmp, "historico.db")
            app.init_db()
            session_id, _ = app.registrar_sessao()
            app.salvar_mensagem(
                session_id,
                "user",
                "ele esta aqui",
                triagem={
                    "nivel": "risco_grave",
                    "risco_imediato": True,
                    "tipos_violencia": ["psicologica"],
                    "sinais_fonar": ["agressor_presente"],
                    "acao_resposta": "risco_imediato",
                },
            )

            response = app.app.test_client().get(
                "/sessoes",
                headers={"Authorization": f"Bearer {app.ADMIN_TOKEN}"},
            )

        self.assertEqual(response.status_code, 200)
        sessao = response.get_json()["sessoes"][session_id]
        self.assertEqual(sessao["modo_detectado"], "real")
        self.assertEqual(sessao["fonar"]["nivel_risco"], "risco_grave")
        self.assertTrue(sessao["fonar"]["risco_imediato"])
        self.assertIn("psicologica", sessao["fonar"]["tipos_violencia_fonar"])
        self.assertIn("agressor_presente", sessao["fonar"]["sinais_fonar"])


class GroqTimeoutRegressionsTest(unittest.TestCase):
    def test_groq_uses_short_timeout_and_single_attempt(self):
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

        self.assertEqual(calls, [15])


if __name__ == "__main__":
    unittest.main()
