import httpx
import pytest

from support_copilot import replay


class Cfg:
    agent_url = "http://agent"
    orders_url = "http://orders"


def test_replay_waits_for_the_orders_api_not_only_the_agent(monkeypatch):
    seen: list[str] = []
    orders_up_after = {"calls": 0}

    def fake_get(url, timeout):
        seen.append(url)
        if url.startswith("http://orders"):
            orders_up_after["calls"] += 1
            if orders_up_after["calls"] < 3:
                raise httpx.ConnectError("connection refused")
        return httpx.Response(200)

    monkeypatch.setattr(replay.httpx, "get", fake_get)
    monkeypatch.setattr("time.sleep", lambda s: None)
    replay.wait_agent(Cfg())
    assert seen[0] == "http://agent/readyz"
    assert seen.count("http://orders/readyz") == 3


def test_replay_gives_up_when_the_orders_api_never_comes_up(monkeypatch):
    monkeypatch.setattr(replay.httpx, "get", lambda url, timeout: httpx.Response(200) if "agent" in url else (_ for _ in ()).throw(httpx.ConnectError("refused")))
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="orders API"):
        replay.wait_agent(Cfg(), timeout_s=0)
