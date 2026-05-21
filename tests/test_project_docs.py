import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
README = PROJECT_ROOT / "README.md"
APP = PROJECT_ROOT / "app.py"
CRYPTO_TOOL = PROJECT_ROOT / "gerenciar_cripto.py"


class ProjectDocsTest(unittest.TestCase):
    def test_readme_explains_run_env_demo_and_safety_limits(self):
        self.assertTrue(README.exists(), "README.md deve existir para demonstracao")
        texto = README.read_text(encoding="utf-8").lower()

        for trecho in [
            "como rodar",
            "variaveis de ambiente",
            "groq_api_key",
            "gemini_api_key",
            "admin_token",
            "db_encryption_key",
            "roteiro seguro de demonstracao",
            "nao substitui atendimento humano",
            "ligue 180",
            "190",
        ]:
            with self.subTest(trecho=trecho):
                self.assertIn(trecho, texto)

    def test_crypto_verification_does_not_print_decrypted_samples(self):
        texto = CRYPTO_TOOL.read_text(encoding="utf-8")

        self.assertNotIn("texto[:50]", texto)
        self.assertIn("sem exibir conteudo", texto)
        self.assertIn("hash", texto)

    def test_app_logs_do_not_print_full_session_id(self):
        texto = APP.read_text(encoding="utf-8")

        self.assertIn("_session_id_seguro", texto)
        self.assertNotIn("session_id={session_id}", texto)
        self.assertNotIn("session={session_id or '?'}", texto)


if __name__ == "__main__":
    unittest.main()
