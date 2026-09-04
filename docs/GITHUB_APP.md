# Deepiri Cascade GitHub App

## Setup Instructions

### Step 1: Create the GitHub App

Go to: https://github.com/settings/apps/new

Fill in:

- **App name**: `deepiri-cascade`
- **Homepage URL**: `https://github.com/Team-Deepiri/deepiri-cascade`
- **Webhook URL**: You'll need to set this after deploying (see below)
- **Webhook secret**: Generate a random secret (save it!)

**Permissions needed:**
- Repository contents: Read
- Metadata: Read
- Pull requests: Read/Write
- Administration: Write *(required only for the admin-merge fallback, see below)*

**Events to subscribe to:**
- Push (specifically tags)
- Repository dispatch

### Step 2: Install the App

Install it on your organization with access to:
- All repositories (or select the ones you want)
- For the admin-merge fallback, the App must be installed on `deepiri-cascade` **and** granted
  admin access to every repo it may merge into (`Administration: write` on the org scope,
  or per-repo admin permissions).

### Step 3: Note the App ID and generate private key

After creating:
- Note the **App ID** (number)
- Generate and download **private key** (.pem file)
- Save the private key as a GitHub secret: `DEEPIRI_CASCADE_APP_PRIVATE_KEY`
- Save the App ID as: `DEEPIRI_CASCADE_APP_ID`

---

## Admin Merge Fallback

When GitHub auto-merge cannot be enabled for a cascade PR (for example, a repo
requires code review approvals), cascade can fall back to a **direct admin merge**
via the REST API. This is disabled by default and gated by two flags:

| Flag | Effects |
|------|---------|
| `--admin-merge` | Enables the fallback for all cascade PRs |
| `--allow-self-merge` | Additionally permits admin-merging `deepiri-cascade` itself, which merges to `main` and triggers a **production deploy** |

### Risk mitigations

Merging to `deepiri-cascade@main` automatically deploys the Cloudflare Worker to
production (`deploy.yml`). To prevent a buggy cascade run from silently shipping:

1. **Both flags disabled by default.** Nothing admin-merges unless explicitly opted in.
2. **Green-CI gate.** Before any admin merge, cascade polls the PR head's combined
   commit status and aborts unless `state == "success"`. Pending or failing checks
   mean the PR stays open.
3. **No merge on conflicts/drafts.** PRs whose `mergeable_state` is
   `conflict`, `dirty`, or `draft` are never admin-merged.
4. **Reliability-first logging.** A blocked merge (405), merge conflict (409), or
   missing admin token is logged and the PR is left open for a human — never
   silently merged, never fatal.

### Rolling back an accidental production deploy

The Worker can be reverted instantly:

```bash
npx wrangler rollback       # revert to the previous production deployment
```

Then close the offending PR/branch and re-run cascade once the fix lands.

### Passing the flags

- **Workflow dispatch**: `cascade.yml` accepts `admin-merge` and `allow-self-merge`
  boolean inputs.
- **Reusable workflow**: `reusable.yml` accepts the same inputs.
- **CLI**: `deepiri-cascade cascade --admin-merge --allow-self-merge --repo ...`
- **`repository_dispatch`**: include `"admin-merge": true` / `"allow-self-merge": true`
  in the `client_payload`.

---

## Architecture

```
Tag pushed → GitHub App webhook → Workflow dispatch → Cascade runs
```

The App receives the tag push event and triggers the cascade workflow via repository_dispatch.
