import pytest


def test_backfill_cli_refuses_remote_writes_before_connecting(monkeypatch):
    from backend.app.config import Settings
    from scripts import backfill_local_features

    settings = Settings(
        _env_file=None,
        database_url="postgresql://example.invalid/findiu",
        jwt_secret="test-only-secret-with-at-least-32-characters",
        storage_provider="local",
    )
    monkeypatch.setattr(backfill_local_features, "Settings", lambda: settings)
    with pytest.raises(SystemExit) as error:
        backfill_local_features.main(["--apply"])
    assert error.value.code == 2


def test_backfill_cli_refuses_nonpositive_batches_before_connecting():
    from scripts.backfill_local_features import main

    with pytest.raises(SystemExit) as error:
        main(["--limit", "0"])
    assert error.value.code == 2
