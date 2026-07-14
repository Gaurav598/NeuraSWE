from app.github import webhook


def test_verify_signature_rejects_missing_secret_in_production(monkeypatch):
    monkeypatch.setattr(webhook.settings, "node_env", "production")
    monkeypatch.setattr(webhook.settings, "github_webhook_secret", "")

    assert webhook.verify_signature(b"{}", None) is False


def test_verify_signature_allows_missing_secret_outside_production(monkeypatch):
    monkeypatch.setattr(webhook.settings, "node_env", "development")
    monkeypatch.setattr(webhook.settings, "github_webhook_secret", "")

    assert webhook.verify_signature(b"{}", None) is True
