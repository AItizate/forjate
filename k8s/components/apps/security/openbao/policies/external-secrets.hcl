# External Secrets Operator (auth/kubernetes role "external-secrets").
# Reads workload secrets and nothing else.
path "kv/data/workloads/*" {
  capabilities = ["read"]
}
