from fastapi.testclient import TestClient

from support_copilot import orders_stub


def client(monkeypatch, recorded, down=False):
    def execute(sql, *params):
        if down:
            raise ConnectionError("postgres is away")
        recorded.append(params)
        return 1

    monkeypatch.setattr(orders_stub.stores, "execute", execute)
    monkeypatch.setattr(orders_stub.stores, "query", lambda sql, *p: [])
    return TestClient(orders_stub.app, raise_server_exceptions=False)


def test_liveness_does_not_depend_on_postgres(monkeypatch):
    recorded: list = []
    c = client(monkeypatch, recorded, down=True)
    assert c.get("/healthz").status_code == 200
    assert recorded == []


def test_probes_are_not_recorded_as_orders_api_calls(monkeypatch):
    recorded: list = []
    c = client(monkeypatch, recorded)
    c.get("/healthz")
    assert recorded == []


def test_api_calls_are_still_recorded(monkeypatch):
    recorded: list = []
    c = client(monkeypatch, recorded)
    assert c.get("/orders/ZZ-1").status_code == 404
    assert c.post("/orders/ZZ-1").status_code == 405
    assert recorded == [("GET", "/orders/ZZ-1"), ("POST", "/orders/ZZ-1")]
