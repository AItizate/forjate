#!/usr/bin/env python3
"""Helper for run.sh: write eval_metadata.json for one eval and print its name and prompt file.

    evals_meta.py <evals.json> <index> <out_root>  →  prints "<name>\t<prompt-file>"
"""
import json
import sys
from pathlib import Path

evals_file, index, out_root = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
e = json.loads(evals_file.read_text())["evals"][index]
d = out_root / e["name"]
d.mkdir(parents=True, exist_ok=True)
(d / "eval_metadata.json").write_text(json.dumps(
    {"eval_name": e["name"], "prompt": e["prompt"], "assertions": e["assertions"]}, indent=2, ensure_ascii=False))
(d / "prompt.txt").write_text(e["prompt"])
print(f"{e['name']}\t{d / 'prompt.txt'}")
