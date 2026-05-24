# IT Secrets Runbook — Deepiri Platform & Cascade

Operational guide for admins with org/repo access. Covers the **PR #242 token leak**, GitHub App rotation, `NODE_AUTH_TOKEN` for npm/GitHub Packages, and application secrets for platform services.

---

## 1. Immediate response — leaked token in PR #242

**Do not merge** [deepiri-platform PR #242](https://github.com/Team-Deepiri/deepiri-platform/pull/242).

That PR was opened by `app/deepiri-cascade` and committed `.npmrc` files containing a literal GitHub App installation token (`ghs_…`). That is a security incident even though the token is short-lived.

| Step | Action | Who |
|------|--------|-----|
| 1 | **Close PR #242** without merging | Repo admin |
| 2 | Confirm no `.npmrc` files with `_authToken=ghs_` exist on `main` | Repo admin |
| 3 | **Merge the cascade fix** in `deepiri-cascade` so future PRs use `${NODE_AUTH_TOKEN}` instead of literal tokens | Repo admin |
| 4 | Re-run the cascade for `deepiri-shared-utils` v1.2.4 (or latest) to open a clean dependency PR | Cascade maintainer |
| 5 | Check **Settings → Code security → Secret scanning** alerts on `deepiri-platform` | Org admin |

### About the leaked token

- Prefix `ghs_` = **GitHub App installation access token** (generated at workflow runtime).
- These tokens **expire in about 1 hour** and cannot be manually revoked individually.
- The **private key was not leaked** — only a derived runtime token was committed to the PR branch.
- Rotating the GitHub App private key (Section 2) is optional but recommended if you want a clean break after an incident.

---

## 2. Rotate the Deepiri Cascade GitHub App credentials

Use this if you want to invalidate all future tokens minted from the current App key, or as post-incident hygiene.

### 2.1 Generate a new private key

1. Go to **GitHub → Settings → Developer settings → GitHub Apps → `deepiri-cascade`**  
   (Org admins: `https://github.com/organizations/team-deepiri/settings/apps/deepiri-cascade`)
2. Scroll to **Private keys → Generate a private key**.
3. Download the new `.pem` file. **Do not commit it.**

### 2.2 Update secrets everywhere the App is used

| Location | Secret name | Value |
|----------|-------------|-------|
| `Team-Deepiri/deepiri-cascade` → Settings → Secrets → Actions | `APP_ID` | App ID (unchanged unless you recreate the App) |
| Same repo | `APP_PRIVATE_KEY` | Full contents of the **new** `.pem` file |
| Cloudflare Worker (webhook) | `GITHUB_APP_ID` | Same App ID |
| Cloudflare Worker | `GITHUB_APP_PRIVATE_KEY` | Same new `.pem` contents |

```bash
# Cloudflare Worker secrets (from worker/ directory)
wrangler secret put GITHUB_APP_ID
wrangler secret put GITHUB_APP_PRIVATE_KEY
```

### 2.3 Revoke the old private key

1. Back in the GitHub App settings, under **Private keys**, click **Revoke** on the **old** key.
2. Trigger a test cascade run (push a tag or use workflow_dispatch) and confirm PRs still open correctly.

---

## 3. Set up `NODE_AUTH_TOKEN` for GitHub Packages (npm)

After the cascade fix, committed `.npmrc` files look like this (safe to commit):

```ini
@deepiri:registry=https://npm.pkg.github.com
@team-deepiri:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${NODE_AUTH_TOKEN}
```

npm reads the token from the **`NODE_AUTH_TOKEN` environment variable** at install time. No literal token belongs in git.

### 3.1 deepiri-cascade (already handled)

The cascade workflow generates an App token and passes it internally:

- Workflow: `.github/workflows/cascade.yml`
- App token → `GITHUB_TOKEN` env → cascade CLI → `NODE_AUTH_TOKEN` for `npm install`

**No extra secret required** in `deepiri-cascade` for npm auth once the fix is deployed.

### 3.2 deepiri-platform (and other repos that run `npm ci` / `npm install`)

Add a step before any npm install in CI workflows (e.g. `platform-build-and-test.yml`):

```yaml
- name: Configure npm for GitHub Packages
  uses: actions/setup-node@v4
  with:
    node-version: '20'
    registry-url: https://npm.pkg.github.com
    scope: '@team-deepiri'

- name: Install dependencies
  working-directory: platform-services/backend/deepiri-adaptive-experience-engine  # per service
  env:
    NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: npm ci
```

**Notes for IT:**

| Topic | Guidance |
|-------|----------|
| Same-org packages | `secrets.GITHUB_TOKEN` works if the workflow has `packages: read` permission |
| Cross-org or stricter scope | Create a fine-grained PAT or classic PAT with `read:packages`, store as repo secret `NODE_AUTH_TOKEN`, use `${{ secrets.NODE_AUTH_TOKEN }}` |
| Workflow permissions | Add to the job or workflow: `permissions: packages: read` |
| Local dev | Developers run `export NODE_AUTH_TOKEN=<pat-with-read-packages>` before `npm install` |

### 3.3 Optional: dedicated repo secret

If `GITHUB_TOKEN` is insufficient, create an org or repo secret:

1. **Settings → Secrets and variables → Actions → New repository secret**
2. Name: `NODE_AUTH_TOKEN`
3. Value: PAT with **`read:packages`** (and `repo` if installing from private git refs)

Use in workflows:

```yaml
env:
  NODE_AUTH_TOKEN: ${{ secrets.NODE_AUTH_TOKEN }}
```

---

## 4. Application secrets — platform services

Someone with **admin access to each repo** must add these under:

**Settings → Secrets and variables → Actions → New repository secret**

Add each secret to **every repo whose CI/deploy consumes that service**. If all services live in `Team-Deepiri/deepiri-platform`, add all secrets there once. If split across repos, add only where the “Used by” column applies.

| Secret | Used by |
|--------|---------|
| `JWT_SECRET` | api-gateway, auth-service |
| `INTERNAL_SERVICE_SECRET` | api-gateway, auth-service, external-bridge |
| `REDIS_PASSWORD` | api-gateway, auth-service, external-bridge, language-intelligence *(all 4)* |
| `POSTGRES_AUTH_PASSWORD` | auth-service |
| `POSTGRES_CORE_PASSWORD` | language-intelligence |

### 4.1 How to add a secret (repeat per secret, per repo)

1. Open the repo on GitHub (e.g. `Team-Deepiri/deepiri-platform`).
2. **Settings → Secrets and variables → Actions**.
3. Click **New repository secret**.
4. **Name**: exact name from the table (e.g. `JWT_SECRET`).
5. **Value**: production-grade random string (e.g. `openssl rand -hex 32`).
6. Save.

CI and deployment workflows reference these by name, e.g. `${{ secrets.JWT_SECRET }}`. GitHub injects the real value at runtime — **never** commit secrets to git or `.env` files in the repo.

### 4.2 Suggested secret generation

```bash
# 256-bit hex secret (good for JWT_SECRET, INTERNAL_SERVICE_SECRET)
openssl rand -hex 32

# Strong password (good for REDIS_PASSWORD, POSTGRES_*)
openssl rand -base64 24
```

Store generated values in your team password manager **before** pasting into GitHub Secrets (GitHub will not show the value again).

### 4.3 Rotation checklist (application secrets)

When rotating any secret below:

1. Generate a new value.
2. Update the GitHub Actions secret in each repo that uses it.
3. Update the runtime environment (Kubernetes/Docker/host) for the affected services **in the same maintenance window**.
4. Redeploy services in dependency order if needed (e.g. auth-service before api-gateway).
5. Verify health checks and a smoke test (login, API call, Redis/Postgres connectivity).

---

## 5. Secret inventory summary

| Secret | Where to store | Used for |
|--------|----------------|----------|
| `APP_ID` | `deepiri-cascade` Actions secrets | Cascade GitHub App |
| `APP_PRIVATE_KEY` | `deepiri-cascade` Actions secrets | Cascade GitHub App JWT |
| `GITHUB_APP_ID` | Cloudflare Worker | Webhook → dispatch |
| `GITHUB_APP_PRIVATE_KEY` | Cloudflare Worker | Webhook → dispatch |
| `NODE_AUTH_TOKEN` | Optional repo secret | npm install from GitHub Packages (if not using `GITHUB_TOKEN`) |
| `JWT_SECRET` | Platform repo(s) | API JWT signing |
| `INTERNAL_SERVICE_SECRET` | Platform repo(s) | Service-to-service auth |
| `REDIS_PASSWORD` | Platform repo(s) | Redis |
| `POSTGRES_AUTH_PASSWORD` | Platform repo(s) | Auth DB |
| `POSTGRES_CORE_PASSWORD` | Platform repo(s) | Core/language-intelligence DB |

---

## 6. Verification checklist

After completing the above:

- [ ] PR #242 closed, not merged
- [ ] Cascade fix merged and deployed
- [ ] New cascade PR has `.npmrc` with `${NODE_AUTH_TOKEN}` only (no `ghs_` / `ghp_` strings)
- [ ] Platform CI passes `npm ci` with `NODE_AUTH_TOKEN` set
- [ ] All application secrets from Section 4 present in target repos
- [ ] Old GitHub App private key revoked (if rotated)
- [ ] Secret scanning alerts reviewed and resolved

---

## Contacts / escalation

- **Cascade bot issues**: `Team-Deepiri/deepiri-cascade` maintainers
- **Platform CI / npm**: `Team-Deepiri/deepiri-platform` maintainers
- **Org-wide secret policy**: GitHub org owners
