# One AI agent. The agent's name is the same whichever way it logs in:
#   - inside the cluster: ServiceAccount <name> in the agents namespace (auth/kubernetes, role "agent")
#   - outside the cluster: AppRole whose role_id is <name> (auth/approle)
#
# Why metadata for kubernetes: the alias is named <namespace>/<serviceaccount> and
# OpenBao refuses a "/" inside a template value, so the policy uses the alias
# metadata field service_account_name. For AppRole the alias name is the role_id.
# One file serves every agent. bootstrap.sh replaces the two placeholders below
# with the accessors of the auth mounts, so this file is not valid HCL policy on its own.
#
# Each agent:
#   - reads only kv/agents/<name>/*
#   - asks the SSH CA for a short-lived certificate (role "agent": TTL 30m, max 1h)
# See docs/tenant-onboarding/agent-secrets.md.
path "kv/data/agents/{{identity.entity.aliases.__ACCESSOR_KUBERNETES__.metadata.service_account_name}}/*" {
  capabilities = ["read"]
}

path "kv/data/agents/{{identity.entity.aliases.__ACCESSOR_APPROLE__.name}}/*" {
  capabilities = ["read"]
}

path "ssh-client/sign/agent" {
  capabilities = ["update"]
}
