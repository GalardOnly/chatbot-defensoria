import re
import unittest
from pathlib import Path


INDEX_HTML = Path(__file__).resolve().parents[1] / "index.html"


def _function_body(script: str, name: str) -> str:
    match = re.search(rf"async function {name}\([^)]*\) \{{([\s\S]*?)\n  \}}", script)
    if not match:
        raise AssertionError(f"function {name} not found")
    return match.group(1)


class FrontendSendFlowTest(unittest.TestCase):
    def setUp(self):
        self.html = INDEX_HTML.read_text(encoding="utf-8")
        script_match = re.search(r"<script>([\s\S]*?)</script>", self.html)
        self.assertIsNotNone(script_match)
        self.script = script_match.group(1)

    def test_send_shows_user_message_before_session_network_wait(self):
        body = _function_body(self.script, "enviar")

        self.assertLess(body.index("input.value = ''"), body.index("await enviarChatServidor(mensagem)"))
        self.assertLess(body.index("adicionarBolha(mensagem, 'usuario')"), body.index("await enviarChatServidor(mensagem)"))
        self.assertLess(body.index("mostrarDigitando()"), body.index("await enviarChatServidor(mensagem)"))

    def test_send_retries_once_when_session_token_is_invalid(self):
        body = _function_body(self.script, "enviarChatServidor")
        clear_body = re.search(r"function limparSessaoLocal\(\) \{([\s\S]*?)\n  \}", self.script).group(1)

        self.assertIn("response.status === 403", body)
        self.assertIn("limparSessaoLocal()", body)
        self.assertIn("sessionStorage.removeItem('chat_session_id')", clear_body)
        self.assertIn("await criarSessaoServidor()", body)


if __name__ == "__main__":
    unittest.main()
