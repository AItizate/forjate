# Security baseline (example)

What a security reviewer checks before a use case leaves Crawl.

1. Every workload runs with a `securityContext` compatible with Pod Security Admission `restricted`.
2. Namespaces ship a default-deny NetworkPolicy; egress is allow-listed per workload.
3. No secret is stored in git in plaintext. Sealed Secrets is the floor; External Secrets is the production mechanism.
4. Any HTTP surface sits behind the org identity provider (GoTrue + oauth2-proxy or equivalent).
5. Prompts and tool calls that touch regulated data are logged with the data class, not the payload.
6. Model egress is documented: which model, which provider, which region, which data classes.
