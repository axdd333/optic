import unittest
from unittest import mock

from ctxorg import ollama


class ProviderRoutingTest(unittest.TestCase):
    def test_model_resolution_is_backward_compatible(self):
        cfg = {"model": "m-main", "fast_model": "m-fast", "chat_model": "m-chat"}
        self.assertEqual(ollama.pick_model(cfg, "chat", ""), "m-chat")
        self.assertEqual(ollama.pick_model(cfg, "home", ""), "m-fast")
        self.assertEqual(ollama.pick_model(cfg, "infer", ""), "m-main")

    def test_provider_order_respects_feature_and_fallback(self):
        cfg = {
            "provider_mode": "mirofish",
            "mirofish_url": "http://mf",
            "provider_fallback_ollama": True,
        }
        self.assertEqual(ollama.providers(cfg, "infer"),
                         ["mirofish", "ollama"])

        cfg = {
            "provider_mode": "mirofish",
            "mirofish_url": "",
            "provider_fallback_ollama": True,
        }
        self.assertEqual(ollama.providers(cfg, "infer"), ["ollama"])

        cfg = {
            "provider_mode": "ollama",
            "chat_provider": "mirofish",
            "mirofish_url": "http://mf",
            "provider_fallback_ollama": False,
            "provider_fallback": "mirofish",
        }
        self.assertEqual(ollama.providers(cfg, "chat"), ["mirofish"])

    def test_json_generation_falls_back_to_ollama(self):
        cfg = {
            "model": "m-main",
            "llm_timeout_sec": 5,
            "num_ctx": 1024,
            "provider_mode": "mirofish",
            "mirofish_url": "http://mf",
            "provider_fallback_ollama": True,
            "ollama_url": "http://ollama",
        }
        with mock.patch("ctxorg.ollama.mirofish.gen_json",
                        side_effect=RuntimeError("down")):
            with mock.patch("ctxorg.ollama.ollama_json",
                            return_value={"ok": True}) as raw:
                out = ollama.gen(cfg, "x", feature="infer")
        self.assertTrue(out["ok"])
        self.assertEqual(raw.call_count, 1)

    def test_stream_falls_back_when_mirofish_fails_early(self):
        cfg = {
            "model": "m-main",
            "fast_model": "m-fast",
            "llm_timeout_sec": 5,
            "num_ctx": 1024,
            "provider_mode": "mirofish",
            "mirofish_url": "http://mf",
            "provider_fallback_ollama": True,
            "ollama_url": "http://ollama",
        }
        with mock.patch("ctxorg.ollama.mirofish.stream_chat",
                        side_effect=RuntimeError("down")):
            with mock.patch("ctxorg.ollama.ollama_stream",
                            return_value=iter([{"message": {"content": "ok"},
                                                "done": True}])):
                rows = list(ollama.stream_chat(cfg, [{"role": "user", "content": "q"}],
                                              feature="iris"))
        self.assertEqual(rows[-1].get("done"), True)


if __name__ == "__main__":
    unittest.main()
