# Deepiri Cascade

Automated dependency cascading across team-deepiri repositories.

## Features

- **Event-Driven**: Real-time updates when tags are pushed
- **Multi-Format**: Poetry Git dependencies and git submodules
- **Wave-Based**: Topological sort ensures correct update order
- **Zero Config**: No workflow files needed in dependent repos
- **Cloudflare-Hosted**: Free webhook handling

## Quick Setup

### 1. Create GitHub App

1. Go to https://github.com/settings/apps/new
2. Create app named `deepiri-cascade`
3. Set permissions: Contents (Read), Metadata (Read), Pull Requests (Read/Write)
4. Subscribe to events: Push, Repository dispatch
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

## Full Setup Guide

See [SETUP.md](SETUP.md) for detailed instructions.

## Usage

### Manual Trigger

```bash
deepiri-cascade cascade --repo deepiri-shared-utils --tag v1.2.3
```

### Dry Run

```bash
deepiri-cascade cascade --repo deepiri-shared-utils --tag v1.2.3 --dry-run
```

## Supported Package Managers

| Manager | File | Updates |
|---------|------|---------|
| Poetry | `pyproject.toml` | Git deps to team-deepiri |
| Git | `.gitmodules` | team-deepiri submodules |

## Architecture

```
Tag push → GitHub App webhook → Cloudflare Worker → GitHub API → cascade.yml
```
