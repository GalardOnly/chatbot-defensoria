import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
README = PROJECT_ROOT / "README.md"
APP = PROJECT_ROOT / "app.py"
CRYPTO_TOOL = PROJECT_ROOT / "gerenciar_cripto.py"
TREINAR_MODELO = PROJECT_ROOT / "treinar_modelo.py"
DATASET_TRANS = PROJECT_ROOT / "dataset_trans.csv"
RENDER_YAML = PROJECT_ROOT / "render.yaml"


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

    def test_dataset_trans_is_integrated_into_training_script(self):
        self.assertTrue(DATASET_TRANS.exists(), "dataset_trans.csv deve estar presente")
        texto = TREINAR_MODELO.read_text(encoding="utf-8")
        dataset = DATASET_TRANS.read_text(encoding="utf-8").lower()

        self.assertIn("dataset_trans.csv", texto)
        self.assertIn("mapa_tipo_trans", texto)
        self.assertIn('"stalking": "psicologica"', texto)
        self.assertIn('"grave": "alta"', texto)
        self.assertIn("nome de registro", dataset)
        self.assertIn("travesti", dataset)

    def test_render_build_trains_models_from_current_datasets(self):
        texto = RENDER_YAML.read_text(encoding="utf-8")

        self.assertIn("pip install -r requirements.txt", texto)
        self.assertIn("python treinar_modelo.py", texto)


if __name__ == "__main__":
    unittest.main()
