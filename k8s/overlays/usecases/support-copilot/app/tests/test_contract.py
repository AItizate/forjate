"""Contract: every tool line of the AI-engineering record has a module with the declared flags."""

import re
from pathlib import Path

import pytest
import yaml

from support_copilot.tools import TOOLS

RECORD = Path(__file__).resolve().parents[2] / ".builder" / "decisions" / "ai-engineering.yaml"
LINE = re.compile(r"^(?P<name>[a-z_]+):.*?(\[(?P<flags>[^\]]*)\])?$")


@pytest.mark.skipif(not RECORD.is_file(), reason="no AI-engineering record next to the app")
def test_every_record_tool_exists_with_its_flags():
    d = yaml.safe_load(RECORD.read_text())
    for stage in d["spec"]["stages"].values():
        for line in stage.get("settings", {}).get("tools", []):
            m = LINE.match(line)
            assert m and m.group("name") in TOOLS, line
            for flag in (m.group("flags") or "").split(","):
                flag = flag.strip()
                if flag:
                    assert any(flag in f for f in TOOLS[m.group("name")].flags), f"{m.group('name')}: flag {flag!r} not implemented"
