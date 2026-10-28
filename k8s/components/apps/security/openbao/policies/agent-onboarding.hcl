# Automation that registers agents (a CI job, a controller). Not a human, not admin.
#   - writes (never reads) the agent's secrets under kv/agents/
#   - manages AppRoles named agent-*  (external agents; role_id = the agent's name)
# The names it chooses are the agents' identities, so this automation is the trust
# root for who an agent is: keep its token out of reach of the agents themselves.
# In-cluster agents need nothing here: a ServiceAccount in the agents namespace is enough.
path "kv/data/agents/*" {
  capabilities = ["create", "update"]
}

path "kv/metadata/agents/*" {
  capabilities = ["list", "delete"]
}

# A trailing * matches everything below, so this one rule also covers role-id and
# secret-id under agent-*, with the same parameter limits (no secret-id options,
# so secret-ids are created with the role's own TTL). Rotating or killing an
# external agent = delete its role and create it again: the role_id is fixed, the
# old secret-ids die with the role.
#
# The roles it creates can only carry the agent policy: without allowed_parameters
# this path would let it mint a role with policy admin and log in as it.
path "auth/approle/role/agent-*" {
  capabilities = ["create", "read", "update", "delete"]
  allowed_parameters = {
    "role_id"            = []
    "bind_secret_id"     = [true]
    "token_policies"     = ["agent"]
    "token_ttl"          = []
    "token_max_ttl"      = []
    "secret_id_ttl"      = []
    "secret_id_num_uses" = []
    "token_bound_cidrs"  = []
    "secret_id_bound_cidrs" = []
  }
}

path "auth/approle/role" {
  capabilities = ["list"]
}
