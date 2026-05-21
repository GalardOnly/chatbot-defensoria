import re
import unittest
from pathlib import Path


PAINEL_HTML = Path(__file__).resolve().parents[1] / "painel.html"


def _function_body(script: str, name: str) -> str:
    match = re.search(rf"(?:async )?function {name}\([^)]*\) \{{([\s\S]*?)\n  \}}", script)
    if not match:
        raise AssertionError(f"function {name} not found")
    return match.group(1)


class PainelFonarTest(unittest.TestCase):
    def setUp(self):
        self.html = PAINEL_HTML.read_text(encoding="utf-8")
        script_match = re.search(r"<script>([\s\S]*?)</script>", self.html)
        self.assertIsNotNone(script_match)
        self.script = script_match.group(1)

    def test_session_list_uses_backend_fonar_metadata(self):
        self.assertIn("function sessaoEhReal", self.script)
        self.assertIn("function fonarResumoSessao", self.script)
        self.assertIn("nivel_risco", self.script)
        self.assertIn("risco_imediato", self.script)
        self.assertIn("tipos_violencia_fonar", self.script)
        self.assertIn("sinais_fonar", self.script)

        body = _function_body(self.script, "renderizarSessoes")
        self.assertIn("sessaoEhReal(info)", body)
        self.assertIn("anexarResumoFonar(div, fonarResumoSessao(info))", body)

    def test_history_uses_fonar_metadata_instead_of_local_text_heuristic(self):
        body = _function_body(self.script, "verHistorico")

        self.assertIn("mensagemEhRealFonar(msg)", body)
        self.assertIn("anexarResumoFonar(wrap,", body)
        self.assertNotIn("detectarModoLocal(msg.mensagem)", body)


if __name__ == "__main__":
    unittest.main()
