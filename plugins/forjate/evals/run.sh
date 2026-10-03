#!/usr/bin/env bash
# Run a skill's evals with and without the plugin, each in a fresh git worktree.
# Usage: run.sh <skill> [--iteration N] [--eval <name>] [--only with|without] [--max-turns N] [--model <alias>] [--timeout SECONDS]
# Default model for eval runs is opus; pass --model to compare. A run that exceeds
# the timeout (default 1800 s, FORJATE_EVAL_TIMEOUT) is killed and recorded as is_error.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO="$(git -C "$PLUGIN_DIR" rev-parse --show-toplevel)"

skill="${1:?usage: run.sh <skill> [--iteration N] [--eval name] [--only with|without]}"; shift
iteration=""; only_eval=""; only_cfg=""; max_turns=40; model="${FORJATE_EVAL_MODEL:-opus}"; timeout_s="${FORJATE_EVAL_TIMEOUT:-1800}"
while [[ $# -gt 0 ]]; do
  case $1 in
    --iteration) iteration="$2"; shift ;;
    --eval) only_eval="$2"; shift ;;
    --only) only_cfg="$2"; shift ;;
    --max-turns) max_turns="$2"; shift ;;
    --model) model="$2"; shift ;;
    --timeout) timeout_s="$2"; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac; shift
done

evals_file="${SCRIPT_DIR}/${skill}/evals.json"
[[ -f "$evals_file" ]] || { echo "no evals for skill '$skill' ($evals_file)" >&2; exit 2; }
ws="${REPO}/evals-workspace/${skill}"
if [[ -z "$iteration" ]]; then
  iteration=1; while [[ -d "${ws}/iteration-${iteration}" ]]; do iteration=$((iteration+1)); done
fi
out_root="${ws}/iteration-${iteration}"
mkdir -p "$out_root"
echo "skill=$skill iteration=$iteration model=$model timeout=${timeout_s}s → $out_root"

run_one() {  # <eval-name> <prompt> <with|without>
  local name="$1" prompt="$2" cfg="$3"
  local dir="${out_root}/${name}/${cfg}_skill"
  local wt="${dir}/repo"
  mkdir -p "$dir"
  git -C "$REPO" worktree remove --force "$wt" 2>/dev/null || true
  git -C "$REPO" worktree add --quiet --detach "$wt" HEAD
  # The worktree has no virtualenv; share the main checkout's so `poetry run`
  # and the skills' validate/packs commands work inside it.
  [[ -d "$REPO/.venv" ]] && { rm -rf "$wt/.venv"; ln -s "$REPO/.venv" "$wt/.venv"; }
  # Seed gitignored .env files so overlays build, as CI does.
  find "$wt/k8s/overlays" -name '*.env.example' | while read -r ex; do [[ -f "${ex%.example}" ]] || cp "$ex" "${ex%.example}"; done
  # Evals run in a throwaway worktree, so the build/validate commands the skills
  # rely on are pre-approved; everything else still goes through the default policy.
  local allowed="Read Edit Write Glob Grep Agent Skill Bash(cd *) Bash(kubectl kustomize *) Bash(kustomize *) Bash(kubeconform *) Bash(poetry run *) Bash(python3 *) Bash(yq *) Bash(./scripts/ephemeral/create-usecase.sh *) Bash(cp *) Bash(mkdir *) Bash(ls *) Bash(cat *) Bash(git diff *) Bash(git status *)"
  # The plugin is checked into this repo, so a worktree carries the skills on
  # disk even without --plugin-dir. Strip them for the baseline so it is a real
  # control; the builder scripts and schemas stay because the prompts cite them.
  if [[ "$cfg" == "without" ]]; then
    rm -rf "$wt/plugins/forjate/skills" "$wt/plugins/forjate/agents" "$wt/docs/use-case-builder"
  fi
  local args=(-p "$prompt" --output-format json --permission-mode acceptEdits --max-turns "$max_turns" --model "$model" --allowedTools "$allowed")
  [[ "$cfg" == "with" ]] && args+=(--plugin-dir "$PLUGIN_DIR")
  echo "  [$cfg] $name"
  # A hung `claude -p` must not block the batch: kill it after the timeout and
  # record the run as an error so the grader and the benchmark show it as such.
  local rc=0
  ( cd "$wt" && exec claude "${args[@]}" < /dev/null > "$dir/result.json" 2> "$dir/stderr.log" ) &
  local pid=$!
  # Wall-clock deadline polled every 15 s rather than one long sleep: a laptop
  # that suspends mid-run still times out on wake, and nothing is left behind.
  local started=$(date +%s)
  while kill -0 "$pid" 2>/dev/null; do
    if (( $(date +%s) - started >= timeout_s )); then
      echo "    TIMEOUT after ${timeout_s}s, killing $pid"
      kill -TERM "$pid" 2>/dev/null; sleep 5; kill -KILL "$pid" 2>/dev/null
      break
    fi
    sleep 15
  done
  wait "$pid" || rc=$?
  [[ $rc -ne 0 ]] && echo "    claude exited $rc (see stderr.log)"
  python3 - "$dir" "$rc" "$timeout_s" <<'PY'
import json, sys, pathlib
d = pathlib.Path(sys.argv[1]); r = d / "result.json"; rc = int(sys.argv[2]); timeout_s = int(sys.argv[3])
try:
    raw = r.read_text()
    if rc in (124, 137, 143) or (rc != 0 and not raw.strip()):
        (d / "timing.json").write_text(json.dumps({
            "duration_ms": None, "total_duration_seconds": None, "num_turns": None, "total_cost_usd": None,
            "total_tokens": 0, "models": [], "is_error": True,
            "error": f"killed after {timeout_s}s timeout" if rc in (124, 137, 143) else f"claude exited {rc} with no output",
        }, indent=2))
        raise SystemExit(0)
    j = json.loads(raw)
    (d / "timing.json").write_text(json.dumps({
        "duration_ms": j.get("duration_ms"), "total_duration_seconds": (j.get("duration_ms") or 0)/1000,
        "num_turns": j.get("num_turns"), "total_cost_usd": j.get("total_cost_usd"),
        "total_tokens": (j.get("usage") or {}).get("input_tokens", 0) + (j.get("usage") or {}).get("output_tokens", 0),
        "models": sorted((j.get("modelUsage") or {}).keys()),
        "is_error": j.get("is_error", False) or "session limit" in str(j.get("result", "")),
    }, indent=2))
    if "session limit" in str(j.get("result", "")):
        print("    RATE LIMITED: " + str(j.get("result"))[:120])
except Exception as e:
    print(f"    could not parse result.json: {e}")
PY
}

count="$(python3 -c "import json;print(len(json.load(open('$evals_file'))['evals']))")"
for ((i=0; i<count; i++)); do
  IFS=$'\t' read -r name prompt_file < <(python3 "${SCRIPT_DIR}/evals_meta.py" "$evals_file" "$i" "$out_root")
  [[ -n "$only_eval" && "$only_eval" != "$name" ]] && continue
  prompt="$(<"$prompt_file")"
  [[ -z "$only_cfg" || "$only_cfg" == "with" ]] && run_one "$name" "$prompt" with
  [[ -z "$only_cfg" || "$only_cfg" == "without" ]] && run_one "$name" "$prompt" without
done
echo "done. grade with: python3 ${SCRIPT_DIR}/grade.py --all $out_root"
