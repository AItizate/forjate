"""Contract layer: the code against the records. Reads .builder/ next to app/ when present, as it is in the factory; an app repo on its
own skips what it cannot read. The markers are checked so that the gates' eval, injection and redaction checks cannot skip."""

from __future__ import annotations

import inspect
import re
import typing
from pathlib import Path

import pytest
import yaml

from invoice_intake.tools import TOOLS
from invoice_intake.verify import ASSERTIONS

APP = Path(__file__).resolve().parents[1]
BUILDER = APP.parent / ".builder"
TOOL_LINE = re.compile(r"^(?P<name>[a-z_]+):[^\[]*(\[(?P<flags>[^\]]*)\])?\s*$")


def _record(name: str) -> dict:
    path = BUILDER / "decisions" / f"{name}.yaml"
    if not path.is_file():
        pytest.skip(f"{name} record not next to this app")
    return yaml.safe_load(path.read_text())


def _tool_lines() -> dict[str, set[str]]:
    tools: dict[str, set[str]] = {}
    for stage in _record("ai-engineering")["spec"]["stages"].values():
        for line in stage["settings"].get("tools") or []:
            match = TOOL_LINE.match(line)
            assert match, line
            flags = {f.strip().lower() for f in (match.group("flags") or "").split(",") if f.strip()}
            tools.setdefault(match.group("name"), set()).update(flags)
    return tools


def test_every_tool_of_the_record_has_a_module_and_nothing_more() -> None:
    assert set(_tool_lines()) == set(TOOLS)


def test_flags_are_signatures() -> None:
    for name, flags in _tool_lines().items():
        params = inspect.signature(TOOLS[name].fn).parameters
        assert ("approval_token" in params) == any("approval token" in f for f in flags), name
        assert ("idempotency_key" in params) == ("idempotent" in flags), name
        if "read-only" in flags:
            assert "approval_token" not in params and "idempotency_key" not in params, name
        if "requires deterministic check result" in flags:
            assert "check_result" in params, name
        assert "timeout_s" in params, name
        for keyword in ("approval_token", "idempotency_key", "timeout_s"):
            if keyword in params:
                assert params[keyword].kind is inspect.Parameter.KEYWORD_ONLY, f"{name}: {keyword}"


def test_tools_are_typed_in_and_out() -> None:
    for tool in TOOLS.values():
        hints = typing.get_type_hints(tool.fn)
        assert hints["args"] is tool.args_model and hints["return"] is tool.result_model, tool.name


def test_tool_modules_are_named_after_the_tool() -> None:
    for tool in TOOLS.values():
        assert tool.fn.__module__ == f"invoice_intake.tools.{tool.name}"


def test_every_verify_assertion_of_the_record_exists_as_a_named_check() -> None:
    assert list(ASSERTIONS) == _record("quality")["spec"]["stages"]["crawl"]["settings"]["verify_assertions"]


def test_bounds_defaults_match_the_record() -> None:
    from invoice_intake.config import Settings
    bounds = dict(b.split("=") for b in _record("ai-engineering")["spec"]["stages"]["crawl"]["settings"]["execution_bounds"])
    s = Settings()
    assert (str(s.max_steps), str(int(s.step_timeout_s)), str(s.delegation_depth), str(s.budget_tokens)) == (
        bounds["max_steps"], bounds["step_timeout_s"], bounds["delegation_depth"], bounds["budget_tokens"])


def test_the_model_of_the_record_is_the_default() -> None:
    from invoice_intake.config import Settings
    assert Settings().model_id == _record("ai-engineering")["spec"]["stages"]["crawl"]["settings"]["model"]


def test_scaffold_yaml_matches_the_code() -> None:
    path = BUILDER / "scaffold.yaml"
    if not path.is_file():
        pytest.skip("scaffold.yaml not next to this app")
    spec = yaml.safe_load(path.read_text())["spec"]
    assert {t["name"] for t in spec["tools"]} == set(TOOLS)
    verify = next(w for w in spec["workloads"] if w.get("phase") == "verify")
    assert verify["name"] == _record("quality")["spec"]["stages"]["crawl"]["settings"]["verify_job"]
    assert "MODEL_MODE=replay" in verify["env"]
    assert spec["model_modes"][0] in ("replay", "rules")


@pytest.mark.parametrize("marker", ["eval", "injection", "redaction"])
def test_the_gate_markers_exist_so_their_checks_cannot_skip(marker: str) -> None:
    source = "\n".join(p.read_text() for p in (APP / "tests").rglob("test_*.py") if p.name != "test_contract.py")
    assert f"pytest.mark.{marker}" in source
