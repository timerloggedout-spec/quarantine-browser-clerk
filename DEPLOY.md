# D2 web app and disposable Docker sandbox

## Architecture

- The web/API process runs on a Vultr Cloud Compute host.
- Every task runs in a fresh browser container; the container is removed after
  success, failure, or timeout.
- A short-lived proxy sidecar is attached to the external Docker bridge.
  The browser container joins the proxy's network namespace with a separate
  UID and no network-administration capabilities.
- The proxy installs namespace-local firewall rules before listening:
  browser UID 10001 may open only TCP connections to loopback port 3128;
  proxy UID 10002 may open DNS/53 and HTTPS/443 only. The policy is applied
  to both IPv4 and IPv6; all other output is dropped.
  The proxy process installs these rules as root, then drops to UID/GID 10002.
- The proxy accepts HTTPS CONNECT only, checks the task allowlist, resolves
  the host once, rejects non-global IPs, and connects to the checked numeric
  address. The browser cannot bypass it with direct TCP, UDP, or DNS sockets.
- The browser container receives only a read-only task JSON mount and a
  writable temporary output mount. It receives no Docker socket, credentials,
  host home directory, or persistent browser profile.
- The web API accepts HTTPS URL + CSS extraction fields only. It does not
  expose click, fill, download, or arbitrary browser-argument controls.

## Build the sandbox image

On the Vultr host, install Docker Engine and Python 3.12. Install the
application dependencies in a dedicated virtual environment, then build the
sandbox image:

```sh
python3 -m venv /opt/qbc-venv
/opt/qbc-venv/bin/pip install -r requirements.txt
docker build -t qbc-sandbox:latest .
```

The image contains Playwright Chromium, the runner, and the egress proxy.

## Run the web service

Create a dedicated unprivileged host account (UID/GID 10001 recommended),
a persistent data directory owned by that account, and a strong random
`QBC_DEMO_TOKEN`. The service account requires Docker daemon access, which is
root-equivalent; restrict that account to this service and never expose the
Docker socket to task containers. Never put the token in Git.

```sh
install -d -o qbc -g qbc -m 0700 /var/lib/qbc
export QBC_DB_PATH=/var/lib/qbc/tasks.sqlite3
export QBC_WORK_ROOT=/var/lib/qbc/sandboxes
export QBC_SANDBOX_IMAGE=qbc-sandbox:latest
export QBC_DEMO_TOKEN='<secret from approved secret custody>'
/opt/qbc-venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8000
```

Run a single Uvicorn worker (startup recovery owns the QBC Docker namespace). Place a TLS reverse proxy in front of the service and expose only HTTPS.
Keep Docker's remote API disabled. Restrict SSH to the operator's management
path. Do not expose port 3128 or the proxy container to the public internet. Configure the host firewall to deny proxy-sidecar access to host management services (including via the host's public IP), and validate the namespace firewall from inside a disposable task before opening the public demo.

## Runtime limits and fail-closed behavior

- One active task maximum by default (`QBC_MAX_ACTIVE_TASKS=1`); raise only after sizing the Vultr host and testing memory/CPU contention.
- Task timeout is bounded to 15–180 seconds.
- Browser container: read-only root filesystem, no capabilities, no-new-
  privileges, bounded memory/CPU/PIDs; shared proxy namespace with UID 10001
  egress limited to loopback TCP/3128.
- Proxy: read-only root filesystem and bounded memory/CPU/PIDs. NET_ADMIN,
  SETUID, and SETGID are granted only for firewall setup; supplementary groups
  are cleared and the process drops to UID/GID 10002 before serving. Both
  iptables and ip6tables restrict that UID to DNS/53 and TCP/443.
- The app requires `QBC_DEMO_TOKEN`; the task API returns 503 when it is
  absent. Startup recovery removes only QBC-labelled containers/networks and
  stale `qbc-*` task workspaces, then marks interrupted DB tasks failed.
  Docker startup failure is a task failure; there is no local-browser fallback.
- Only public HTTPS destinations matching the allowlist are permitted by the
  proxy. DNS answers containing private/reserved addresses are rejected.

## Evidence boundary

This is the deployment recipe and sandbox implementation. It does not prove a
Vultr deployment or key-bearing execution. The D2 submission packet remains
blocked until the host is provisioned, the service is deployed, a real task
is executed and destroyed, and the public App URL is verified.
