# Cascade secrets setup

> **Action required:** @Team-Deepiri/it-management-team — please configure the secrets and App settings below so cascade can open dependency PRs across the org.

Checklist for wiring up **deepiri-cascade** end to end: GitHub Actions, the Cloudflare Worker webhook, and the GitHub App.

Repo: **Team-Deepiri/deepiri-cascade**  
Settings path: **Settings → Secrets and variables → Actions**

---

## CI/CD — what runs without secrets

| Workflow | Trigger | Secrets required | Status |
|----------|---------|------------------|--------|
| **CI** (`ci.yml`) | PR / push to `main`, `dev` | None | Runs pytest + Node checks on every PR |
| **CodeQL** (`codeql.yml`) | PR / push to `main`, `dev` | None | Security scan |
| **Tag Monitor** (`monitor.yml`) | Cron every 5 min | `GITHUB_TOKEN` (automatic) | Polls org tags → dispatches cascade |
| **Push Monitor** (`monitor-push.yml`) | Cron every 5 min | `GITHUB_TOKEN` (automatic) | Polls default-branch HEAD → dispatches cascade |
| **Cascade Update** (`cascade.yml`) | Dispatch / manual | `APP_ID`, `APP_PRIVATE_KEY` | **Blocked until App secrets are set** |
| **Deploy Worker** (`deploy.yml`) | After CI passes on `main` | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | **Blocked until Cloudflare secrets are set** |

**Summary:** CI and monitors work today with zero manual secrets. Cascade PR creation and worker deploy only need the four Actions secrets below (+ two Worker secrets via Wrangler). No other configuration is required.

---

## Required — GitHub Actions secrets

Add these four secrets in the **deepiri-cascade** repository.

| Secret | Used by | Value |
|--------|---------|-------|
| `APP_ID` | `cascade.yml`, `reusable.yml` | Numeric ID of the `deepiri-cascade` GitHub App |
| `APP_PRIVATE_KEY` | `cascade.yml`, `reusable.yml` | Full contents of the App `.pem` file (include `-----BEGIN ... PRIVATE KEY-----` and `-----END ... PRIVATE KEY-----` lines, with real newlines — not literal `\n`). If cascade logs `APP_PRIVATE_KEY does not look like a PEM`, re-download the key from the GitHub App settings and replace this secret. |
| `CLOUDFLARE_API_TOKEN` | `deploy.yml` | Cloudflare API token with permission to deploy Workers |
| `CLOUDFLARE_ACCOUNT_ID` | `deploy.yml` | Cloudflare account ID (Wrangler / dashboard) |

### How each workflow uses them

| Workflow | Secrets |
|----------|---------|
| `cascade.yml` | `APP_ID`, `APP_PRIVATE_KEY` → mints an installation token to clone repos, bump deps, and open PRs |
| `deploy.yml` | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` → runs `wrangler deploy` after CI passes on `main` |
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

After merging to `main`, `deploy.yml` publishes the worker automatically once CI passes (when the four Actions secrets above are set).

---

## GitHub App configuration

Create or verify the App at **GitHub → Developer settings → GitHub Apps → deepiri-cascade** (org admins: organization settings → GitHub Apps).

### Permissions

| Permission | Level |
|------------|-------|
| Repository contents | Read and write |
| Pull requests | Read and write |
| Administration | Read and write |
| Metadata | Read |

Contents write is required so cascade can push branches and open PRs in consumer repos. Administration write lets cascade turn on **Allow auto-merge** on consumer repos so dependency PRs merge automatically once CI passes.

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

- [ ] GitHub App created with permissions and events above (include **Administration: Read and write** for auto-merge)
- [ ] App installed on **Team-Deepiri**
- [ ] Actions secrets: `APP_ID`, `APP_PRIVATE_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`
- [ ] Worker secrets: `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`
- [ ] Worker deployed; App webhook URL points at worker
- [ ] Merge cascade to `main` so `deploy.yml` can auto-publish worker updates

### Smoke tests

1. **Tag trigger** — push `vX.Y.Z` on a library repo (e.g. `deepiri-gpu-utils`). Expect a cascade PR in consumers with `tag=` or `rev=` updated per pin style.
2. **Push trigger** — merge to `main` on a platform service. Expect a submodule pointer PR in `deepiri-platform` (or run `monitor-push.yml` manually).
3. **Manual** — Actions → **Cascade Update** → **Run workflow** with `repo`, `tag` or `sha`, and `trigger`.

### Auto-merge

Cascade enables **Allow auto-merge** on each consumer repo (when the App has **Administration: write**) and queues the PR via `enablePullRequestAutoMerge`. GitHub merges once required status checks pass.

If a repo still requires human review (`required_approving_review_count > 0`), auto-merge waits until someone approves. To fully automate dependency bumps, add the `deepiri-cascade` GitHub App to the branch protection **bypass** list for those repos.

---

## Troubleshooting — `Invalid keyData` in Cascade Update

If **Generate App token** fails with `Invalid keyData` / `header too long`:

1. **Action runtime** — cascade mints tokens with `scripts/mint_github_app_token.py` (PyJWT + cryptography), avoiding Node 24 `Invalid keyData` issues from `actions/create-github-app-token@v1`.
2. **App ID** — `APP_ID` must be the numeric GitHub App ID for the same App as the PEM (not empty, not a Client ID from the wrong field).
3. **Private key** — paste the **entire** downloaded `.pem` into `APP_PRIVATE_KEY`. PKCS#1 (`BEGIN RSA PRIVATE KEY`) is auto-converted in CI; PKCS#8 (`BEGIN PRIVATE KEY`) is preferred.
4. **Matching pair** — App ID and private key must belong to the same GitHub App installation on **Team-Deepiri**.

---

## Rotating credentials

@Team-Deepiri/it-management-team — **action required now (2026-07-03):** Cascade Update is failing because `APP_PRIVATE_KEY` in this repo is not a valid GitHub App PEM. Rotate/replace the secret before the next tag cascade.

### Rotate `APP_PRIVATE_KEY` now

1. Open **GitHub → Organization settings → GitHub Apps → `deepiri-cascade`**  
   (`https://github.com/organizations/team-deepiri/settings/apps/deepiri-cascade`)
2. Under **Private keys**, click **Generate a private key** and download the `.pem`.
3. In **Team-Deepiri/deepiri-cascade → Settings → Secrets and variables → Actions**, update:
   - `APP_PRIVATE_KEY` — paste the **entire** `.pem` (include `-----BEGIN ... PRIVATE KEY-----` / `-----END ... PRIVATE KEY-----`, real newlines)
   - `APP_ID` — confirm it is the **numeric App ID** for that same App (unchanged unless the App was recreated)
4. Update the Cloudflare Worker secrets to match (same PEM + App ID):
   ```bash
   cd worker
   wrangler secret put GITHUB_APP_ID
   wrangler secret put GITHUB_APP_PRIVATE_KEY
   ```
5. Revoke the old App private key in GitHub App settings after the new secret works.
6. Smoke test: **Actions → Cascade Update → Run workflow** with `repo=deepiri-training-orchestrator`, `tag=v0.4.1`, `trigger=tag`.

If the workflow still fails, check the **Generate App token** step — `scripts/mint_github_app_token.py` prints whether the PEM is invalid or the App ID/key pair mismatches.

---

@Team-Deepiri/it-management-team — use the section below when rotating App keys routinely or responding to a leaked token.

To rotate the App private key, update **both** Actions secrets (`APP_PRIVATE_KEY`) and Worker secrets (`GITHUB_APP_PRIVATE_KEY`), then revoke the old key in the App settings. Full steps: [IT_SECRETS_RUNBOOK.md](./IT_SECRETS_RUNBOOK.md#2-rotate-the-deepiri-cascade-github-app-credentials).
