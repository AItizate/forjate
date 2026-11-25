"""The two health signals `ephemeral.sh up` records after the verify Job (#41): container restarts since the
verify (expected zero) and the verify's KPI lines on a second `up` of the same seed (expected equal).

The cluster is a fake kubectl that prints canned pod rows and a canned Job log; what is under test is the
counting, the comparison and the HEALTH lines the nightly asserts on.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
LIB = REPO / "scripts" / "ephemeral" / "lib"
EPHEMERAL = REPO / "scripts" / "ephemeral" / "ephemeral.sh"


DESCRIBE = """Name:           worker-5c4
Containers:
  worker:
    Container ID:   containerd://abc
    State:          Running
    Last State:     Terminated
      Reason:       Error
      Exit Code:    137
    Restart Count:  3
    Liveness:       http-get http://:8080/healthz delay=0s timeout=1s period=15s #success=1 #failure=3
    Environment Variables from:
      worker-config  ConfigMap  Optional: false
    Environment:
      API_TOKEN:  literal-secret-value
      DB_PASSWORD:  <set to the key 'password' in secret 'db'>  Optional: false
    Mounts:
      /data from data (rw)
Events:
  Warning  Unhealthy  Liveness probe failed: context deadline exceeded
"""


def fake_cluster(tmp: Path, pods: str, logs: str) -> dict[str, str]:
    """A use case `demo` whose verify Job is demo-verify, and a kubectl answering `get pods`, `logs` and, for a
    restarted pod, `get pod` (the restarted container names), `describe pod` and `logs --previous`."""
    uc_root = tmp / "usecases"
    (uc_root / "demo").mkdir(parents=True)
    (uc_root / "demo" / "usecase.yaml").write_text("metadata: {name: demo}\nspec:\n  jobs:\n    verify: {name: demo-verify}\n")
    (tmp / "pods.txt").write_text(pods)
    (tmp / "logs.txt").write_text(logs)
    (tmp / "describe.txt").write_text(DESCRIBE)
    (tmp / "previous.txt").write_text("worker booting\nfatal: cannot reach orders\n")
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    kubectl = bin_dir / "kubectl"
    kubectl.write_text(
        f'#!/bin/sh\necho "$*" >> "{tmp}/calls.txt"\ncase " $* " in\n'
        f'  *" get pods "*) cat "{tmp}/pods.txt" ;;\n'
        f'  *" get pod "*) echo worker ;;\n'
        f'  *" describe pod "*) cat "{tmp}/describe.txt" ;;\n'
        f'  *" logs "*" --previous "*) cat "{tmp}/previous.txt" ;;\n'
        f'  *" logs "*) cat "{tmp}/logs.txt" ;;\nesac\n'
    )
    kubectl.chmod(kubectl.stat().st_mode | stat.S_IEXEC)
    return {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{REPO / '.tools' / 'bin'}{os.pathsep}{os.environ['PATH']}", "UC_ROOT": str(uc_root), "FORJATE_TOOLCHAIN": "warn"}


def bash(env: dict[str, str], script: str) -> subprocess.CompletedProcess:
    pre = f'set -euo pipefail; source "{LIB}/log.sh"; source "{LIB}/usecase.sh"; source "{LIB}/health.sh"; '
    return subprocess.run(["bash", "-c", pre + script], capture_output=True, text=True, env=env)


HEALTHY = "api-7d9\t0 0 \nworker-5c4\t0 \nseed-job-x\t0 \n"
RESTARTED = "api-7d9\t0 0 \nworker-5c4\t3 1 \nseed-job-x\t0 \n"   # a container restarted 3 times, an init container once
LOGS = "noise\n  KPI straight_through_rate=0.85\n  EVAL field_accuracy=0.97\nPASS everything\n"


def test_no_restart_is_reported_as_zero(tmp_path: Path):
    env = fake_cluster(tmp_path, HEALTHY, LOGS)
    r = bash(env, "record_health demo uc-demo")
    assert r.returncode == 0, r.stderr
    assert "HEALTH pod_restarts_after_verify=0" in r.stdout
    assert "restarted_pod" not in r.stdout


def test_restarts_are_summed_across_containers_and_the_pod_is_named(tmp_path: Path):
    env = fake_cluster(tmp_path, RESTARTED, LOGS)
    r = bash(env, "record_health demo uc-demo; echo total=$HEALTH_RESTARTS")
    assert "HEALTH pod_restarts_after_verify=4" in r.stdout
    assert "HEALTH restarted_pod=worker-5c4 restarts=4" in r.stdout
    assert "total=4" in r.stdout


def test_a_restarted_pod_prints_its_last_state_and_previous_logs(tmp_path: Path):
    r = bash(fake_cluster(tmp_path, RESTARTED, LOGS), "record_health demo uc-demo")
    assert r.returncode == 0, r.stderr
    assert "DIAG describe pod worker-5c4" in r.stdout
    assert "Exit Code:    137" in r.stdout and "Liveness probe failed" in r.stdout
    assert "DIAG previous logs worker-5c4/worker" in r.stdout
    assert "fatal: cannot reach orders" in r.stdout
    assert "logs worker-5c4 -c worker --previous" in (tmp_path / "calls.txt").read_text()


def test_the_describe_output_drops_the_environment_block(tmp_path: Path):
    r = bash(fake_cluster(tmp_path, RESTARTED, LOGS), "record_health demo uc-demo")
    assert "literal-secret-value" not in r.stdout and "API_TOKEN" not in r.stdout and "DB_PASSWORD" not in r.stdout
    assert "Mounts:" in r.stdout and "worker-config  ConfigMap" in r.stdout


def test_a_healthy_run_asks_for_no_diagnostics(tmp_path: Path):
    r = bash(fake_cluster(tmp_path, HEALTHY, LOGS), "record_health demo uc-demo")
    assert "DIAG" not in r.stdout
    assert "describe" not in (tmp_path / "calls.txt").read_text()


def test_kpi_and_eval_lines_of_the_verify_log_are_collected_sorted(tmp_path: Path):
    env = fake_cluster(tmp_path, HEALTHY, LOGS)
    r = bash(env, "record_health demo uc-demo; printf '%s\\n' \"$HEALTH_KPIS\"")
    assert "HEALTH kpi_lines=2" in r.stdout
    assert r.stdout.splitlines()[-2:] == ["EVAL field_accuracy=0.97", "KPI straight_through_rate=0.85"]


def test_a_log_without_kpi_lines_counts_zero(tmp_path: Path):
    env = fake_cluster(tmp_path, HEALTHY, "PASS everything\n")
    assert "HEALTH kpi_lines=0" in bash(env, "record_health demo uc-demo").stdout


def test_equal_kpis_on_a_second_up(tmp_path: Path):
    r = bash(fake_cluster(tmp_path, HEALTHY, LOGS), 'compare_kpis "KPI a=1" "KPI a=1"')
    assert r.returncode == 0 and "HEALTH kpi_second_up=equal" in r.stdout


def test_a_kpi_that_moved_between_the_two_ups_fails_and_shows_both_values(tmp_path: Path):
    r = bash(fake_cluster(tmp_path, HEALTHY, LOGS), 'compare_kpis "KPI a=0.85" "KPI a=0.80"')
    assert r.returncode == 1
    assert "HEALTH kpi_second_up=differs" in r.stdout
    assert "HEALTH kpi_diff < KPI a=0.85" in r.stdout and "HEALTH kpi_diff > KPI a=0.80" in r.stdout


def test_no_kpi_on_either_up_is_unmeasured_not_equal(tmp_path: Path):
    r = bash(fake_cluster(tmp_path, HEALTHY, LOGS), 'compare_kpis "" ""')
    assert r.returncode == 0 and "HEALTH kpi_second_up=unmeasured" in r.stdout


def test_up_takes_the_stability_flag_and_rejects_unknown_ones():
    assert "--stability" in subprocess.run([str(EPHEMERAL), "help"], capture_output=True, text=True).stdout
    r = subprocess.run([str(EPHEMERAL), "up", "demo", "--bogus"], capture_output=True, text=True)
    assert r.returncode != 0 and "Unknown flag for up: --bogus" in r.stdout + r.stderr


def test_the_nightly_asks_for_the_stability_run():
    text = (REPO / ".github" / "workflows" / "usecase-e2e-nightly.yml").read_text()
    assert '"${{ matrix.usecase }}" --stability' in text


def test_the_nightly_installs_pinned_checksummed_tools_and_authenticates_the_github_api():
    text = (REPO / ".github" / "workflows" / "usecase-e2e-nightly.yml").read_text()
    pin = (REPO / ".github" / "toolchain.env").read_text()
    assert "install_kustomize.sh" not in text and "k3d-io/k3d/main/install.sh" not in text
    for var in ("K3D_VERSION", "K3D_LINUX_AMD64_SHA256", "KUSTOMIZE_VERSION", "KUSTOMIZE_LINUX_AMD64_SHA256"):
        assert f"{var}=" in pin and f"${{{var}}}" in text
    assert text.count("sha256sum -c -") == 2
    assert "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in text
