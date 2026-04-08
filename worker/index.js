/**
 * deepiri-cascade Cloudflare Worker
 * 
 * Receives GitHub App webhooks for tag pushes and triggers cascade workflow.
 * 
 * Setup:
 * 1. Deploy this worker to Cloudflare Workers
 * 2. Set secrets: GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY
 * 3. Set webhook URL in GitHub App to: https://your-worker.your-subdomain.workers.dev
 */

const GITHUB_API = "https://api.github.com";
const ORG = "team-deepiri";
const TARGET_REPO = "deepiri-cascade";
const EVENT_TYPE = "cascade-trigger";

export default {
  async fetch(request, env, ctx) {
    if (request.method === "GET") {
      return new Response("deepiri-cascade worker running", { status: 200 });
    }

    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    try {
      const payload = await request.json();
      const eventType = request.headers.get("X-GitHub-Event");

      console.log("Received event:", eventType);

      // Only handle tag push events
      if (eventType === "push") {
        const result = handleTagPush(payload);
        
        if (result.shouldCascade) {
          console.log(`Triggering cascade for ${result.repo} ${result.tag}`);
          
          // Get installation token and trigger workflow
          await triggerCascade(env, result.repo, result.tag);
          
          return new Response(JSON.stringify({
            success: true,
            cascade: result
          }), { status: 200 });
        } else {
          console.log("Skipped:", result.reason);
        }
      }

      return new Response(JSON.stringify({ 
        received: true, 
        event: eventType 
      }), { status: 200 });

    } catch (error) {
      console.error("Error:", error.message);
      return new Response(error.message, { status: 500 });
    }
  }
};

function handleTagPush(payload) {
  const ref = payload.ref || "";
  const repo = payload.repository?.name || "";
  
  // Check if this is a tag
  if (!ref.startsWith("refs/tags/")) {
    return { shouldCascade: false, reason: "not a tag" };
  }

  const tag = ref.replace("refs/tags/", "");
  
  // Only process version tags (v*.*.*)
  if (!tag.match(/^v\d+\.\d+\.\d+/)) {
    return { shouldCascade: false, reason: "not a version tag" };
  }

  return {
    shouldCascade: true,
    repo: repo,
    tag: tag
  };
}

async function triggerCascade(env, repo, tag) {
  // Create JWT for GitHub App
  const jwt = createJWT(env.GITHUB_APP_ID, env.GITHUB_APP_PRIVATE_KEY);
  
  // Get installation token
  const installToken = await getInstallationToken(jwt);
  
  // Trigger repository dispatch
  const response = await fetch(`${GITHUB_API}/repos/${ORG}/${TARGET_REPO}/dispatches`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${installToken}`,
      "Accept": "application/vnd.github+json",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      event_type: EVENT_TYPE,
      client_payload: {
        repo: repo,
        tag: tag,
        action: "cascade"
      }
    })
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Failed to trigger cascade: ${response.status} - ${error}`);
  }

  console.log("Cascade triggered successfully");
}

function createJWT(appId, privateKey) {
  const header = btoa(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const payload = btoa(JSON.stringify({
    iss: appId,
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 600
  }));

  // Use Web Crypto API to sign
  const cryptoKey = await crypto.subtle.importKey(
    "pkcs8",
    base64ToArrayBuffer(privateKey),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    cryptoKey,
    new TextEncoder().encode(`${header}.${payload}`)
  );

  return `${header}.${payload}.${btoa(String.fromCharCode(...new Uint8Array(signature)))}`;
}

function base64ToArrayBuffer(base64) {
  const binary = atob(base64.replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\s/g, ""));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

async function getInstallationToken(jwt) {
  // Get installations
  const response = await fetch(`${GITHUB_API}/app/installations`, {
    headers: {
      "Authorization": `Bearer ${jwt}`,
      "Accept": "application/vnd.github+json"
    }
  });

  const installations = await response.json();
  if (!installations || installations.length === 0) {
    throw new Error("No installations found");
  }

  // Get access token for first installation
  const installId = installations[0].id;
  const tokenResponse = await fetch(`${GITHUB_API}/app/installations/${installId}/access_tokens`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${jwt}`,
      "Accept": "application/vnd.github+json"
    },
    body: JSON.stringify({})
  });

  const tokenData = await tokenResponse.json();
  return tokenData.token;
}