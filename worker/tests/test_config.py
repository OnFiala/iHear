import pytest

from ihear_worker.config import Settings


def _required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-only")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ASTRA_MODEL", "another-model"),
        ("ASTRA_REASONING_EFFORT", "high"),
        ("WORKER_CONCURRENCY", "2"),
        ("REPORT_VERSION", "2"),
    ],
)
def test_fixed_runtime_contract_rejects_misleading_overrides(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str,
) -> None:
    _required(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match=name):
        Settings.from_env()


def test_fixed_runtime_contract_accepts_documented_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _required(monkeypatch)
    monkeypatch.setenv("ASTRA_MODEL", "gpt-6-astra")
    monkeypatch.setenv("ASTRA_REASONING_EFFORT", "low")
    monkeypatch.setenv("WORKER_CONCURRENCY", "1")
    settings = Settings.from_env()
    assert settings.worker_id
    assert settings.report_version == 4
