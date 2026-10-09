#!/usr/bin/env python3
"""Gates runner: executes a use case's .builder/gates.yaml for one stage transition.

    gates.py run <usecase> --transition crawl->walk [--usecase-dir DIR] [--json] [--only TYPE]
    gates.py list <usecase> [--usecase-dir DIR]

Per gate, by check.type:
  ci          runs scripts/gates/checks/<ref>.sh with the gate's context in the environment.
              The checks directory is the enum validate.py checks against. Exit 0 pass,
              1 fail, 2 skipped (the script prints why), anything else fail.
  verify-job  runs `scripts/ephemeral/ephemeral.sh validate <usecase>` once per Job name when
              the use case's environment is live on the k3d cluster, else skipped. KPI/EVAL
              lines of the Job log are captured into .builder/metrics.yaml.
  metric      reads the metric from .builder/metrics.yaml (written by the verify-job run or
              by an operator); the quality record's kpi_metric_source says where it comes
              from. pass with the value when present, else pending.
  manual      listed with the owner and the document or rehearsal in check.ref; never blocks.

Exit 1 when any ci or verify-job gate failed; 0 otherwise (pending, skipped and manual never
block, the table shows them). Status per gate: pass | fail | skipped | pending | manual.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CHECKS = HERE / "checks"
BUILDER = REPO / "plugins" / "forjate" / "scripts" / "builder"
sys.path.insert(0, str(BUILDER))
try:
    from common import load_yaml, schema_errors  # noqa: E402
except ImportError:  # running outside the factory checkout
    import yaml

    def load_yaml(p: Path) -> dict:  # type: ignore[no-redef]
        return yaml.safe_load(p.read_text())

    def schema_errors(*_a, **_k) -> list[str]:  # type: ignore[no-redef]
        return []

TRANSITIONS = {"crawl->walk": ("crawl", "walk"), "walk->run": ("walk", "run")}
KPI_LINE = re.compile(r"^\s*(KPI|EVAL)\s+([A-Za-z0-9_]+)=([^\s]+)")


class Runner:
    def __init__(self, name: str, uc_dir: Path, transition: str, only: str | None = None, quiet: bool = False):
        self.name, self.uc_dir, self.transition, self.only, self.quiet = name, uc_dir, transition, only, quiet
        self.source, self.target = TRANSITIONS[transition]
        self.builder = uc_dir / ".builder"
        self.gates_doc = load_yaml(self.builder / "gates.yaml")
        self.metrics_path = self.builder / "metrics.yaml"
        self.metrics = load_yaml(self.metrics_path) if self.metrics_path.is_file() else {}
        self._verify_cache: dict[str, tuple[str, str]] = {}
        self._live: bool | None = None

    # ---------------------------------------------------------------- context
    def stage_dir(self) -> Path:
        return self.uc_dir if self.target == "crawl" else self.uc_dir / "stages" / self.target

    def env(self, gate: dict) -> dict[str, str]:
        e = dict(os.environ)
        e.update({
            "REPO": str(REPO), "UC_NAME": self.name, "UC_DIR": str(self.uc_dir), "UC_NS": f"uc-{self.name}",
            "TRANSITION": self.transition, "SOURCE_STAGE": self.source, "STAGE": self.target,
            "STAGE_DIR": str(self.stage_dir()), "GATE_ID": gate["id"], "GATE_TEXT": gate.get("text", ""),
            "CHECKS_DIR": str(CHECKS),
        })
        return e

    def verify_job_name(self) -> str:
        uc = self.uc_dir / "usecase.yaml"
        if uc.is_file():
            return str((load_yaml(uc).get("spec") or {}).get("jobs", {}).get("verify", {}).get("name") or "")
        return ""

    def kubeconfig(self) -> Path:
        return Path(os.environ.get("KUBECONFIG_UC") or (Path.home() / ".kube" / f"{os.environ.get('UC_SHARED_CLUSTER', 'forjate-uc-shared')}.yaml"))

    def live(self) -> bool:
        """The use case's namespace exists on the ephemeral cluster."""
        if self._live is None:
            kc = self.kubeconfig()
            if not kc.is_file():
                self._live = False
            else:
                p = subprocess.run(["kubectl", "--kubeconfig", str(kc), "get", "ns", f"uc-{self.name}"], capture_output=True, text=True)
                self._live = p.returncode == 0
        return self._live

    # ---------------------------------------------------------------- checks
    def run_ci(self, gate: dict) -> tuple[str, str]:
        ref = (gate.get("check") or {}).get("ref") or ""
        script = CHECKS / f"{ref}.sh"
        if not ref or not script.is_file():
            return "fail", f"no check script for ref '{ref}' in {CHECKS.relative_to(REPO)}/"
        p = subprocess.run(["bash", str(script)], env=self.env(gate), capture_output=True, text=True, cwd=REPO)
        out = (p.stdout + p.stderr).strip()
        last = out.splitlines()[-1] if out else ""
        if p.returncode == 0:
            return "pass", last[:160]
        if p.returncode == 2:
            return "skipped", last[:160]
        return "fail", out[-600:]

    def run_verify(self, gate: dict) -> tuple[str, str]:
        job = (gate.get("check") or {}).get("ref") or self.verify_job_name()
        if job in self._verify_cache:
            return self._verify_cache[job]
        if not self.live():
            res = ("skipped", f"no live environment for {self.name}; run scripts/ephemeral/ephemeral.sh up {self.name}")
        else:
            p = subprocess.run(["bash", str(REPO / "scripts/ephemeral/ephemeral.sh"), "validate", self.name], capture_output=True, text=True, cwd=REPO)
            out = p.stdout + p.stderr
            self.capture_metrics(out, job)
            res = ("pass", f"Job/{job} completed") if p.returncode == 0 else ("fail", out[-800:])
        self._verify_cache[job] = res
        return res

    def capture_metrics(self, log: str, job: str) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        found = 0
        for line in log.splitlines():
            m = KPI_LINE.match(line)
            if m:
                self.metrics[m.group(2)] = {"value": m.group(3), "source": f"verify-job-log:{job}", "measured_at": now}
                found += 1
        if found:
            import yaml
            self.metrics_path.write_text(yaml.safe_dump(self.metrics, sort_keys=True))

    def run_metric(self, gate: dict) -> tuple[str, str]:
        ref = (gate.get("check") or {}).get("ref") or ""
        source = self.metric_source()
        if ref in self.metrics:
            m = self.metrics[ref]
            return "pass", f"{ref}={m.get('value')} ({m.get('source')}, {m.get('measured_at', '')})"
        hint = {"verify-job-log": f"run the verify Job (gates.py captures KPI/EVAL lines into .builder/metrics.yaml)"}.get(source.split(":")[0], f"read it from {source} and record it in .builder/metrics.yaml")
        return "pending", f"{ref} not measured yet; source {source}: {hint}"

    def metric_source(self) -> str:
        q = self.builder / "decisions" / "quality.yaml"
        if q.is_file():
            st = (load_yaml(q).get("spec") or {}).get("stages", {}).get(self.source) or {}
            return str((st.get("settings") or {}).get("kpi_metric_source") or "unknown")
        return "unknown"

    # ---------------------------------------------------------------- run
    def run(self) -> tuple[list[dict], int]:
        tr = (self.gates_doc.get("spec") or {}).get("transitions", {}).get(self.transition)
        if tr is None:
            raise SystemExit(f"gates.yaml has no transition {self.transition} (in scope: {', '.join(self.gates_doc['spec']['transitions'])})")
        rows = []
        gates_in_order = sorted(tr.get("gates") or [], key=lambda g: 0 if ((g.get("check") or {}).get("type") == "verify-job") else 1)
        for gate in gates_in_order:
            check = gate.get("check") or {"type": "manual"}
            ctype = check.get("type", "manual")
            if self.only and ctype != self.only:
                continue
            if ctype == "ci":
                status, detail = self.run_ci(gate)
            elif ctype == "verify-job":
                status, detail = self.run_verify(gate)
            elif ctype == "metric":
                status, detail = self.run_metric(gate)
            else:
                status, detail = "manual", f"{gate.get('owner', '?')} signs; ref: {check.get('ref', 'the record')}"
            rows.append({"id": gate["id"], "type": ctype, "ref": check.get("ref", ""), "owner": gate.get("owner", ""), "status": status, "detail": detail, "text": gate.get("text", "")})
        failed = [r for r in rows if r["status"] == "fail"]
        return rows, (1 if failed else 0)


def norm_transition(v: str) -> str:
    key = v.replace("->", "-").replace(">", "-").replace("_", "-").replace(" ", "")
    for t in TRANSITIONS:
        if t.replace("->", "-") == key:
            return t
    raise argparse.ArgumentTypeError(f"{v!r}: expected one of {', '.join(TRANSITIONS)}")


def table(rows: list[dict], name: str, transition: str, approver: str) -> str:
    lines = [f"# gates: {name} {transition} (approver: {approver or 'unset'})", "",
             "| gate | type | ref | status | detail |", "|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: ("pass", "fail", "skipped", "pending", "manual").index(r["status"])):
        d = r["detail"].replace("\n", " ").replace("|", "/")
        lines.append(f"| {r['id']} | {r['type']} | {r['ref']} | **{r['status']}** | {d[:140]} |")
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("pass", "fail", "skipped", "pending", "manual")}
    lines += ["", "  ".join(f"{k}: {v}" for k, v in counts.items())]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("run", "list"):
        s = sub.add_parser(c)
        s.add_argument("usecase")
        s.add_argument("--usecase-dir")
        if c == "run":
            s.add_argument("--transition", required=True, type=norm_transition, help="crawl->walk or walk->run (quote it in a shell; crawl-walk is accepted too)")
            s.add_argument("--only", choices=["ci", "verify-job", "metric", "manual"])
            s.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    uc_dir = Path(a.usecase_dir).resolve() if a.usecase_dir else REPO / "k8s" / "overlays" / "usecases" / a.usecase
    gates_file = uc_dir / ".builder" / "gates.yaml"
    if not gates_file.is_file():
        print(f"error: {gates_file} missing; run the quality expert in consolidate mode first", file=sys.stderr)
        return 2
    doc = load_yaml(gates_file)
    errs = schema_errors("gates", doc, str(gates_file))
    if errs:
        print("\n".join(f"error: {e}" for e in errs), file=sys.stderr)
        return 2
    if a.cmd == "list":
        for tr, body in doc["spec"]["transitions"].items():
            print(f"{tr}  approver: {body.get('approver', 'unset')}")
            for g in body.get("gates") or []:
                c = g.get("check") or {"type": "manual"}
                print(f"  {g['id']:<10} {c.get('type', 'manual'):<10} {c.get('ref', ''):<28} {g.get('owner', ''):<14} {g.get('text', '')[:80]}")
        return 0
    r = Runner(a.usecase, uc_dir, a.transition, a.only)
    rows, rc = r.run()
    approver = doc["spec"]["transitions"][a.transition].get("approver", "")
    if a.json:
        print(json.dumps({"usecase": a.usecase, "transition": a.transition, "approver": approver, "gates": rows, "exit": rc}, indent=2))
    else:
        print(table(rows, a.usecase, a.transition, approver))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
