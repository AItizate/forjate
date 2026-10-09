#!/usr/bin/env python3
"""Plaintext-credential scan for Forjate overlays.

    secret-scan.py <dir>... [--json]

A production tenant surveyed in docs/use-case-builder/tenant-patterns.md sealed all 24 of its
Secrets and still committed two LLM API keys: one as a configMapGenerator literal, one in an
env patch. A scan limited to secrets/ passes that tree. This one covers what the security
expert's gate names (plugins/forjate/skills/security/references/secrets-ladder.md):

  - configMapGenerator[].literals and secretGenerator[].literals in every kustomization.yaml
  - files under configs/ (and any file a configMapGenerator reads)
  - patches/*.yaml, inline `patch:` blocks and every manifest: env[].value, stringData, data
  - *.env files tracked by git, and .env.example files whose values are not placeholders

Findings are printed as `path:line: <rule>: <masked value>`. Exit 1 on any finding, 0 clean.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PLACEHOLDER = re.compile(
    r"^(|\s*|change[-_ ]?me.*|changeme.*|placeholder.*|example.*|dummy.*|todo.*|xxx+|\*+|<[^>]*>|"
    r"\$\{?[A-Z_]+\}?|\$\([A-Z_]+\)|ephemeral-local-only|secret|password|postgres|admin|dev-only.*|replace[-_ ]me.*|your[-_].*|none|null|n/a)$",
    re.IGNORECASE,
)
# A value that says it is not a real credential, wherever it says it.
SELF_DECLARED = re.compile(r"(?i)(local[-_]?only|localdev|local-dev|example|placeholder|change[-_]?me|dummy|test[-_]?only|not-a-secret|quickstart|sample)")
# Indirections that resolve at runtime, never a value in git.
INDIRECT = ("os.environ/", "$", "{{", "valueFrom", "secretKeyRef", "/", "vault:", "ref+")
# Patterns that identify a credential by shape alone, independent of the key name.
SHAPES = [
    ("openai-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("slack token", re.compile(r"\bxox[bpa]-[A-Za-z0-9-]{10,}\b")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("credentials in url", re.compile(r"[a-z][a-z0-9+.-]*://[^:/\s@'\"]+:(?P<pw>[^@\s'\"]+)@")),
]
# A key name that means "secret" with a value that is not a placeholder.
KEYED = re.compile(
    r"(?i)\b(?P<key>[A-Z0-9_.-]*(api[_-]?key|secret|token|password|passwd|pwd|private[_-]?key|access[_-]?key)[A-Z0-9_.-]*)"
    r"\s*[:=]\s*[\"']?(?P<val>[^\s\"'#,}]{8,})"
)
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "charts", "evals-workspace"}
TEXT_SUFFIXES = {".yaml", ".yml", ".env", ".example", ".json", ".toml", ".ini", ".cfg", ".conf", ".txt", ".md", ".sh", ".py", ""}


def mask(value: str) -> str:
    value = str(value)
    return value[:4] + "…" + value[-2:] if len(value) > 8 else "…"


def is_placeholder(value: str) -> bool:
    v = str(value).strip()
    return PLACEHOLDER.match(v) is not None or SELF_DECLARED.search(v) is not None or v.startswith(INDIRECT)


def looks_random(value: str) -> bool:
    """A real credential has letters and digits (or is long); CHANGE_ME does not."""
    v = str(value)
    classes = sum(bool(re.search(p, v)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]"))
    return len(v) >= 16 and classes >= 3 or len(v) >= 32


def scan_text(text: str, path: Path, findings: list[dict], *, keyed: bool = True) -> None:
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for rule, rx in SHAPES:
            m = rx.search(line)
            if m:
                val = m.group("pw") if "pw" in rx.groupindex else m.group(0)
                if rule != "private key block" and is_placeholder(val):
                    continue
                findings.append({"path": str(path), "line": lineno, "rule": rule, "value": mask(val)})
        if keyed:
            for m in KEYED.finditer(line):
                val = m.group("val").rstrip(";")
                if is_placeholder(val) or "://" in val:
                    continue
                if "secretKeyRef" in line or "valueFrom" in line:
                    continue
                if looks_random(val):
                    findings.append({"path": str(path), "line": lineno, "rule": f"credential-shaped value for {m.group('key')}", "value": mask(val)})


def tracked_files(root: Path) -> set[Path]:
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "--full-name", "--", "."], capture_output=True, text=True, check=True).stdout
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()
    return {Path(top) / f for f in out.splitlines() if f}


def scan_dir(root: Path) -> list[dict]:
    findings: list[dict] = []
    root = root.resolve()
    tracked = tracked_files(root)
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix not in TEXT_SUFFIXES and not path.name.endswith(".env.example"):
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        rel = path.relative_to(root)
        name = path.name
        if name.endswith(".env") and (not tracked or path in tracked):
            # A real .env in git is the finding, whatever it holds. (With no git, assume tracked.)
            findings.append({"path": str(rel), "line": 0, "rule": ".env file tracked by git (must be gitignored; commit the .env.example)", "value": ""})
            continue
        if name.endswith(".env.example"):
            for lineno, line in enumerate(text.splitlines(), 1):
                if "=" not in line or line.strip().startswith("#"):
                    continue
                key, _, val = line.partition("=")
                if "://" in val:
                    continue  # the credentials-in-url shape rule covers it
                if KEYED.match(f"{key.strip()}={val.strip()}") and not is_placeholder(val.strip()) and looks_random(val.strip()):
                    findings.append({"path": str(rel), "line": lineno, "rule": f".env.example value for {key.strip()} is not a placeholder", "value": mask(val.strip())})
            scan_text(text, rel, findings, keyed=False)
            continue
        if name.endswith(".env"):
            continue
        scan_text(text, rel, findings)
        if name in ("kustomization.yaml", "kustomization.yml"):
            findings += scan_kustomization(text, rel)
    # de-duplicate (a literal may match both a shape and the keyed rule)
    seen = set()
    unique = []
    for f in findings:
        k = (f["path"], f["line"], f["value"])
        if k not in seen:
            seen.add(k)
            unique.append(f)
    return unique


def scan_kustomization(text: str, rel: Path) -> list[dict]:
    """Literals of any generator are plaintext in git by construction; flag secret-shaped ones."""
    out: list[dict] = []
    try:
        import yaml
        doc = yaml.safe_load(text) or {}
    except Exception:
        return out
    for gen in ("configMapGenerator", "secretGenerator"):
        for entry in doc.get(gen) or []:
            for lit in entry.get("literals") or []:
                key, _, val = str(lit).partition("=")
                if gen == "secretGenerator" and not is_placeholder(val):
                    out.append({"path": str(rel), "line": 0, "rule": f"secretGenerator literal {key} (use envs: with a gitignored .env and a committed .env.example)", "value": mask(val)})
                elif KEYED.match(f"{key}={val}") and not is_placeholder(val) and looks_random(val):
                    out.append({"path": str(rel), "line": 0, "rule": f"configMapGenerator literal {key} looks like a credential", "value": mask(val)})
    return out


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    dirs = [Path(a) for a in argv if not a.startswith("--")]
    if not dirs:
        print(__doc__)
        return 2
    findings: list[dict] = []
    for d in dirs:
        if not d.is_dir():
            print(f"error: not a directory: {d}", file=sys.stderr)
            return 2
        findings += [dict(f, root=str(d)) for f in scan_dir(d)]
    if as_json:
        print(json.dumps(findings, indent=2))
    else:
        for f in findings:
            print(f"{f['root']}/{f['path']}:{f['line']}: {f['rule']}: {f['value']}")
        print(f"secret-scan: {len(findings)} finding(s) in {len(dirs)} dir(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
