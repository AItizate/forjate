# Token used by the raft-snapshot CronJob (Secret openbao-snapshot-token).
path "sys/storage/raft/snapshot" {
  capabilities = ["read"]
}
