"""The oauth2-proxy example against the Secret the zitadel bootstrap writes.

This is integration between two components, so it lives with the example and not in
the zitadel component (whose tests may not name another component). CI runs it from
validate-zitadel.yml.
"""
from pathlib import Path

import yaml

EXAMPLE = Path(__file__).resolve().parents[1]


def test_oauth2_example_verifies_tls_and_reads_the_secret_the_bootstrap_writes():
    values = yaml.safe_load((EXAMPLE / "oauth2-values-zitadel.yaml").read_text())
    assert "ssl-insecure-skip-verify" not in values["extraArgs"]
    refs = {(e["valueFrom"]["secretKeyRef"]["name"], e["valueFrom"]["secretKeyRef"]["key"])
            for e in values["extraEnv"] if e["name"] != "OAUTH2_PROXY_COOKIE_SECRET"}
    assert refs == {("zitadel-oidc-oauth2-proxy", "client-id"), ("zitadel-oidc-oauth2-proxy", "client-secret")}
    # ... which is what the bootstrap writes for the application the example declares
    apps = yaml.safe_load((EXAMPLE / "bootstrap-application.yaml").read_text())
    assert [a["name"] for a in apps] == ["oauth2-proxy"]
    assert values["extraArgs"]["oidc-groups-claim"] == "groups"
