"""ZEABUR-1: DATA_DIR-relative defaults for DATABASE_URL / UPLOAD_DIR.

app/config.py's Settings._resolve_data_dependent_defaults should only
redirect the sqlite DB path / upload dir under DATA_DIR when DATA_DIR is
actually usable (exists + writable) *and* the deployer didn't already set
DATABASE_URL / UPLOAD_DIR explicitly. Every other test in this suite relies
on the fallback-to-local behavior (DATA_DIR=/data essentially never exists
in CI/dev/test sandboxes), so this file focuses on exercising both branches
directly against a tmp_path standing in for a real mounted volume.
"""

from __future__ import annotations


async def test_database_url_falls_back_to_local_when_data_dir_missing(monkeypatch, tmp_path):
    from app.config import Settings

    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("DATA_DIR", str(missing))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("UPLOAD_DIR", raising=False)

    settings = Settings()
    assert settings.database_url == "sqlite+aiosqlite:///./openmailroom.db"
    assert settings.database_url.endswith("openmailroom.db")
    assert str(missing) not in settings.database_url


async def test_database_url_and_upload_dir_use_data_dir_when_usable(monkeypatch, tmp_path):
    from app.config import Settings

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("UPLOAD_DIR", raising=False)

    settings = Settings()
    assert settings.database_url == f"sqlite+aiosqlite:///{data_dir}/openmailroom.db"
    assert settings.upload_dir == f"{data_dir}/uploads"


async def test_explicit_database_url_always_wins_over_data_dir(monkeypatch, tmp_path):
    from app.config import Settings

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./explicit.db")
    monkeypatch.delenv("UPLOAD_DIR", raising=False)

    settings = Settings()
    assert settings.database_url == "sqlite+aiosqlite:///./explicit.db"
    # upload_dir is independent of database_url and should still redirect.
    assert settings.upload_dir == f"{data_dir}/uploads"


async def test_explicit_upload_dir_always_wins_over_data_dir(monkeypatch, tmp_path):
    from app.config import Settings

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    custom_upload = tmp_path / "custom-uploads"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("UPLOAD_DIR", str(custom_upload))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings()
    assert settings.upload_dir == str(custom_upload)
    assert settings.database_url == f"sqlite+aiosqlite:///{data_dir}/openmailroom.db"


async def test_serve_frontend_and_frontend_dist_defaults(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("SERVE_FRONTEND", raising=False)
    monkeypatch.delenv("FRONTEND_DIST", raising=False)

    settings = Settings()
    assert settings.serve_frontend is True
    assert settings.frontend_dist == "/app/frontend_dist"


async def test_serve_frontend_can_be_disabled_via_env(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("SERVE_FRONTEND", "0")
    settings = Settings()
    assert settings.serve_frontend is False


async def test_port_default_and_override(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("PORT", raising=False)
    assert Settings().port == 8080

    monkeypatch.setenv("PORT", "9000")
    assert Settings().port == 9000
