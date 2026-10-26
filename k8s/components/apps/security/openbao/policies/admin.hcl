# Day-2 administration without the root token. Revoke the root token once an
# admin token with this policy exists.

# Policies, auth methods, secret engines, audit devices
path "sys/policies/acl/*"      { capabilities = ["create", "read", "update", "delete", "list"] }
path "sys/policies/acl"        { capabilities = ["list"] }
path "sys/auth/*"              { capabilities = ["create", "read", "update", "delete", "sudo"] }
path "sys/auth"                { capabilities = ["read"] }
path "sys/mounts/*"            { capabilities = ["create", "read", "update", "delete", "sudo"] }
path "sys/mounts"              { capabilities = ["read"] }
path "sys/audit*"              { capabilities = ["create", "read", "update", "delete", "sudo", "list"] }

# What those engines and methods hold
path "auth/*"                  { capabilities = ["create", "read", "update", "delete", "list", "sudo"] }
path "identity/*"              { capabilities = ["create", "read", "update", "delete", "list"] }
path "kv/*"                    { capabilities = ["create", "read", "update", "delete", "list"] }
path "ssh-client/*"            { capabilities = ["create", "read", "update", "delete", "list"] }

# Raft: status, snapshot and restore (see raft-snapshot/)
path "sys/storage/raft/configuration"  { capabilities = ["read"] }
path "sys/storage/raft/snapshot"       { capabilities = ["read", "update"] }
path "sys/storage/raft/snapshot-force" { capabilities = ["update"] }
