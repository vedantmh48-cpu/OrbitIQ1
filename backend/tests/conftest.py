"""Shared pytest fixtures: isolated app + test client."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def db_env(tmp_path, monkeypatch):
    """Point storage at a fresh temp dir + local JSON mode for each test."""
    data_dir = tmp_path / "testdata"
    data_dir.mkdir(exist_ok=True)
    monkeypatch.setattr("app.config.settings.DATA_DIR", data_dir)
    monkeypatch.setattr("app.config.settings.LOCAL_DB_FILE", data_dir / "local_db.json")
    monkeypatch.setattr("app.config.settings.SEED_FLAG_FILE", data_dir / ".seeded")
    monkeypatch.setattr("app.config.settings.LOG_FILE", data_dir / "satquery.log")
    monkeypatch.setattr("app.config.settings.DB_MODE", "off")
    # Force the legacy (compat) auth backend + in-memory session cache so the
    # suite never probes for PostgreSQL/Redis.
    monkeypatch.setattr("app.config.settings.AUTH_STORE", "compat")
    monkeypatch.setattr("app.config.settings.REDIS_ENABLED", "off")
    # Auth-flow tests assert the local ``demo_code``/``demo_reset_link`` OTP
    # fallback, which only activates when SMTP is NOT configured. Pin mail off
    # here so the suite is hermetic regardless of any real credentials a
    # developer has in their local .env; the mailer's own behaviour is covered
    # separately by test_mail.py (which stubs the socket and configures SMTP
    # explicitly per-test).
    monkeypatch.setattr("app.config.settings.MAIL_MODE", "off", raising=False)
    monkeypatch.setattr("app.config.settings.SMTP_HOST", "", raising=False)
    monkeypatch.setattr("app.config.settings.SMTP_USERNAME", "", raising=False)
    monkeypatch.setattr("app.config.settings.SMTP_PASSWORD", "", raising=False)
    from app.storage import reset_db_for_tests
    from app.auth_store import reset_auth_store_for_tests
    from app.session_cache import reset_session_cache_for_tests
    from app.middleware import reset_rate_limit_for_tests

    reset_auth_store_for_tests()
    reset_session_cache_for_tests()
    reset_rate_limit_for_tests()
    reset_db_for_tests()
    yield


@pytest.fixture()
def client(db_env):
    from app.main import app  # noqa: F401

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client):
    """Register + refresh tokens for a fresh user."""
    email = "itest@satquery.ai"
    password = "Password1"
    r = client.post(
        "/api/auth/register",
        json={
            "name": "Integration Tester",
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}