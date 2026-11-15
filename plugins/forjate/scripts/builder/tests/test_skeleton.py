"""The walking skeleton (#44): scaffold-check's skeleton contract and the backlog derived from it.

The fixture `fixtures/skeleton/parcel-claims` is the shape app-scaffold writes since #44: every workload of
every stage in scope has an entry point, every seam carries its marker, the verify Job connects the Crawl
seams and reads the strict switch, and `.builder/backlog.yaml` is what backlog.py derives. Each case breaks
a copy the way a careless scaffold would and asserts the finding names it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BUILDER = HERE.parent
FIXTURE = HERE / "fixtures" / "skeleton" / "parcel-claims"

sys.path.insert(0, str(BUILDER))
from validate import backlog_findings  # noqa: E402


def copy(tmp_path: Path) -> Path:
    dst = tmp_path / "parcel-claims"
    shutil.copytree(FIXTURE, dst, ignore=shutil.ignore_patterns("__pycache__", ".venv*", "*.egg-info"))
    return dst


def findings(uc: Path) -> list[str]:
    p = subprocess.run([sys.executable, str(BUILDER / "scaffold-check.py"), str(uc), "--json"], capture_output=True, text=True)
    return json.loads(p.stdout)


def skeleton(found: list[str]) -> list[str]:
    return [f for f in found if f.startswith("skeleton:")]


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, f"{path.name}: fixture drifted, {old!r} not found"
    path.write_text(text.replace(old, new, 1))


def scaffold(uc: Path) -> dict:
    return yaml.safe_load((uc / ".builder/scaffold.yaml").read_text())


def save(uc: Path, doc: dict) -> None:
    (uc / ".builder/scaffold.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))


def backlog(uc: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(BUILDER / "backlog.py"), str(uc), *flags], capture_output=True, text=True)


# ------------------------------------------------------------------------------------------- scaffold-check
def test_fixture_skeleton_is_clean(tmp_path: Path):
    assert findings(copy(tmp_path)) == []


def test_a_walk_workload_without_an_entry_point_is_named(tmp_path: Path):
    """#28's scaffold stopped at Crawl: the Walk workloads of the record had nowhere to land."""
    uc = copy(tmp_path)
    doc = scaffold(uc)
    doc["spec"]["workloads"] = [w for w in doc["spec"]["workloads"] if w["name"] != "review-api"]
    save(uc, doc)
    assert any("review-api is in the architecture record at walk but has no entry point" in f for f in skeleton(findings(uc)))


def test_a_workload_at_the_wrong_stage_is_named(tmp_path: Path):
    uc = copy(tmp_path)
    edit(uc / ".builder/scaffold.yaml", "name: review-api, kind: deployment, stage: walk", "name: review-api, kind: deployment, stage: crawl")
    assert any("review-api has stage crawl but the architecture record first lists review-api at walk" in f for f in skeleton(findings(uc)))


def test_a_tool_that_is_not_a_seam_is_named(tmp_path: Path):
    uc = copy(tmp_path)
    doc = scaffold(uc)
    doc["spec"]["skeleton"]["seams"] = [s for s in doc["spec"]["skeleton"]["seams"] if s["name"] != "file_claim"]
    save(uc, doc)
    assert any("tool file_claim is not a seam" in f for f in skeleton(findings(uc)))


def test_a_tool_at_the_wrong_stage_is_named(tmp_path: Path):
    uc = copy(tmp_path)
    edit(uc / ".builder/scaffold.yaml", "flags: [idempotent, requires approval token], stage: walk", "flags: [idempotent, requires approval token], stage: crawl")
    assert any("tool file_claim has stage crawl" in f for f in skeleton(findings(uc)))


def test_a_seam_without_its_marker_is_named(tmp_path: Path):
    uc = copy(tmp_path)
    edit(uc / "app/src/parcel_claims/tools/file_claim.py", "# SEAM claim-filing:", "#")
    assert any("seam claim-filing: no `SEAM claim-filing` marker" in f for f in skeleton(findings(uc)))


def test_a_seam_whose_contract_module_is_missing_is_named(tmp_path: Path):
    uc = copy(tmp_path)
    (uc / "app/src/parcel_claims/review_api.py").unlink()
    found = findings(uc)
    assert any("seam review-surface: contract module parcel_claims/review_api.py does not exist" in f for f in found), found


def test_a_diagram_that_leaves_a_part_out_is_named(tmp_path: Path):
    uc = copy(tmp_path)
    edit(uc / "app/docs/connections.md", "  review-api -.->|review-surface, walk| claims-run\n", "")
    assert any("the connection diagram does not name review-api, review-surface" in f for f in skeleton(findings(uc)))


def test_a_missing_diagram_is_named(tmp_path: Path):
    uc = copy(tmp_path)
    (uc / "app/docs/connections.md").unlink()
    assert any("connection diagram app/docs/connections.md does not exist" in f for f in skeleton(findings(uc)))


def test_a_verify_that_skips_a_crawl_seam_is_named(tmp_path: Path):
    uc = copy(tmp_path)
    edit(uc / "app/src/parcel_claims/verify.py", '    check("connected: damage-classifier", all(first.values()))\n', "")
    assert any("never checks the wired Crawl seam(s) damage-classifier" in f for f in skeleton(findings(uc)))


def test_a_verify_without_the_strict_switch_is_named(tmp_path: Path):
    """Without the switch, Walk's 'minimal implementation' criterion has nothing to fail."""
    uc = copy(tmp_path)
    edit(uc / "app/src/parcel_claims/verify.py", 'os.environ.get("VERIFY_STRICT", "0")', 'os.environ.get("STRICTNESS", "0")')
    assert any("never reads VERIFY_STRICT" in f for f in skeleton(findings(uc)))


def test_unknown_seams_and_gates_are_named(tmp_path: Path):
    uc = copy(tmp_path)
    doc = scaffold(uc)
    sk = doc["spec"]["skeleton"]
    sk["verify"]["pending"][0]["seams"] = ["po-matching"]
    sk["workarounds"][0]["seam"] = "nowhere"
    sk["seams"][0]["gates"] = ["G-AI-9"]
    save(uc, doc)
    found = skeleton(findings(uc))
    assert any("names unknown seam(s) po-matching" in f for f in found), found
    assert any("workaround names unknown seam nowhere" in f for f in found), found
    assert any("seam shipment-lookup names gate(s) G-AI-9" in f for f in found), found


def test_a_legacy_full_app_skips_the_skeleton_checks(tmp_path: Path):
    """The goldens predate #44 (#46 regenerates them): without spec.skeleton only the old checks run."""
    uc = copy(tmp_path)
    doc = scaffold(uc)
    del doc["spec"]["skeleton"]
    save(uc, doc)
    assert skeleton(findings(uc)) == []


# ------------------------------------------------------------------------------------------------ backlog
def test_committed_backlog_is_what_backlog_py_derives():
    p = backlog(FIXTURE, "--check")
    assert p.returncode == 0, p.stdout + p.stderr


def test_backlog_has_a_ticket_per_seam_linked_to_record_and_gate(tmp_path: Path):
    uc = copy(tmp_path)
    assert backlog(uc).returncode == 0
    doc = yaml.safe_load((uc / ".builder/backlog.yaml").read_text())
    tickets = {t["id"]: t for t in doc["spec"]["tickets"]}
    seams = scaffold(uc)["spec"]["skeleton"]["seams"]
    for s in seams:
        t = tickets[f"T-{s['id']}"]
        assert t["record"].startswith(s["record"])
        assert t["gates"], t
        assert any(f"SEAM {s['id']}" in a for a in t["acceptance"])
    # file_claim: the walk tool line, its gate's text verbatim as acceptance
    assert tickets["T-claim-filing"]["record"] == "decisions/ai-engineering.yaml#stages.walk.settings.tools"
    assert "no claim reaches the carrier without the clerk's approval token" in tickets["T-claim-filing"]["acceptance"]
    # Crawl's seams are due at Walk: Walk closes with the minimal implementation
    assert {t["stage"] for t in tickets.values()} == {"walk"}
    # the pending assertion depends on the seam that will make it true, and links the verify gate
    assert tickets["T-assert-1"]["depends_on"] == ["T-damage-classifier"]
    assert tickets["T-assert-1"]["gates"] == ["G-Q-1"]
    assert "T-wa-shipment-lookup" in tickets and "T-open-1" in tickets
    assert (uc / ".builder/backlog.md").read_text().count("## T-") == len(tickets)
    assert backlog_findings(uc / ".builder", yaml.safe_load((uc / ".builder/gates.yaml").read_text())) == []


def test_backlog_inherits_the_area_gates_when_a_seam_names_none(tmp_path: Path):
    uc = copy(tmp_path)
    doc = scaffold(uc)
    for s in doc["spec"]["skeleton"]["seams"]:
        s.pop("gates", None)
    save(uc, doc)
    backlog(uc)
    tickets = {t["id"]: t for t in yaml.safe_load((uc / ".builder/backlog.yaml").read_text())["spec"]["tickets"]}
    assert tickets["T-claim-filing"]["gates"] == ["G-AI-2"]       # ai-engineering at walk->run
    assert tickets["T-review-surface"]["gates"] == ["G-ARCH-2"]   # architecture at walk->run


def test_a_later_stage_workload_without_a_seam_gets_a_ticket(tmp_path: Path):
    uc = copy(tmp_path)
    doc = scaffold(uc)
    doc["spec"]["skeleton"]["seams"] = [s for s in doc["spec"]["skeleton"]["seams"] if s["id"] != "review-surface"]
    save(uc, doc)
    backlog(uc)
    tickets = {t["id"]: t for t in yaml.safe_load((uc / ".builder/backlog.yaml").read_text())["spec"]["tickets"]}
    t = tickets["T-wl-review-api"]
    assert t["contract"] == "app/src/parcel_claims/review_api.py" and t["gates"] == ["G-ARCH-2"]


def test_backlog_is_deterministic_and_check_catches_drift(tmp_path: Path):
    uc = copy(tmp_path)
    backlog(uc)
    first = (uc / ".builder/backlog.yaml").read_text()
    backlog(uc)
    assert (uc / ".builder/backlog.yaml").read_text() == first
    edit(uc / ".builder/scaffold.yaml", "summary: read the shipment the report names", "summary: read the shipment and its events")
    assert backlog(uc, "--check").returncode == 1


def test_backlog_refuses_a_legacy_full_app(tmp_path: Path):
    uc = copy(tmp_path)
    doc = scaffold(uc)
    del doc["spec"]["skeleton"]
    save(uc, doc)
    p = backlog(uc)
    assert p.returncode == 2 and "legacy full app" in p.stdout


def test_validator_names_tickets_that_point_nowhere(tmp_path: Path):
    uc = copy(tmp_path)
    b = uc / ".builder"
    doc = yaml.safe_load((b / "backlog.yaml").read_text())
    doc["spec"]["tickets"][0]["seam"] = "ghost"
    doc["spec"]["tickets"][0]["gates"] = ["G-Q-9"]
    doc["spec"]["tickets"][1]["depends_on"] = ["T-nothing"]
    (b / "backlog.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
    errs = backlog_findings(b, yaml.safe_load((b / "gates.yaml").read_text()))
    assert any("names seam ghost" in e for e in errs), errs
    assert any("names gate G-Q-9" in e for e in errs), errs
    assert any("depends on unknown ticket T-nothing" in e for e in errs), errs


def test_backlog_and_skeleton_checks_name_no_component():
    """Facts about components come from the catalog; the backlog only reads the records and the scaffold."""
    for f in ("backlog.py",):
        assert not re.search(r"[\"']apps/", (BUILDER / f).read_text())
