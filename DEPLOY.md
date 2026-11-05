# D2 web app and disposable Docker sandbox

## Architecture

- The web/API process runs on a Vultr Cloud Compute host.
- Every task runs in a fresh browser container; the container is removed after
  success, failure, or timeout.
- The browser container joins a per-task Docker network marked `--internal`.
  It has no direct internet route.
- A short-lived proxy sidecar is attached to that internal network and the
  external bridge. It accepts HTTPS CONNECT only, checks the task allowlist,
  resolves the host once, rejects non-global IPs, and connects to the checked
  numeric address. The browser container cannot reach the proxy's external
  interface except through the proxy process.
- The browser container receives only a read-only task JSON mount and a
  writable temporary output mount. It receives no Docker socket, credentials,
  host home directory, or persistent browser profile.
- The web API accepts HTTPS URL + CSS extraction fields only. It does not
  expose click, fill, download, or arbitrary browser-argument controls.

## Build the sandbox image

On the Vultr host, install Docker Engine and Python 3.12, then:

```sh
docker build -t qbc-sandbox:latest .
```

The image contains Playwright Chromium, the runner, and the egress proxy.

## Run the web service

Create a dedicated unprivileged host account (UID/GID 10001 recommended),
a persistent data directory owned by that account, and a strong random
`QBC_DEMO_TOKEN`. Never put the token in Git.

```sh
install -d -o qbc -g qbc -m 0700 /var/lib/qbc
export QBC_DB_PATH=/var/lib/qbc/tasks.sqlite3
export QBC_WORK_ROOT=/var/lib/qbc/sandboxes
export QBC_SANDBOX_IMAGE=qbc-sandbox:latest
export QBC_DEMO_TOKEN='<secret from approved secret custody>'
uvicorn web.app:app --host 127.0.0.1 --port 8000
```

Place a TLS reverse proxy in front of the service and expose only HTTPS.
Keep Docker's remote API disabled. Restrict SSH to the operator's management
path. Do not expose port 3128 or any task network to the public internet.

## Runtime limits and fail-closed behavior

- Two active tasks maximum per app process.
- Task timeout is bounded to 15–180 seconds.
- Browser container: read-only root filesystem, no capabilities, no-new-
  privileges, bounded memory/CPU/PIDs, isolated internal network.
- Proxy: no capabilities, read-only root filesystem, bounded memory/CPU/PIDs.
- The app requires `QBC_DEMO_TOKEN`; the task API returns 503 when it is
  absent. Docker startup failure is a task failure; there is no local-browser
  fallback.
- Only public HTTPS destinations matching the allowlist are permitted by the
  proxy. DNS answers containing private/reserved addresses are rejected.

## Evidence boundary

This is the deployment recipe and sandbox implementation. It does not prove a
Vultr deployment or key-bearing execution. The D2 submission packet remains
blocked until the host is provisioned, the service is deployed, a real task
is executed and destroyed, and the public App URL is verified.
