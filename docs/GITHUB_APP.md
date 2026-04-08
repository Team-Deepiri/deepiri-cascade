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

**Events to subscribe to:**
- Push (specifically tags)
- Repository dispatch

### Step 2: Install the App

Install it on your organization with access to:
- All repositories (or select the ones you want)

### Step 3: Note the App ID and generate private key

After creating:
- Note the **App ID** (number)
- Generate and download **private key** (.pem file)
- Save the private key as a GitHub secret: `DEEPIRI_CASCADE_APP_PRIVATE_KEY`
- Save the App ID as: `DEEPIRI_CASCADE_APP_ID`

---

## Architecture

```
Tag pushed → GitHub App webhook → Workflow dispatch → Cascade runs
```

The App receives the tag push event and triggers the cascade workflow via repository_dispatch.
