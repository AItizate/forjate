#!/usr/bin/env bash
# Run a skill's evals with and without the plugin, each in a fresh git worktree.
# Usage: run.sh <skill> [--iteration N] [--eval <name>] [--only with|without] [--max-turns N]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO="$(git -C "$PLUGIN_DIR" rev-parse --show-toplevel)"

skill="${1:?usage: run.sh <skill> [--iteration N] [--eval name] [--only with|without]}"; shift
iteration=""; only_eval=""; only_cfg=""; max_turns=40
while [[ $# -gt 0 ]]; do
  case $1 in
    --iteration) iteration="$2"; shift ;;
    --eval) only_eval="$2"; shift ;;
    --only) only_cfg="$2"; shift ;;
    --max-turns) max_turns="$2"; shift ;;
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
echo "skill=$skill iteration=$iteration → $out_root"

run_one() {  # <eval-name> <prompt> <with|without>
  local name="$1" prompt="$2" cfg="$3"
  local dir="${out_root}/${name}/${cfg}_skill"
  local wt="${dir}/repo"
  mkdir -p "$dir"
  git -C "$REPO" worktree remove --force "$wt" 2>/dev/null || true
  git -C "$REPO" worktree add --quiet --detach "$wt" HEAD
  # Seed gitignored .env files so overlays build, as CI does.
  find "$wt/k8s/overlays" -name '*.env.example' | while read -r ex; do [[ -f "${ex%.example}" ]] || cp "$ex" "${ex%.example}"; done
  # Evals run in a throwaway worktree, so the build/validate commands the skills
  # rely on are pre-approved; everything else still goes through the default policy.
  local allowed="Read Edit Write Glob Grep Agent Bash(kubectl kustomize *) Bash(kustomize *) Bash(kubeconform *) Bash(poetry run *) Bash(python3 *) Bash(yq *) Bash(./scripts/ephemeral/create-usecase.sh *) Bash(cp *) Bash(mkdir *) Bash(ls *) Bash(cat *) Bash(git diff *) Bash(git status *)"
  local args=(-p "$prompt" --output-format json --permission-mode acceptEdits --max-turns "$max_turns" --allowedTools "$allowed")
  [[ "$cfg" == "with" ]] && args+=(--plugin-dir "$PLUGIN_DIR")
  echo "  [$cfg] $name"
  ( cd "$wt" && claude "${args[@]}" < /dev/null > "$dir/result.json" 2> "$dir/stderr.log" ) || echo "    claude exited $? (see stderr.log)"
  python3 - "$dir" <<'PY'
import json, sys, pathlib
d = pathlib.Path(sys.argv[1]); r = d / "result.json"
try:
    j = json.loads(r.read_text())
    (d / "timing.json").write_text(json.dumps({
        "duration_ms": j.get("duration_ms"), "total_duration_seconds": (j.get("duration_ms") or 0)/1000,
        "num_turns": j.get("num_turns"), "total_cost_usd": j.get("total_cost_usd"),
        "total_tokens": (j.get("usage") or {}).get("input_tokens", 0) + (j.get("usage") or {}).get("output_tokens", 0),
    }, indent=2))
except Exception as e:
    print(f"    could not parse result.json: {e}")
PY
}

count="$(python3 -c "import json;print(len(json.load(open('$evals_file'))['evals']))")"
for ((i=0; i<count; i++)); do
  name="$(python3 -c "import json;print(json.load(open('$evals_file'))['evals'][$i]['name'])")"
  prompt="$(python3 -c "import json;print(json.load(open('$evals_file'))['evals'][$i]['prompt'])")"
  [[ -n "$only_eval" && "$only_eval" != "$name" ]] && continue
  python3 -c "import json;e=json.load(open('$evals_file'))['evals'][$i];json.dump({'eval_name':e['name'],'prompt':e['prompt'],'assertions':e['assertions']},open('$out_root/$name/eval_metadata.json','w'),indent=2)" 2>/dev/null || { mkdir -p "$out_root/$name"; python3 -c "import json;e=json.load(open('$evals_file'))['evals'][$i];json.dump({'eval_name':e['name'],'prompt':e['prompt'],'assertions':e['assertions']},open('$out_root/$name/eval_metadata.json','w'),indent=2)"; }
  [[ -z "$only_cfg" || "$only_cfg" == "with" ]] && run_one "$name" "$prompt" with
  [[ -z "$only_cfg" || "$only_cfg" == "without" ]] && run_one "$name" "$prompt" without
done
echo "done. grade with: python3 ${SCRIPT_DIR}/grade.py --all $out_root"
