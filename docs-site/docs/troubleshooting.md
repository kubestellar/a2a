---
sidebar_position: 4
---

# Troubleshooting

This guide highlights frequent stumbling blocks when setting up or running KubeStellar A2A and offers quick fixes for each scenario.

## Quick Diagnostics

Run these commands first—they answer most “is it installed/configured?” questions.

```bash
# Confirm CLI version and that uv tooling works
uv run kubestellar --version

# Inspect function registry for the active mode
uv run kubestellar list-functions

# Smoke test kubeconfig resolution
uv run kubestellar execute get_kubeconfig

# Enable verbose logging for a single call
uv run kubestellar execute get_kubeconfig --debug
```

## CLI & Tooling Installation

### `kubectl a2a` Not Found

**Symptom**: `kubectl a2a` returns `plugin not found` or the binary is missing.

**Fix**:
- Ensure `uv tool install kubestellar` completed successfully.
- Confirm `~/.local/bin` (Linux/macOS) or `%USERPROFILE%\.local\bin` (Windows) is on your `PATH`.
- Reinstall to regenerate the shim: `uv tool install kubestellar --force`.

### Missing Python Dependencies

**Symptom**: `ModuleNotFoundError: click` (or similar) when running `uv run` or tests.

**Fix**:
- Synchronize dev extras: `uv pip install -r pyproject.toml#dev` or `uv sync --dev`.
- Verify you are executing commands inside the repository root so `.venv` is used.

### `uv` Command Not Found

**Fix**:
- Install via curl: `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- Reload your shell (`source ~/.bashrc` or restart terminal).
- Windows users can run `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`.

## Mode Detection & kubeconfig Troubles

### Wrong Provider Mode Selected

**Symptom**: CLI defaults to `kubestellar` when you expected vanilla Kubernetes (or vice versa).

**Fix**:
- Override explicitly with `--mode kubernetes` or `--mode kubestellar`.
- Remove stale WDS/ITS contexts from your kubeconfig if they’re no longer valid.

### Function Missing After Switching kubeconfig

**Cause**: The function registry is tied to the detected mode; new kubeconfig wasn’t reinitialised.

**Fix**:
- Re-run the command with `--mode` or `--kubeconfig` flags (forces rebuild).
- If using the CLI group interactively, start a fresh shell session to reset context.

### `context ... not found`

**Fix**:
- Merge KubeStellar contexts with your default config:
  ```bash
  KUBECONFIG=~/.kube/config:~/.kube/kubestellar.yaml     kubectl config view --flatten > ~/.kube/merged
  export KUBECONFIG=~/.kube/merged
  ```
- Point CLI commands at the merged file with `--kubeconfig`.

## Kubernetes Connectivity

### TLS / CA Errors

**Symptom**: `x509: certificate signed by unknown authority`.

**Fix**:
- Ensure the kubeconfig references a CA file that exists on disk.
- Re-export kubeconfig from cluster admin tooling if certificates have rotated.

### Access Denied / Forbidden

**Fix**:
- Verify RBAC permissions: `kubectl auth can-i '*' '*' --all-namespaces`.
- Switch to an admin context or request elevated credentials.

## Helm & BindingPolicy Operations

### Repo Not Found

**Symptom**: `Error: repository name (kubestellar) not found`.

**Fix**:
- Add the Helm repo: `helm repo add kubestellar https://charts.kubestellar.io && helm repo update`.
- Override the `repo_url` parameter in `helm_deploy` if using a mirror.

### CRDs Missing

**Symptom**: `no matches for kind "BindingPolicy"` while deploying.

**Fix**:
- Apply KubeStellar CRDs to the target cluster: `kubectl apply -k manifests/crds`.
- Confirm presence with `kubectl get crd bindingpolicies.control.kubestellar.io`.

## Redis / Backend Service Issues

### Redis Unreachable

**Symptom**: API returns `unable to reach Redis`.

**Fix**:
- Verify Redis host/port credentials.
- Restart Redis or update environment variables (`REDIS_HOST`, `REDIS_PORT`).

### Stale Data After Delete

**Symptom**: BindingPolicy appears again after deletion.

**Fix**:
- Clear cached keys: `redis-cli --scan --pattern 'bindingpolicy:*' | xargs redis-cli del`.
- Restart the controller to rebuild in-memory cache.

## Debug Logging

Need detailed traces? Enable verbose mode:

```bash
kubectl a2a debug --enable          # global toggle
kubectl a2a execute ... --debug     # per-command
```

Verbose logs are emitted under the `kubestellar.*` logger namespace.

## Still Stuck?

Gather CLI output (use `--debug`), controller logs, and relevant kubeconfig snippets, then open an issue or reach the maintainers through the project’s support channel.
