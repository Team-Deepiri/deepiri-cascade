# Deepiri Cascade Setup Guide

Complete setup for automated dependency cascading across team-deepiri repos.

## Architecture Overview

```
┌─────────────────┐      webhook       ┌──────────────────┐
│  Any repo in    │ ──── push tag ───▶ │  GitHub App      │
│  team-deepiri   │                   │  (receives event)│
└─────────────────┘                   └────────┬─────────┘
                                               │
                                    API call    ▼
                                               ┌──────────────────┐
                              ┌──────────────▶ │ deepiri-cascade  │
                              │                │ workflow         │
                              │                └────────┬─────────┘
                              │                         │
                              │                ┌────────▼────────┐
                              │                │ cascade.py      │
                              │                │ updates deps   │
                              │                └────────┬────────┘
                              │                         │
                              └─────────────────────────┘
```

## Prerequisites

- Cloudflare account with a domain
- GitHub organization: `team-deepiri`
- GitHub App permissions to access the org

---

## Part 1: Create GitHub App

### Step 1.1: Create the App

1. Go to: **https://github.com/settings/apps/new**

2. Fill in the form:

| Field | Value |
|-------|-------|
| **App name** | `deepiri-cascade` |
| **Homepage URL** | `https://github.com/Team-Deepiri/deepiri-cascade` |
| **Description** | Cascade dependency updates across team-deepiri repos |
| **Webhook URL** | (We'll set this after deploying the worker) |
| **Webhook secret** | Generate a random secret (e.g., `openssl rand -hex 32`) |

3. Click **Create App**

### Step 1.2: Set Permissions

On the settings page, find **Permissions** section:

- **Repository contents**: Read
- **Metadata**: Read  
- **Pull requests**: Read and write
- **Repositories**: Select "All repositories" or choose specific ones

### Step 1.3: Subscribe to Events

Under **Subscribe to events**, check:
- [x] Push
- [x] Repository dispatch

### Step 1.4: Install the App

1. Click **Install** (left sidebar)
2. Select **All repositories** (or choose specific repos)
3. Click **Install**

### Step 1.5: Get Credentials

After installation, note these values:

| Value | Where to find |
|-------|---------------|
| **App ID** | App settings page (number, e.g., `1234567`) |
| **Private Key** | App settings → **Generate a private key** (downloads .pem file) |

---

## Part 2: Deploy Cloudflare Worker

### Step 2.1: Install Wrangler

```bash
npm install -g wrangler
```

### Step 2.2: Login to Cloudflare

```bash
wrangler login
# Opens browser - authenticate with your Cloudflare account
```

### Step 2.3: Configure the Worker

Edit `worker/wrangler.toml`:

```toml
name = "deepiri-cascade"
main = "worker/index.js"
compatibility_date = "2024-01-01"

[secrets]
GITHUB_APP_ID = "your_app_id_here"
GITHUB_APP_PRIVATE_KEY = "your_private_key_here"
```

Or use wrangler secrets (recommended):

```bash
cd worker

# Add the App ID
wrangler secret put GITHUB_APP_ID
# When prompted, enter your App ID (e.g., 1234567)

# Add the Private Key
wrangler secret put GITHUB_APP_PRIVATE_KEY
# When prompted, paste the ENTIRE contents of your .pem file
# Including the -----BEGIN PRIVATE KEY----- and -----END PRIVATE KEY----- lines
```

### Step 2.4: Deploy

```bash
wrangler deploy
```

You'll see output like:

```
⛅️  deepiri-cascade  Published
  https://deepiri-cascade.your-subdomain.workers.dev
```

### Step 2.5: Test the Worker

```bash
# Check it's running
curl https://deepiri-cascade.your-subdomain.workers.dev
# Should return: "deepiri-cascade worker running"

# View logs
wrangler tail
```

---

## Part 3: Configure GitHub App Webhook

Go back to your GitHub App settings:

1. **Webhook URL**: `https://deepiri-cascade.your-subdomain.workers.dev`
2. **Webhook secret**: The secret you generated in Step 1.1

Click **Update webhook**.

---

## Part 4: Verify the Setup

### Test Manual Trigger

You can trigger cascade manually:

```bash
# Replace with your worker URL and repo/tag
curl -X POST https://deepiri-cascade.your-subdomain.workers.dev \
  -H "Content-Type: application/json" \
  -d '{
    "action": "push",
    "ref": "refs/tags/v1.0.0",
    "repository": {"name": "deepiri-shared-utils"}
  }'
```

Or trigger via GitHub API:

```bash
curl -X POST https://api.github.com/repos/Team-Deepiri/deepiri-cascade/dispatches \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "cascade-trigger",
    "client_payload": {
      "repo": "deepiri-shared-utils",
      "tag": "v1.0.0"
    }
  }'
```

### Test with Actual Tag Push

```bash
# In any repo in team-deepiri
git tag v1.0.1
git push origin v1.0.1
```

Check:
1. **Worker logs**: `wrangler tail`
2. **GitHub Actions**: Go to `deepiri-cascade` repo → Actions

---

## How It Works

### Flow

1. You push a version tag (`v1.2.3`) to any repo in team-deepiri
2. GitHub sends webhook to the Cloudflare Worker
3. Worker validates it's a version tag
4. Worker gets GitHub App installation token
5. Worker calls GitHub API to trigger `repository_dispatch` on `deepiri-cascade`
6. The `cascade.yml` workflow runs in `deepiri-cascade`
7. Cascade tool discovers all dependent repos and updates them

### Package Managers Supported

| Manager | Files | What Gets Updated |
|---------|-------|-------------------|
| **npm** | `package.json` | Registry-published `dependencies`, `devDependencies` with `@deepiri/*` |
| **Poetry** | `pyproject.toml` | Git dependencies (`rev=`, `tag=`) for team-deepiri repos |
| **Git** | `.gitmodules` | Submodule URLs pointing to team-deepiri |

---

## Troubleshooting

### Worker Not Receiving Webhooks

1. Check worker logs: `wrangler tail`
2. Verify webhook URL in GitHub App settings
3. Check GitHub App is installed on the repo where you're pushing tags

### Cascade Not Triggering

1. Check GitHub Actions in `deepiri-cascade` repo
2. Verify the workflow is enabled
3. Check workflow run logs for errors

### Permission Errors

Ensure GitHub App has:
- Repository contents: Read
- Metadata: Read
- Pull requests: Read and write

### Worker JWT Errors

Make sure:
- Private key is correctly formatted (includes header/footer)
- App ID matches the one in GitHub App settings
- Private key hasn't expired (GitHub App private keys don't expire)

---

## Files Reference

```
deepiri-cascade/
├── worker/
│   ├── index.js           # Cloudflare Worker (webhook handler)
│   ├── wrangler.toml      # Worker configuration
│   └── README.md          # Quick reference
├── src/
│   └── deepiri_cascade/  # Python cascade tool
│       ├── cli.py         # CLI entrypoint
│       ├── discovery.py   # Find dependencies
│       ├── cascade.py     # Update repos
│       └── parser/        # npm, poetry, gitmodules
└── .github/
    └── workflows/
        ├── cascade.yml    # Main cascade workflow
        └── monitor.yml    # Fallback: scheduled tag checker
```
