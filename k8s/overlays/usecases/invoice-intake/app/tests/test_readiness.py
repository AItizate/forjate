import httpx
import pytest

from invoice_intake import batch, readiness


def test_wait_ready_polls_until_the_service_answers(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200)

    monkeypatch.setattr(readiness.httpx, "get", fake_get)
    monkeypatch.setattr("time.sleep", lambda s: None)
    readiness.wait_ready("http://erp", "ERP stub")
    assert calls["n"] == 3


def test_wait_ready_gives_up_naming_the_service(monkeypatch):
    monkeypatch.setattr(readiness.httpx, "get", lambda url, timeout: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(readiness.NotReady, match="ERP stub"):
        readiness.wait_ready("http://erp", "ERP stub", timeout_s=0)


def test_the_batch_waits_for_the_erp_stub_before_its_first_request(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(batch, "wait_ready", lambda url, what, timeout_s=180.0: seen.append(url))
    monkeypatch.setattr(batch, "docling_ready", lambda: seen.append("docling"))
    monkeypatch.setattr(batch.stores, "ensure_schema", lambda: None)
    monkeypatch.setattr(batch.stores, "labels", lambda: {})
    monkeypatch.setattr(batch.stores, "minio_client", lambda: object())
    monkeypatch.setattr(batch.stores, "list_objects", lambda *a, **k: [])
    monkeypatch.setattr(batch, "model_for", lambda cfg, labels=None: object())
    batch.run_once()
    assert batch.settings().erp_url in seen
