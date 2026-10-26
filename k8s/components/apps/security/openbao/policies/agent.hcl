# One AI agent, identified by its identity entity name.
#   - reads only its own kv path
#   - asks the SSH CA for a short-lived certificate (role "agent": TTL 30m, max 1h)
# Create one entity per agent and attach this policy to it (docs/tenant-onboarding/agent-secrets.md).
path "kv/data/agents/{{identity.entity.name}}/*" {
  capabilities = ["read"]
}

path "ssh-client/sign/agent" {
  capabilities = ["update"]
}
