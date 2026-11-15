#!/usr/bin/env python3
"""Turn a walking skeleton into the backlog an agent team implements at Walk (#44).

    backlog.py <usecase-dir> [--check] [--json]

Reads .builder/scaffold.yaml (its `spec.skeleton`), the decision records and gates.yaml, and writes
.builder/backlog.yaml (schemas/backlog.schema.json) and .builder/backlog.md. Deterministic: the same
inputs write the same tickets with the same ids, so running it again after a scaffold change is a diff.

  - one ticket per seam (T-<seam id>): the business rule behind the `SEAM <id>` marker, linked to the
    record that specifies it and the gates it serves;
  - one per workload of a later stage that no seam stands for (T-wl-<name>);
  - one per pending verify assertion (T-assert-<n>), depending on the tickets of its seams;
  - one per workaround (T-wa-<seam>) and per `OPEN:` note of scaffold.yaml (T-open-<n>).

A seam that names no gates inherits those of its record's area at the transition out of its stage.
A ticket is due at Walk (the minimal implementation) unless its seam belongs to Run.

--check exits 1 when backlog.yaml is missing or differs from what the inputs give. A scaffold without
`spec.skeleton` is a legacy full app: there is nothing to derive, exit 2.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import STAGES, load_yaml, schema_errors  # noqa: E402

KEY_OF_KIND = {"tool": "tools", "workload": "workloads", "surface": "workloads"}
NEXT = {"crawl": "crawl->walk", "walk": "walk->run"}


def area_of(record: str) -> str:
    return Path(record.split("#", 1)[0]).stem


class Inputs:
    def __init__(self, uc: Path):
        b = uc / ".builder"
        self.uc = uc
        self.scaffold = load_yaml(b / "scaffold.yaml")
        self.spec = self.scaffold.get("spec") or {}
        self.skeleton = self.spec.get("skeleton") or {}
        gates = load_yaml(b / "gates.yaml") if (b / "gates.yaml").is_file() else {}
        self.transitions = ((gates.get("spec") or {}).get("transitions") or {})
        self.gate_text = {g["id"]: g["text"] for t in self.transitions.values() for g in t.get("gates") or []}
        plan = load_yaml(b / "stage-plan.yaml") if (b / "stage-plan.yaml").is_file() else {}
        stages = (plan.get("spec") or {}).get("stages") or {}
        self.in_scope = [s for s in STAGES if (stages.get(s) or {}).get("in_scope")] if stages else list(STAGES)

    def due(self, stage: str) -> str:
        """Walk closes with the minimal implementation: Crawl's seams are due there too."""
        if stage == "run" or "walk" not in self.in_scope:
            return stage
        return "walk"

    def area_gates(self, area: str, stage: str) -> list[str]:
        t = self.transitions.get(NEXT.get(stage, "")) or {}
        return [g["id"] for g in t.get("gates") or [] if g.get("owner") == area]


def tickets(inp: Inputs) -> list[dict]:
    sk, spec = inp.skeleton, inp.spec
    strict = (sk.get("verify") or {}).get("strict_env", "VERIFY_STRICT")
    done_line = f"the verify Job passes with {strict}=1"
    seams = sk.get("seams") or []
    pending = (sk.get("verify") or {}).get("pending") or []
    out: list[dict] = []
    for s in seams:
        key = KEY_OF_KIND.get(s["kind"])
        record = s["record"] + (f"#stages.{s['stage']}.settings.{key}" if key else "")
        gates = list(s.get("gates") or inp.area_gates(area_of(s["record"]), s["stage"]))
        acceptance = [inp.gate_text[g] for g in gates if g in inp.gate_text]
        acceptance += [p["assertion"] for p in pending if s["id"] in p["seams"]]
        acceptance += [f"`SEAM {s['id']}` in {s['contract']} is replaced by the rule it describes", done_line]
        out.append({"id": f"T-{s['id']}", "kind": "seam",
                    "title": f"{s['name']}: {s['summary']}" if s.get("summary") else f"Implement {s['kind']} {s['name']}",
                    "stage": inp.due(s["stage"]), "seam": s["id"], "record": record,
                    "contract": f"app/src/{s['contract']}" if s["contract"].endswith(".py") else s["contract"],
                    "gates": gates, "acceptance": acceptance})
    named = {s["name"] for s in seams}
    for w in spec.get("workloads", []):
        st = w.get("stage", "crawl")
        if st == "crawl" or w["name"] in named:
            continue
        cmd = w.get("command") or []
        module = f"app/src/{cmd[2].replace('.', '/')}.py" if len(cmd) >= 3 and cmd[:2] == ["python", "-m"] else ""
        gates = inp.area_gates("architecture", st)
        out.append({"id": f"T-wl-{w['name']}", "kind": "workload",
                    "title": f"Implement workload {w['name']} ({w['kind']}) for {st}",
                    "stage": inp.due(st), "record": f"decisions/architecture.yaml#stages.{st}.settings.workloads",
                    **({"contract": module} if module else {}),
                    "gates": gates,
                    "acceptance": [inp.gate_text[g] for g in gates if g in inp.gate_text]
                    + [f"{w['name']} serves its route end to end at {st}", done_line]})
    verify_gates = [g["id"] for t in inp.transitions.values() for g in t.get("gates") or []
                    if (g.get("check") or {}).get("type") == "verify-job" and (g.get("check") or {}).get("ref") == (sk.get("verify") or {}).get("job")]
    for i, p in enumerate(pending, 1):
        out.append({"id": f"T-assert-{i}", "kind": "assertion", "title": f"Make it true: {p['assertion']}",
                    "stage": inp.due(min((s["stage"] for s in seams if s["id"] in p["seams"]), key=STAGES.index, default="crawl")),
                    "record": "decisions/quality.yaml#stages.crawl.settings.verify_assertions",
                    "gates": verify_gates[:1], "acceptance": [f"[PASS] {p['assertion']}", done_line],
                    "depends_on": [f"T-{x}" for x in p["seams"]]})
    by_id = {s["id"]: s for s in seams}
    last = "run" if "run" in inp.in_scope else inp.due("walk")
    for wa in sk.get("workarounds") or []:
        s = by_id.get(wa["seam"], {})
        out.append({"id": f"T-wa-{wa['seam']}", "kind": "workaround", "title": f"Revisit the workaround on {wa['seam']}: {wa['problem']}",
                    "stage": last, "seam": wa["seam"], "record": s.get("record", "scaffold.yaml#spec.skeleton.workarounds"),
                    "gates": [], "acceptance": [f"today: {wa['workaround']}", "replaced by the integration, or kept with the reason in the README"]})
    opens = [n for n in spec.get("notes") or [] if str(n).startswith("OPEN:")]
    for i, n in enumerate(opens, 1):
        out.append({"id": f"T-open-{i}", "kind": "open", "title": str(n)[5:].strip(), "stage": inp.due("crawl"),
                    "record": "scaffold.yaml#spec.notes", "gates": [], "acceptance": ["the owner's answer is recorded and the code follows it"]})
    return out


def document(inp: Inputs) -> dict:
    return {"apiVersion": "forjate.io/v0", "kind": "Backlog",
            "metadata": {"usecase": (inp.scaffold.get("metadata") or {}).get("usecase", inp.uc.name), "version": 1,
                         "generated_by": "forjate backlog.py from .builder/scaffold.yaml"},
            "spec": {"tickets": tickets(inp)}}


def markdown(doc: dict) -> str:
    ts = doc["spec"]["tickets"]
    lines = [f"# Backlog of {doc['metadata']['usecase']}", "",
             "Generated by `backlog.py` from `.builder/scaffold.yaml`; do not edit, re-run it. "
             "Walk closes when every Walk ticket is done: the minimal implementation.", "",
             "| Ticket | Kind | Stage | Gates | Title |", "|---|---|---|---|---|"]
    lines += [f"| {t['id']} | {t['kind']} | {t['stage']} | {', '.join(t['gates']) or '-'} | {t['title']} |" for t in ts]
    for t in ts:
        lines += ["", f"## {t['id']}: {t['title']}", "", f"- Record: `{t['record']}`"]
        if t.get("contract"):
            lines.append(f"- Where: `{t['contract']}`")
        if t.get("depends_on"):
            lines.append(f"- Depends on: {', '.join(t['depends_on'])}")
        lines += ["- Done when:"] + [f"  - {a}" for a in t["acceptance"]]
    return "\n".join(lines) + "\n"


def dump(doc: dict) -> str:
    return "# Generated by backlog.py from scaffold.yaml, the records and gates.yaml; re-run it instead of editing.\n" + \
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    uc = Path(args[0]).resolve()
    b = uc / ".builder"
    if not (b / "scaffold.yaml").is_file():
        print(f"{b / 'scaffold.yaml'} missing: run the scaffold first")
        return 2
    inp = Inputs(uc)
    if not inp.skeleton:
        print("scaffold.yaml has no spec.skeleton: a legacy full app, nothing to derive")
        return 2
    doc = document(inp)
    errors = schema_errors("backlog", doc, "backlog")
    if errors:
        print("\n".join(errors))
        return 1
    text = dump(doc)
    if "--check" in argv:
        current = (b / "backlog.yaml").read_text() if (b / "backlog.yaml").is_file() else ""
        if current != text:
            print(f"{b / 'backlog.yaml'} is stale or missing: run backlog.py {args[0]}")
            return 1
        print(f"backlog: {len(doc['spec']['tickets'])} ticket(s), up to date")
        return 0
    (b / "backlog.yaml").write_text(text)
    (b / "backlog.md").write_text(markdown(doc))
    if "--json" in argv:
        print(json.dumps(doc, indent=2))
    else:
        by_stage = {s: sum(t["stage"] == s for t in doc["spec"]["tickets"]) for s in STAGES}
        print(f"backlog: {len(doc['spec']['tickets'])} ticket(s) ({', '.join(f'{s} {n}' for s, n in by_stage.items() if n)}) "
              f"-> {b / 'backlog.yaml'}, {b / 'backlog.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
