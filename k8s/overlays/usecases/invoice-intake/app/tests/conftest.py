"""A Crawl environment in memory: the stubs' real ASGI apps, the tools' real code, memory stores and a parser that returns each seeded
PDF's text. The real parser, Postgres and MinIO run only on the cluster."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace

import pytest
from fastapi.testclient import TestClient

from invoice_intake import config, odoo_stub, shared_imap_mailbox_stub, toolkit
from invoice_intake.config import TOOL_CREDENTIAL_ENV, Settings
from invoice_intake.double_store import MemoryKV
from invoice_intake.generator import SeedSet, golden_set, injection_set, verify_set
from invoice_intake.model import ReplayModel, RulesModel
from invoice_intake.objects import MemoryObjects, read_label
from invoice_intake.parser import ParseFailed
from invoice_intake.pipeline import Ctx
from invoice_intake.seed import deliver, seed_odoo
from invoice_intake.store import MemoryStore

TOKEN = "test-token"
TEST_SETTINGS = Settings(workload="test", bank_hash_salt="test-salt", admin_token=TOKEN, credentials={t: TOKEN for t in TOOL_CREDENTIAL_ENV})


class SeedParser:
    """Returns the text each seeded PDF renders; the corrupt one fails the way a real parser does."""

    def __init__(self, *seeds: SeedSet) -> None:
        self.calls = 0
        self.texts = {item.content: item.text for seed in seeds for item in seed.items}

    def parse(self, filename: str, content: bytes) -> str:
        self.calls += 1
        text = self.texts.get(content)
        if text is None:
            raise ParseFailed("docling status failure")
        return text


@dataclass
class Env:
    settings: Settings
    store: MemoryStore
    objects: MemoryObjects
    parser: SeedParser
    odoo_kv: MemoryKV
    mailbox_kv: MemoryKV

    def ctx(self, mode: str = "replay", **overrides: object) -> Ctx:
        settings = replace(self.settings, **overrides) if overrides else self.settings
        config.set_settings(settings)
        if mode == "rules":
            model = RulesModel()
        else:
            model = ReplayModel(lambda sha: read_label(self.objects, settings.source_scope, sha))
        return Ctx(settings, self.store, self.objects, self.parser, model)


@pytest.fixture(autouse=True)
def clean_globals(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in list(TOOL_CREDENTIAL_ENV.values()) + ["DOUBLE_ADMIN_TOKEN"]:
        monkeypatch.setenv(name, TOKEN)
    config.set_settings(TEST_SETTINGS)
    yield
    config.set_settings(None)
    toolkit.set_client_factory(None)


@pytest.fixture
def env() -> Env:
    odoo_kv, mailbox_kv = MemoryKV(), MemoryKV()
    clients = {"odoo": TestClient(odoo_stub.create_app(odoo_kv)), "mailbox": TestClient(shared_imap_mailbox_stub.create_app(mailbox_kv))}
    toolkit.set_client_factory(clients.__getitem__)
    environment = Env(TEST_SETTINGS, MemoryStore(), MemoryObjects(), SeedParser(verify_set(), golden_set(), injection_set()), odoo_kv, mailbox_kv)
    seed_odoo(TEST_SETTINGS)
    return environment


@pytest.fixture
def seeded(env: Env) -> Env:
    deliver(verify_set(), "shared", env.objects, env.settings.scope, env.settings)
    return env
