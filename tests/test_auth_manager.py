from src.a2a.security import AuthManager
from src.llm_providers.config import get_config_manager


def test_auth_manager_uses_config_secret(tmp_path, monkeypatch):
    # Point config to a temp dir
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cm = get_config_manager()
    cm.set_a2a_secret("super-secret")

    auth = AuthManager()
    token = auth.issue_token("agent-x")
    assert auth.verify("agent-x", token)


def test_roles_are_persistent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cm = get_config_manager()
    cm.set_a2a_secret("super-secret")
    cm.set_agent_role("agent-y", "coordinator")

    auth = AuthManager()
    assert auth.has_role("agent-y", "coordinator")


