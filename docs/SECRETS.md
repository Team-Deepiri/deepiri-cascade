# Cascade secrets setup

> **Action required:** @Team-Deepiri/it-management-team — please configure the secrets and App settings below so cascade can open dependency PRs across the org.

Checklist for wiring up **deepiri-cascade** end to end: GitHub Actions, the Cloudflare Worker webhook, and the GitHub App.

Repo: **Team-Deepiri/deepiri-cascade**  
Settings path: **Settings → Secrets and variables → Actions**

---

## Required — GitHub Actions secrets

Add these four secrets in the **deepiri-cascade** repository.

| Secret | Used by | Value |
|--------|---------|-------|
| `APP_ID` | `cascade.yml`, `reusable.yml` | Numeric ID of the `deepiri-cascade` GitHub App |
| `APP_PRIVATE_KEY` | `cascade.yml`, `reusable.yml` | Full contents of the App `.pem` file (include `-----BEGIN/END RSA PRIVATE KEY-----` lines) |
| `CLOUDFLARE_API_TOKEN` | `deploy.yml` | Cloudflare API token with permission to deploy Workers |
| `CLOUDFLARE_ACCOUNT_ID` | `deploy.yml` | Cloudflare account ID (Wrangler / dashboard) |

### How each workflow uses them

| Workflow | Secrets |
|----------|---------|
| `cascade.yml` | `APP_ID`, `APP_PRIVATE_KEY` → mints an installation token to clone repos, bump deps, and open PRs |
| `deploy.yml` | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` → runs `wrangler deploy` when `worker/` changes on `main` |
| `monitor.yml` | *(none — uses built-in `GITHUB_TOKEN`)* |
| `monitor-push.yml` | *(none — uses built-in `GITHUB_TOKEN`)* |

---

## Automatic — do not add manually

| Name | Provided by | Purpose |
|------|-------------|---------|
| `GITHUB_TOKEN` | GitHub Actions | Tag monitor and push monitor poll the org and fire `repository_dispatch` to start `cascade.yml` |

No configuration needed unless you tighten default workflow permissions at the org level (these workflows need `contents: write` and `pull-requests: write` on `cascade.yml`).

---

## Required — Cloudflare Worker secrets

These are **not** GitHub Actions secrets. Set them with Wrangler from the repo root or `worker/`:

```bash
cd worker
wrangler login
wrangler secret put GITHUB_APP_ID
wrangler secret put GITHUB_APP_PRIVATE_KEY
wrangler deploy
```

| Worker secret | Value |
|---------------|-------|
| `GITHUB_APP_ID` | Same number as Actions `APP_ID` |
| `GITHUB_APP_PRIVATE_KEY` | Same PEM as Actions `APP_PRIVATE_KEY` |

The worker receives GitHub App webhooks (tag create + default-branch push) and dispatches `cascade-trigger` to `deepiri-cascade`.

After merging worker changes to `main`, `deploy.yml` redeploys automatically when the four Actions secrets above are set.

---

## GitHub App configuration

Create or verify the App at **GitHub → Developer settings → GitHub Apps → deepiri-cascade** (org admins: organization settings → GitHub Apps).

### Permissions

| Permission | Level |
|------------|-------|
| Repository contents | Read and write |
| Pull requests | Read and write |
| Metadata | Read |

Contents write is required so cascade can push branches and open PRs in consumer repos.

### Subscribed events

| Event | Why |
|-------|-----|
| **Push** | Default-branch merges (submodule cascade) |
| **Create** | New semver tags `vX.Y.Z` (dependency cascade) |
| **Repository dispatch** | Worker / monitor triggers `cascade.yml` |

### Installation

Install the App on **Team-Deepiri** with access to all repos cascade should update (or an explicit allow list).

### Webhook

Set the App webhook URL to the deployed Cloudflare Worker URL (from `wrangler deploy` output).

---

## Optional — `NODE_AUTH_TOKEN`

Only needed if cascade PRs fail during `npm install` / lock regeneration for private `@team-deepiri` packages on GitHub Packages.

| Secret | When to add |
|--------|-------------|
| `NODE_AUTH_TOKEN` | Fine-grained or classic PAT with `read:packages`, if the App installation token is not sufficient |

Cascade writes `.npmrc` with `//npm.pkg.github.com/:_authToken=${NODE_AUTH_TOKEN}` and passes the App token at runtime. See [IT_SECRETS_RUNBOOK.md](./IT_SECRETS_RUNBOOK.md) for incident response and rotation.

---

## Setup checklist

@Team-Deepiri/it-management-team

- [ ] GitHub App created with permissions and events above
- [ ] App installed on **Team-Deepiri**
- [ ] Actions secrets: `APP_ID`, `APP_PRIVATE_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`
- [ ] Worker secrets: `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`
- [ ] Worker deployed; App webhook URL points at worker
- [ ] Merge cascade to `main` so `deploy.yml` can auto-publish worker updates

### Smoke tests

1. **Tag trigger** — push `vX.Y.Z` on a library repo (e.g. `deepiri-gpu-utils`). Expect a cascade PR in consumers with `tag=` or `rev=` updated per pin style.
2. **Push trigger** — merge to `main` on a platform service. Expect a submodule pointer PR in `deepiri-platform` (or run `monitor-push.yml` manually).
3. **Manual** — Actions → **Cascade Update** → **Run workflow** with `repo`, `tag` or `sha`, and `trigger`.

---

## Rotating credentials

@Team-Deepiri/it-management-team — use this when rotating App keys or responding to a leaked token.

To rotate the App private key, update **both** Actions secrets (`APP_PRIVATE_KEY`) and Worker secrets (`GITHUB_APP_PRIVATE_KEY`), then revoke the old key in the App settings. Full steps: [IT_SECRETS_RUNBOOK.md](./IT_SECRETS_RUNBOOK.md#2-rotate-the-deepiri-cascade-github-app-credentials).
