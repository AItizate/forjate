# Human administrators of OpenBao

`scripts/openbao/bootstrap.sh` gives every human administrator an identity, so that day-to-day administration never needs the root token. This guide covers how people log in, how to add and remove them, and what is still pending.

## The model

```
 auth/userpass  ── alias <name> ──►  identity <name>  ──►  group "admins"  ──►  policy "admin"
 (today)                                                         ▲
 auth/oidc      ── alias <email> ─►  identity <name>  ───────────┘
 (pending)
```

The **group `admins`** carries the `admin` policy, not the login method. That is what lets a second method (OIDC) be added later without touching any policy: it only adds another alias to the same identity.

The `admin` policy covers policies, auth methods, engines, identities and Raft restore. It is close to root: an admin can rewrite policies, **including its own**. Its purpose is to keep the root token out of daily use and to leave an audited identity per person, not to limit a malicious admin.

## First setup

```sh
BAO_ADDR=... BAO_TOKEN=<root token from `bao operator init`> \
  scripts/openbao/bootstrap.sh agent,deploy alice,bob
```

The second argument lists the administrators (letters, digits, `.`, `_`, `-`). For each one the script creates an identity, a `userpass` alias and a `userpass` account whose password **nobody knows**: it is random and never printed. The account cannot be used yet.

Set each person's password with the root token, reading it without echo and passing it on stdin so it stays out of the process list:

```sh
read -rs PW
printf '{"password":"%s"}' "$PW" | bao write auth/userpass/users/alice/password -
unset PW
```

Then the person logs in, and changes the password with the same command (their `admin` policy covers it):

```sh
bao write -field=token auth/userpass/login/alice password=...
```

Admin tokens last **8 hours** (24 at most). When at least one admin can log in and has run `bootstrap.sh` successfully with their own token, revoke the root token:

```sh
bao token revoke -self      # with the root token
```

`bootstrap.sh` works with an admin token, so re-running it later does not need root.

## Adding and removing administrators

- **Add**: run `bootstrap.sh` again with the new name in the list, then set the password as above. Existing accounts and their passwords are not touched.
- **Remove**: the script never removes anyone, so a mistake in the list cannot lock everybody out. Remove a person on purpose:

```sh
bao delete auth/userpass/users/alice
bao delete identity/entity/name/alice     # also drops the membership in admins
```

  Tokens already issued keep working until they expire (at most 24 hours) unless you revoke them.

## Pending: OIDC

`userpass` is the baseline because it needs nothing outside the cluster. For real teams the better method is OIDC against the organisation's identity provider (MFA and offboarding handled in one place). It is **not implemented**:

- `auth/oidc` is not enabled by `bootstrap.sh`.
- There is **no ephemeral use case** that proves it yet. It needs an identity provider inside the k3d cluster to log in against, and the check that a person who logs in through OIDC lands in `admins` and can run `bootstrap.sh`. Tracked in the plan (`docs/openbao-plan.md`, follow-ups).

Until then, the same identity gets an extra alias when OIDC arrives; the group and the policy do not change.
