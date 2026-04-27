Of course. Here is a direct, command-focused README in Markdown for managing users.

---

# Managing Basic Auth Users for Traefik

This guide provides the steps to add or update users for the Traefik Basic Authentication middleware in Kubernetes.

The user credentials are not stored in Git; they are stored in a Kubernetes Secret named `basic-auth-secret`. The following steps show how to safely update this secret.

### Prerequisites

- `kubectl` installed and configured to access your cluster.
- `htpasswd` installed (`httpd-tools` or `apache2-utils` package).

---

## How to Add a New User

Follow these steps to add a new user without overwriting existing ones.

### Step 1: Fetch the Current User List

First, retrieve the current user list from the Kubernetes secret and decode it into a local file named `users.txt`. This ensures you are working with the most up-to-date version.

```bash
# Replace 'default' with the namespace where your secret is located
kubectl get secret basic-auth-secret -n default -o jsonpath='{.data.users}' | base64 -d > users.txt
```

### Step 2: Add the New User to the File

Use `htpasswd` to add the new user. It will prompt you for a password.

**Important:** Do **not** use the `-c` flag, as this will create a new file and delete all existing users.

```bash
# Replace '<new-username>' with the desired username
htpasswd users.txt <new-username>
```

### Step 3: Update the Kubernetes Secret

Encode the updated `users.txt` file and use `kubectl patch` to update the secret in the cluster. This single command handles the entire update.

```bash
# Replace 'default' with your namespace
NEW_USERS_BASE64=$(cat users.txt | base64) && kubectl patch secret basic-auth-secret -n default -p '{"data":{"users":"'"$NEW_USERS_BASE64"'"}}'
```

### Step 4: Verification and Cleanup

Traefik will automatically detect the updated secret within a few moments. No pod restart is needed.

1.  Try to log in to your service with the new user credentials.
2.  For security, delete the local `users.txt` file.

    ```bash
    rm users.txt
    ```