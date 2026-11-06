#!/usr/bin/env python3
"""Cost per agent of one eval run, and a copy of its transcripts.

Usage: agent-costs.py <run_dir>   (the with_skill/ or without_skill/ directory run.sh writes)

result.json carries the session's total only. The transcripts under ~/.claude/projects/ carry each message's
token usage, the subagents' included, with the agent type in each subagent's meta.json; Claude Code deletes them
after cleanupPeriodDays. This copies them to <run_dir>/transcripts/ and writes <run_dir>/agent-costs.json: tokens
per agent, and the run's cost split by each agent's share of the price-weighted tokens (input 1, cache write 1.25
for 5 min and 2 for 1 h, cache read 0.1, output 5), so the split always sums to the cost Claude Code reported."""
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

WEIGHTS = {"input_tokens": 1.0, "cache_5m": 1.25, "cache_1h": 2.0, "cache_read_input_tokens": 0.1, "output_tokens": 5.0}


def results(run_dir: Path) -> list[dict]:
    """The run's result.json and one per earlier segment of a resumed run."""
    paths = sorted(run_dir.glob("segments/*/result.json")) + [run_dir / "result.json"]
    return [json.loads(p.read_text()) for p in paths if p.exists()]


def usage_by_message(path: Path) -> dict[str, dict]:
    """One usage per assistant message id: a streamed message repeats its usage on every content block."""
    seen: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        m = o.get("message")
        if isinstance(m, dict) and m.get("usage") and m.get("id"):
            seen[m["id"]] = m["usage"]
    return seen


def tokens(usages) -> dict[str, int]:
    t = defaultdict(int)
    for u in usages:
        cc = u.get("cache_creation") or {}
        t["input_tokens"] += u.get("input_tokens", 0)
        t["cache_read_input_tokens"] += u.get("cache_read_input_tokens", 0)
        t["output_tokens"] += u.get("output_tokens", 0)
        five, hour = cc.get("ephemeral_5m_input_tokens"), cc.get("ephemeral_1h_input_tokens")
        if five is None and hour is None:
            five = u.get("cache_creation_input_tokens", 0)
        t["cache_5m"] += five or 0
        t["cache_1h"] += hour or 0
    return dict(t)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__); return 2
    run_dir = Path(argv[0]).resolve()
    rs = results(run_dir)
    sids = list(dict.fromkeys(r["session_id"] for r in rs if r.get("session_id")))
    if not sids:
        print(f"agent-costs: no session id in {run_dir}", file=sys.stderr); return 1
    cost = round(sum(r.get("total_cost_usd") or 0 for r in rs), 6)
    agents: dict[str, dict] = defaultdict(lambda: {"calls": 0, "usages": {}})
    out = run_dir / "transcripts"
    for sid in sids:
        found = sorted(Path.home().glob(f".claude/projects/*/{sid}.jsonl"))
        if not found:
            print(f"agent-costs: transcript of {sid} not found (cleaned up?)", file=sys.stderr); continue
        main_file = found[0]
        (out / sid).mkdir(parents=True, exist_ok=True)
        shutil.copy2(main_file, out / sid / main_file.name)
        a = agents["main"]; a["calls"] += 1; a["usages"].update(usage_by_message(main_file))
        sub = main_file.with_suffix("") / "subagents"
        if sub.is_dir():
            shutil.copytree(sub, out / sid / "subagents", dirs_exist_ok=True)
            for f in sorted(sub.glob("agent-*.jsonl")):
                meta = f.with_suffix(".meta.json")
                kind = json.loads(meta.read_text()).get("agentType", "unknown") if meta.exists() else "unknown"
                a = agents[kind]; a["calls"] += 1; a["usages"].update(usage_by_message(f))
    rows = {k: {"calls": v["calls"], "messages": len(v["usages"]), "tokens": tokens(v["usages"].values())} for k, v in agents.items()}
    weight = {k: sum(WEIGHTS[t] * n for t, n in r["tokens"].items()) for k, r in rows.items()}
    total = sum(weight.values()) or 1
    for k, r in rows.items():
        r["share"] = round(weight[k] / total, 4)
        r["cost_usd"] = round(cost * weight[k] / total, 2)
    ordered = dict(sorted(rows.items(), key=lambda kv: -kv[1]["cost_usd"]))
    report = {"sessions": sids, "total_cost_usd": cost, "method": "cost split by price-weighted tokens", "agents": ordered}
    (run_dir / "agent-costs.json").write_text(json.dumps(report, indent=2) + "\n")
    for k, r in ordered.items():
        print(f"  {r['cost_usd']:>8.2f} USD  {r['share']:>6.1%}  {r['calls']:>2} call(s)  {k}")
    print(f"  {cost:>8.2f} USD  total")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
