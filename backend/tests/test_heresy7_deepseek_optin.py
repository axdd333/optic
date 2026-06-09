"""
Regression tests for Heresy 7 fix (commit 4e8dd96):
  - DeepSeek is now opt-in only (Invariant #12: Local-First By Default).
  - DEEPSEEK_API_KEY defaults to empty string (was hardcoded key).
  - DEEPSEEK_BASE_URL is configurable via env var.
  - System runs without DeepSeek (iris_audit.py falls back to Ollama/deterministic).
  - start.sh and docker-compose.yml no longer contain hardcoded API keys.

Before the fix:
  - DEEPSEEK_API_KEY defaulted to "sk-ef42d79c0ff64ba9bd21c011638397f6"
  - DEEPSEEK_BASE_URL was hardcoded literal "https://api.deepseek.com/v1"
  - start.sh and docker-compose.yml exported a hardcoded key
After the fix:
  - DEEPSEEK_API_KEY defaults to "" (empty)
  - DEEPSEEK_BASE_URL is os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
  - start.sh exports empty default, docker-compose.yml removed hardcoded key
"""

import os
import sys
import re
from pathlib import Path

import pytest

# Ensure the Optic source tree is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# ---------------------------------------------------------------------------
# UNIT TESTS — DEEPSEEK_API_KEY default
# ---------------------------------------------------------------------------

class TestDeepSeekApiKeyDefault:
    """DEEPSEEK_API_KEY must default to empty string, NOT a hardcoded key."""

    def test_server_py_default_api_key_is_empty(self):
        """server.py must have: DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')"""
        server_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "optic" / "v1" / "server.py"
        )
        content = server_path.read_text()

        # Should contain the correct assignment
        assert 'os.environ.get("DEEPSEEK_API_KEY", "")' in content or \
               "os.environ.get('DEEPSEEK_API_KEY', '')" in content, \
               "DEEPSEEK_API_KEY must default to empty string"

        # Should NOT contain old hardcoded key pattern
        assert "sk-ef42d79c0ff64ba9bd21c011638397f6" not in content, \
               "server.py must not contain the old hardcoded DeepSeek key"

    def test_iris_audit_py_default_api_key_is_empty(self):
        """iris_audit.py must check os.environ.get('DEEPSEEK_API_KEY', '')"""
        iris_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "optic" / "v1" / "iris_audit.py"
        )
        content = iris_path.read_text()

        # DeepSeek methods should check for empty key
        assert 'os.environ.get("DEEPSEEK_API_KEY", "")' in content or \
               "os.environ.get('DEEPSEEK_API_KEY', '')" in content, \
               "iris_audit.py must check DEEPSEEK_API_KEY defaulting to empty"

        # The _try_deepseek methods should return None when key is empty
        assert "if not key:" in content, \
               "iris_audit.py must return None when no DeepSeek key is set"


class TestDeepSeekBaseUrlConfigurable:
    """DEEPSEEK_BASE_URL must be configurable via env var."""

    def test_server_py_base_url_is_configurable(self):
        server_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "optic" / "v1" / "server.py"
        )
        content = server_path.read_text()
        assert 'os.environ.get("DEEPSEEK_BASE_URL"' in content or \
               "os.environ.get('DEEPSEEK_BASE_URL'" in content, \
               "DEEPSEEK_BASE_URL must be configurable via env var"

    def test_iris_audit_py_base_url_is_configurable(self):
        iris_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "optic" / "v1" / "iris_audit.py"
        )
        content = iris_path.read_text()
        assert 'os.environ.get("DEEPSEEK_BASE_URL"' in content or \
               "os.environ.get('DEEPSEEK_BASE_URL'" in content, \
               "DEEPSEEK_BASE_URL must be configurable via env var"

    def test_base_url_default_is_deepseek_v1(self):
        """Default DEEPSEEK_BASE_URL should be https://api.deepseek.com/v1"""
        server_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "optic" / "v1" / "server.py"
        )
        content = server_path.read_text()
        assert '"https://api.deepseek.com/v1"' in content or \
               "'https://api.deepseek.com/v1'" in content, \
               "Default DEEPSEEK_BASE_URL should be https://api.deepseek.com/v1"


class TestIrisAuditNoDeepSeekKey:
    """When DEEPSEEK_API_KEY is empty, _try_deepseek must return None."""

    def test_try_deepseek_returns_none_without_key(self):
        from optic.v1.iris_audit import IrisAuditChat

        # Ensure no DeepSeek key is set
        saved_key = os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            chat = IrisAuditChat()
            result = chat._try_deepseek("What is this?", "test context")
            assert result is None, (
                "_try_deepseek must return None when DEEPSEEK_API_KEY is empty"
            )
        finally:
            if saved_key is not None:
                os.environ["DEEPSEEK_API_KEY"] = saved_key

    def test_try_deepseek_messages_returns_none_without_key(self):
        from optic.v1.iris_audit import IrisAuditChat

        saved_key = os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            chat = IrisAuditChat()
            messages = [{"role": "user", "content": "Hello"}]
            result = chat._try_deepseek_messages(messages)
            assert result is None, (
                "_try_deepseek_messages must return None when DEEPSEEK_API_KEY is empty"
            )
        finally:
            if saved_key is not None:
                os.environ["DEEPSEEK_API_KEY"] = saved_key


class TestSystemRunsWithoutDeepSeek:
    """The system must be functional without DeepSeek."""

    def test_iris_audit_chat_has_ollama_fallback(self):
        """IrisAuditChat.ask() must fall back to Ollama (and then deterministic)."""
        from optic.v1.iris_audit import IrisAuditChat

        chat = IrisAuditChat()
        # The ask method chains: deepseek → ollama → fallback
        assert hasattr(chat, "_try_deepseek"), "IrisAuditChat must have _try_deepseek"
        assert hasattr(chat, "_try_ollama"), "IrisAuditChat must have _try_ollama"
        assert hasattr(chat, "_fallback"), "IrisAuditChat must have _fallback"

    def test_deepseek_is_optional_in_ask(self):
        """The ask() docstring should show DeepSeek → Ollama → deterministic chain."""
        from optic.v1.iris_audit import IrisAuditChat
        import inspect

        source = inspect.getsource(IrisAuditChat.ask)
        assert "_try_deepseek" in source
        assert "_try_ollama" in source
        assert "_fallback" in source


# ---------------------------------------------------------------------------
# SCRIPT & CONFIG FILE CHECKS — no hardcoded keys
# ---------------------------------------------------------------------------

class TestStartScriptNoHardcodedKey:
    """start.sh must not hardcode a DeepSeek API key."""

    def test_start_sh_no_hardcoded_key(self):
        start_path = (
            Path(__file__).resolve().parent.parent / "scripts" / "start.sh"
        )
        content = start_path.read_text()
        assert "sk-ef42d79c0ff64ba9bd21c011638397f6" not in content, \
               "start.sh must not contain the old hardcoded DeepSeek API key"

    def test_start_sh_defaults_to_empty(self):
        start_path = (
            Path(__file__).resolve().parent.parent / "scripts" / "start.sh"
        )
        content = start_path.read_text()
        # Should export DEEPSEEK_API_KEY defaulting to empty
        assert 'DEEPSEEK_API_KEY="' in content, "start.sh should export DEEPSEEK_API_KEY"
        # The default should be empty (${DEEPSEEK_API_KEY:-})
        assert '${DEEPSEEK_API_KEY:-}' in content, \
               "start.sh should default DEEPSEEK_API_KEY to empty string"

    def test_start_sh_has_deepseek_base_url(self):
        start_path = (
            Path(__file__).resolve().parent.parent / "scripts" / "start.sh"
        )
        content = start_path.read_text()
        assert 'DEEPSEEK_BASE_URL' in content, \
               "start.sh should export DEEPSEEK_BASE_URL"


class TestDockerComposeNoHardcodedKey:
    """docker-compose.yml must not contain hardcoded DeepSeek key."""

    def test_docker_compose_no_hardcoded_key(self):
        compose_path = (
            Path(__file__).resolve().parent.parent / "docker-compose.yml"
        )
        content = compose_path.read_text()
        assert "sk-ef42d79c0ff64ba9bd21c011638397f6" not in content, \
               "docker-compose.yml must not contain the old hardcoded DeepSeek API key"

    def test_docker_compose_no_deepseek_env_by_default(self):
        compose_path = (
            Path(__file__).resolve().parent.parent / "docker-compose.yml"
        )
        content = compose_path.read_text()
        # DEEPSEEK_API_KEY should NOT be in the environment section of docker-compose
        # (it's opt-in, so no default should be provided)
        lines = content.split("\n")
        in_env = False
        for line in lines:
            if "environment:" in line:
                in_env = True
                continue
            if in_env and line.strip().startswith("-"):
                assert "DEEPSEEK_API_KEY" not in line, (
                    "docker-compose.yml should not set DEEPSEEK_API_KEY by default"
                )
            elif in_env and not line.strip().startswith("-") and not line.strip().startswith("#"):
                in_env = False


class TestEnvExample:
    """.env.example should clearly indicate DeepSeek is opt-in."""

    def test_env_example_has_optin_message(self):
        env_path = (
            Path(__file__).resolve().parent.parent / ".env.example"
        )
        content = env_path.read_text()
        assert "opt-in" in content.lower(), \
               ".env.example should mention DeepSeek is opt-in"
        assert "DEEPSEEK_API_KEY" in content, \
               ".env.example should document DEEPSEEK_API_KEY"
        assert "# DEEPSEEK_API_KEY=" in content or "# DEEPSEEK_API_KEY=sk" in content, \
               ".env.example should have DEEPSEEK_API_KEY commented out (opt-in)"


class TestReadme:
    """README.md should document DeepSeek as opt-in."""

    def test_readme_documents_optin(self):
        readme_path = (
            Path(__file__).resolve().parent.parent / "README.md"
        )
        content = readme_path.read_text()
        assert "opt-in" in content.lower(), \
               "README.md should mention DeepSeek is opt-in"
        assert "local-first" in content.lower(), \
               "README.md should mention local-first"

    def test_readme_no_hardcoded_key(self):
        readme_path = (
            Path(__file__).resolve().parent.parent / "README.md"
        )
        content = readme_path.read_text()
        assert "sk-ef42d79c0ff64ba9bd21c011638397f6" not in content, \
               "README.md must not contain the old hardcoded API key"


class TestSwarmHtml:
    """swarm.html should show Ollama (local) not DeepSeek."""

    def test_swarm_html_shows_ollama_local(self):
        swarm_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "ctxorg" / "static" / "swarm.html"
        )
        content = swarm_path.read_text()
        assert "Ollama (local)" in content, \
               "swarm.html should show 'Ollama (local)' not 'DeepSeek loaded'"
        assert "DeepSeek loaded" not in content, \
               "swarm.html should NOT say 'DeepSeek loaded' anymore"
