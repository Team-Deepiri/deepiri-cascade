# Deepiri Cascade

Automated dependency cascading across team-deepiri repositories.

## Features

- **Tag releases**: semver `vX.Y.Z` tags cascade to Poetry/npm/submodule consumers
- **Default-branch pushes**: merges to `main` cascade submodule pointer bumps (e.g. `deepiri-auth-service` → `deepiri-platform`)
- **Multi-Format**: npm, Poetry, and git submodules
- **Wave-Based**: Topological sort ensures correct update order
- **Zero Config**: No workflow files needed in dependent repos
- **Cloudflare-Hosted**: Webhook relay + scheduled monitors as fallback

## Triggers

| Event | Example | Consumer update |
|-------|---------|-----------------|
| Tag `v1.2.3` pushed | `deepiri-gpu-utils` release | `pyproject.toml` / npm git spec → tag |
| Push to default branch | `deepiri-auth-service` merge to `main` | `.gitmodules` submodule → commit SHA |

Discovery scans each repo's **default branch** (`main`) for `pyproject.toml`, `package.json`, and `.gitmodules` anywhere in the tree. Submodule contents are not scanned — only the parent's `.gitmodules` edges (e.g. `platform-services/backend/deepiri-auth-service` → `deepiri-auth-service`).

Fallback monitors (every 5 min): `monitor.yml` (tags), `monitor-push.yml` (default-branch HEAD).

## CodeQL Security Scanning

This repository includes GitHub CodeQL analysis for both Python and JavaScript/TypeScript code.

- Workflow file: `.github/workflows/codeql.yml`
- Config file: `.github/codeql/codeql-config.yml`
- Triggers: `push` and `pull_request` on `main` and `dev`
- Languages scanned: `python`, `javascript-typescript`

### Workflow

```yaml
name: CodeQL

on:
	pull_request:
		branches: [main, dev]
	push:
		branches: [main, dev]

permissions:
	actions: read
	contents: read
	security-events: write

jobs:
	analyze:
		name: Analyze (${{ matrix.language }})
		runs-on: ubuntu-latest
		strategy:
			fail-fast: false
			matrix:
				language: [python, javascript-typescript]

		steps:
			- name: Checkout repository
				uses: actions/checkout@v4
				with:
					fetch-depth: 0

			- name: Initialize CodeQL
				uses: github/codeql-action/init@v3
				with:
					languages: ${{ matrix.language }}
					config-file: ./.github/codeql/codeql-config.yml

			- name: Perform CodeQL Analysis
				uses: github/codeql-action/analyze@v3
```

### CodeQL Config

```yaml
# Exclude generated/build/runtime artifact paths.
paths-ignore:
	- '**/node_modules/**'
	- '**/dist/**'
	- '**/build/**'
	- '**/coverage/**'
	- '**/logs/**'
	- '**/*.min.js'
	- '**/__pycache__/**'
	- '**/*.egg-info/**'
```

This keeps analysis focused on source code under `src/` and `worker/` while excluding generated and runtime artifacts.

## Quick Setup

### 1. Create GitHub App

1. Go to https://github.com/settings/apps/new
2. Create app named `deepiri-cascade`
3. Set permissions: Contents (Read), Metadata (Read), Pull Requests (Read/Write)
4. Subscribe to events: **Push**, **Create a tag**, Repository dispatch
5. Install on your organization
6. Get **App ID** and generate **Private Key** (.pem)

### 2. Deploy Cloudflare Worker

```bash
cd worker
wrangler login
wrangler secret put GITHUB_APP_ID
wrangler secret put GITHUB_APP_PRIVATE_KEY
wrangler deploy
```

### 3. Configure Webhook

Set GitHub App webhook URL to your worker URL.

### 4. Push a Tag

```bash
git tag v1.0.0
git push origin v1.0.0
```

The cascade runs automatically!

### 5. GitHub Actions secrets (`Team-Deepiri/deepiri-cascade`)

See **[docs/SECRETS.md](docs/SECRETS.md)** for the full setup checklist.

| Secret | Used by | Purpose |
|--------|---------|---------|
| `APP_ID` | `cascade.yml` | GitHub App ID for PR creation |
| `APP_PRIVATE_KEY` | `cascade.yml` | GitHub App PEM (full file contents) |
| `CLOUDFLARE_API_TOKEN` | `deploy.yml` | Auto-deploy worker on merge to `main` |
| `CLOUDFLARE_ACCOUNT_ID` | `deploy.yml` | Cloudflare account for Wrangler |

`GITHUB_TOKEN` is provided automatically for monitor workflows.

### 6. Cloudflare Worker secrets

| Secret | Purpose |
|--------|---------|
| `GITHUB_APP_ID` | Same App ID as above |
| `GITHUB_APP_PRIVATE_KEY` | Same PEM as `APP_PRIVATE_KEY` |

After merging to `main`, `deploy.yml` publishes the worker automatically when `worker/` changes.

## Full Setup Guide

See [SETUP.md](SETUP.md) for detailed instructions.

## Usage

### Manual trigger (tag)

```bash
deepiri-cascade cascade --repo deepiri-shared-utils --tag v1.2.3
```

### Manual trigger (push / submodule)

```bash
deepiri-cascade cascade --repo deepiri-auth-service --sha abc123... --trigger push
```

### Dry Run

```bash
deepiri-cascade cascade --repo deepiri-shared-utils --tag v1.2.3 --dry-run
```

## Supported Package Managers

| Manager | File | Updates |
|---------|------|---------|
| npm | `package.json` | Registry-published `@deepiri/*` dependencies |
| Poetry | `pyproject.toml` | Git deps to team-deepiri |
| Git | `.gitmodules` | team-deepiri submodules |

## Architecture

```
Tag push ──┐
           ├──► Cloudflare Worker / monitor ──► cascade.yml ──► dependent PRs
Main push ─┘
```
