"""Static checks of scaffold-check.py on the scaffold's readiness (#41): a replay, seed or verify entrypoint
waits on the /readyz of every service on its route, and every workload with a health_path has a startup probe
in the assembled overlay.

The #21 nightly failed because a replay Job asked the agent API a question the orders stub could not yet
answer, and the Job did not wait for it. Each case mutates a copy of a golden use case the way a careless
scaffold would and asserts the check names the service.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent
BUILDER = HERE.parent
REPO = BUILDER.parents[3]
USECASES = REPO / "k8s" / "overlays" / "usecases"
ASSEMBLE = BUILDER.parent.parent / "skills" / "kustomize" / "scripts" / "assemble.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("scaffold_check_under_test", BUILDER / "scaffold-check.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(BUILDER))
    spec.loader.exec_module(mod)
    return mod


checker = load_checker()
IGNORE = shutil.ignore_patterns(".venv", "__pycache__", "*.egg-info", ".pytest_cache", "*.env")


def copy_usecase(tmp_path: Path, name: str) -> Path:
    dst = tmp_path / name
    shutil.copytree(USECASES / name, dst, ignore=IGNORE)
    return dst


def findings(uc: Path) -> list[str]:
    p = subprocess.run([sys.executable, str(BUILDER / "scaffold-check.py"), str(uc), "--json"], capture_output=True, text=True)
    import json
    return json.loads(p.stdout)


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, f"{path.name}: fixture drifted, {old!r} not found"
    path.write_text(text.replace(old, new, 1))


def readiness(found: list[str]) -> list[str]:
    return [f for f in found if "/readyz" in f or "before it waits" in f]


@pytest.mark.parametrize("name", ["support-copilot", "invoice-intake"])
def test_golden_use_cases_are_clean(tmp_path: Path, name: str):
    assert findings(copy_usecase(tmp_path, name)) == []


# ------------------------------------------------------------------------------------------------ waits
def test_replay_that_forgets_the_orders_stub_is_named(tmp_path: Path):
    """The #21 failure: the agent answers, the orders stub behind it does not yet, the lookup becomes a false escalation."""
    uc = copy_usecase(tmp_path, "support-copilot")
    edit(uc / "app/src/support_copilot/replay.py", '    wait_ready(cfg.orders_url, "orders API", timeout_s)\n', "")
    found = readiness(findings(uc))
    assert any("replay-job (run)" in f and "orders-stub" in f for f in found), found
    # the verify Job runs the replay too, so it is just as exposed
    assert any("copilot-validate (verify)" in f and "orders-stub" in f for f in found), found
    assert not any("agent-api" in f for f in found)


def test_replay_that_waits_for_nothing_names_every_service_on_its_route(tmp_path: Path):
    uc = copy_usecase(tmp_path, "support-copilot")
    edit(uc / "app/src/support_copilot/replay.py", "    wait_agent(cfg)\n", "")
    found = [f for f in readiness(findings(uc)) if "replay-job" in f]
    assert {s for s in ("agent-api", "orders-stub") if any(f"reaches {s}" in f for f in found)} == {"agent-api", "orders-stub"}, found


def test_using_the_url_before_waiting_for_it_is_a_finding(tmp_path: Path):
    uc = copy_usecase(tmp_path, "support-copilot")
    edit(uc / "app/src/support_copilot/replay.py", "    wait_agent(cfg)\n", "    first = httpx.get(f\"{cfg.agent_url}/replay/ping\")\n    wait_agent(cfg)\n")
    found = readiness(findings(uc))
    assert any("run_once uses agent_url" in f and "before it waits for agent-api" in f for f in found), found


def test_invoice_worker_must_wait_for_the_odoo_stub_and_so_must_the_verify_that_reruns_it(tmp_path: Path):
    """The waits sit in one helper the Jobs share: route_checks builds one /readyz check per service, through
    http_ready(url), and each main passes them to wait_ready. Dropping one service's check names it per Job."""
    uc = copy_usecase(tmp_path, "invoice-intake")
    edit(uc / "app/src/invoice_intake/readiness.py", '        "Odoo double": http_ready(f"{settings.odoo_url}/readyz"),\n', "")
    found = readiness(findings(uc))
    assert any("worker (run)" in f and "odoo-stub" in f for f in found), found
    assert any("invoice-intake-verify (verify)" in f and "odoo-stub" in f for f in found), found
    assert not any("shared-imap-mailbox-stub" in f for f in found), found


def test_a_url_a_job_lists_but_never_uses_is_not_on_its_route(tmp_path: Path):
    uc = copy_usecase(tmp_path, "support-copilot")
    sc = uc / ".builder" / "scaffold.yaml"
    d = yaml.safe_load(sc.read_text())
    seed = next(w for w in d["spec"]["workloads"] if w["name"] == "copilot-seed")
    seed["env"].append("ORDERS_URL=http://orders-stub:8001")
    sc.write_text(yaml.safe_dump(d, sort_keys=False))
    assert findings(uc) == []


def test_components_the_app_only_calls_are_out_of_scope(tmp_path: Path):
    """Docling and Ollama are catalog components, not scaffold workloads: the check names no component."""
    uc = copy_usecase(tmp_path, "invoice-intake")
    edit(uc / "app/src/invoice_intake/readiness.py", '        checks["docling"] = lambda: docling_ready(settings.docling_url)\n', "        pass\n")
    assert readiness(findings(uc)) == []


# --------------------------------------------------------------------------------------- startup probes
def deployment_file(uc: Path, name: str) -> Path:
    return next(p for p in (uc / "namespaces").rglob(f"{name}.yaml"))


def drop_startup_probe(path: Path) -> None:
    docs = list(yaml.safe_load_all(path.read_text()))
    for d in docs:
        if d.get("kind") == "Deployment":
            for c in d["spec"]["template"]["spec"]["containers"]:
                c.pop("startupProbe", None)
    path.write_text(yaml.safe_dump_all(docs, sort_keys=False))


def test_health_checked_workload_without_a_startup_probe_is_a_finding(tmp_path: Path):
    uc = copy_usecase(tmp_path, "support-copilot")
    drop_startup_probe(deployment_file(uc, "agent-api"))
    found = findings(uc)
    assert any("agent-api" in f and "no startupProbe" in f for f in found), found
    assert not any("orders-stub" in f and "startupProbe" in f for f in found)


def test_health_checked_workload_missing_from_the_overlay_is_a_finding(tmp_path: Path):
    uc = copy_usecase(tmp_path, "support-copilot")
    deployment_file(uc, "orders-stub").unlink()
    k = uc / "namespaces" / "uc-support-copilot" / "kustomization.yaml"
    text = k.read_text()
    k.write_text("\n".join(line for line in text.splitlines() if "orders-stub.yaml" not in line) + "\n")
    found = findings(uc)
    assert any("orders-stub" in f and "no Deployment of that name in the overlay" in f for f in found), found


def test_a_scaffold_without_an_assembled_overlay_is_not_asked_for_probes(tmp_path: Path):
    uc = copy_usecase(tmp_path, "support-copilot")
    (uc / "kustomization.yaml").unlink()
    assert findings(uc) == []


def test_assembly_gives_every_health_checked_workload_a_startup_probe(tmp_path: Path):
    """Sibling of test_assembly_reproduces_the_golden_overlays: regenerate each overlay from its records and
    check the output itself, so a generator change that drops the probe fails here, not in the nightly."""
    k8s = tmp_path / "k8s"
    (k8s / "overlays" / "usecases").mkdir(parents=True)
    for d in ("components", "base"):
        (k8s / d).symlink_to(REPO / "k8s" / d)
    for name in ("invoice-intake", "support-copilot"):
        dst = k8s / "overlays" / "usecases" / name
        shutil.copytree(USECASES / name / ".builder", dst / ".builder")
        r = subprocess.run([sys.executable, str(ASSEMBLE), str(dst), "--force"], capture_output=True, text=True, cwd=REPO)
        assert r.returncode == 0, r.stdout + r.stderr
        scaffold = yaml.safe_load((dst / ".builder" / "scaffold.yaml").read_text())
        checked = [w["name"] for w in scaffold["spec"]["workloads"] if w.get("health_path")]
        assert checked, f"{name}: the fixture no longer has a health-checked workload"
        found: list[str] = []
        checker.check_startup_probes(dst, scaffold, found)
        assert found == [], found
        have = checker.overlay_workloads(dst)
        for w in checked:
            assert all(c.get("startupProbe") for d in have[w] for c in d["spec"]["template"]["spec"]["containers"]), w
