# Deepiri Cascade

Cascade version updates across Deepiri organization repositories.

## Features

- **Event-Driven**: Real-time updates when tags are pushed (via GitHub App)
- **Multi-Format Support**: Handles npm (package.json), Poetry (pyproject.toml), and git submodules
- **Wave-Based Updates**: Topological sort ensures correct update order
- **Dry-Run Mode**: Preview changes without making updates
- **Zero Config**: Works with any repo in the org once GitHub App is installed

## Architecture

```
Tag pushed → GitHub App webhook → cascade.yml workflow → Updates all dependents
```

## Quick Start

### Step 1: Install GitHub App

1. Go to **GitHub App settings** and create a new app named `deepiri-cascade`
2. Set permissions:
   - Repository contents: Read
   - Metadata: Read
   - Pull requests: Read/Write
3. Subscribe to events: **Push** and **Repository dispatch**
4. Install on your organization (all repos or selected)

### Step 2: Configure Secrets

Add these secrets to the `deepiri-cascade` repo:

- `DEEPIRI_CASCADE_APP_ID`: Your GitHub App ID (number)
- `DEEPIRI_CASCADE_APP_PRIVATE_KEY`: Private key (.pem file contents)

### Step 3: Push a Tag

```bash
git tag v1.2.3
git push origin v1.2.3
```

The GitHub App detects the tag and triggers the cascade workflow, which updates all dependent repos.

## Manual Trigger

You can also trigger cascades manually via GitHub Actions:

```yaml
on:
  workflow_dispatch:
    inputs:
      repo:
        required: true
      tag:
        required: true
```

Run with:
```bash
deepiri-cascade cascade --repo deepiri-shared-utils --tag v1.2.3
```

## CLI Usage

```bash
# With explicit repo and tag
deepiri-cascade cascade --repo deepiri-shared-utils --tag v1.2.3

# Dry-run mode
deepiri-cascade cascade --repo deepiri-shared-utils --tag v1.2.3 --dry-run

# Custom bump type
deepiri-cascade cascade --repo deepiri-shared-utils --tag v2.0.0 --bump-type minor
```

## Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--repo` | Repository name | auto-detected |
| `--tag` | Version tag | auto-detected |
| `--org` | GitHub organization | team-deepiri |
| `--bump-type` | Version bump type | patch |
| `--dry-run` | Preview only | false |
| `--no-confirm` | Skip confirmation | false |

## Supported Package Managers

- **npm**: Updates `dependencies` and `devDependencies` in package.json
- **Poetry**: Updates git dependencies with `rev=` or `tag=` in pyproject.toml
- **Git Submodules**: Updates submodule URLs in .gitmodules
