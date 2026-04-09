/**
 * deepiri-cascade Cloudflare Worker
 */

const GITHUB_API = "https://api.github.com";
const ORG = "team-deepiri";
const TARGET_REPO = "deepiri-cascade";
const EVENT_TYPE = "cascade-trigger";

export default {
  async fetch(request, env) {
    console.log("=== Webhook received ===");
    console.log("Method:", request.method);
    console.log("URL:", request.url);

    if (request.method === "GET") {
      return new Response("deepiri-cascade worker running", { status: 200 });
    }

    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    try {
      const payload = await request.json();
      const eventType = request.headers.get("X-GitHub-Event");
      const delivery = request.headers.get("X-GitHub-Delivery");

      console.log("Event:", eventType);
      console.log("Delivery:", delivery);
      console.log("Payload keys:", Object.keys(payload));

      if (eventType === "push") {
        console.log("Push event - ref:", payload.ref);
        console.log("Push event - repo:", payload.repository?.name);
        
        const result = handleTagPush(payload);
        console.log("Result:", JSON.stringify(result));
        
        if (result.shouldCascade) {
          console.log(`>>> Triggering cascade for ${result.repo} ${result.tag}`);
          
          try {
            await triggerCascade(env, result.repo, result.tag);
            console.log(">>> Cascade triggered OK");
          } catch (err) {
            console.error(">>> Cascade trigger FAILED:", err.message);
          }
          
          return new Response(JSON.stringify({ success: true, cascade: result }), { status: 200 });
        } else {
          console.log(">>> Skipped:", result.reason);
          return new Response(JSON.stringify({ skipped: result.reason }), { status: 200 });
        }
      }

      return new Response(JSON.stringify({ received: true, event: eventType }), { status: 200 });

    } catch (error) {
      console.error("ERROR:", error.message);
      console.error(error.stack);
      return new Response(error.message, { status: 500 });
    }
  }
};

function handleTagPush(payload) {
  const ref = payload.ref || "";
  const repo = payload.repository?.name || "";
  
  console.log("Checking ref:", ref);
  
  if (!ref.startsWith("refs/tags/")) {
    return { shouldCascade: false, reason: "not a tag ref" };
  }

  const tag = ref.replace("refs/tags/", "");
  console.log("Tag:", tag);
  
  if (!tag.match(/^v\d+\.\d+\.\d+/)) {
    return { shouldCascade: false, reason: "not a version tag (need vX.Y.Z)" };
  }

  return { shouldCascade: true, repo: repo, tag: tag };
}

async function triggerCascade(env, repo, tag) {
  console.log("Creating JWT...");
  const jwt = createJWT(env.GITHUB_APP_ID, env.GITHUB_APP_PRIVATE_KEY);
  
  console.log("Getting installation token...");
  const installToken = await getInstallationToken(jwt);
  
  console.log("Calling GitHub API to trigger dispatch...");
  const response = await fetch(`${GITHUB_API}/repos/${ORG}/${TARGET_REPO}/dispatches`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${installToken}`,
      "Accept": "application/vnd.github+json",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      event_type: EVENT_TYPE,
      client_payload: { repo, tag, action: "cascade" }
    })
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`API error ${response.status}: ${error}`);
  }

  console.log("Dispatch triggered!");
}

function createJWT(appId, privateKeyPem) {
  if (!appId) throw new Error("Missing GITHUB_APP_ID");
  if (!privateKeyPem) throw new Error("Missing GITHUB_APP_PRIVATE_KEY");

  const now = Math.floor(Date.now() / 1000);
  const header = btoa(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const payload = btoa(JSON.stringify({ iss: parseInt(appId), iat: now, exp: now + 600 }));
  const message = `${header}.${payload}`;

  return signWithRSA(message, privateKeyPem);
}

function btoa(str) {
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function signWithRSA(message, privateKeyPem) {
  const pemBody = privateKeyPem
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/[\r\n\s]/g, "");

  const binaryKey = atob(pemBody);
  const keyBytes = new Uint8Array(binaryKey.length);
  for (let i = 0; i < binaryKey.length; i++) {
    keyBytes[i] = binaryKey.charCodeAt(i);
  }

  const cryptoKey = await crypto.subtle.importKey(
    "pkcs8", keyBytes.buffer,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false, ["sign"]
  );

  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5", cryptoKey, new TextEncoder().encode(message)
  );

  return `${message}.${btoa(String.fromCharCode(...new Uint8Array(signature)))}`;
}

async function getInstallationToken(jwt) {
  const response = await fetch(`${GITHUB_API}/app/installations`, {
    headers: { "Authorization": `Bearer ${jwt}`, "Accept": "application/vnd.github+json" }
  });

  if (!response.ok) {
    throw new Error(`Get installations failed: ${response.status}`);
  }

  const installations = await response.json();
  console.log("Installations:", JSON.stringify(installations));
  
  if (!installations || installations.length === 0) {
    throw new Error("No installations found - is the App installed on the org?");
  }

  const tokenResponse = await fetch(`${GITHUB_API}/app/installations/${installations[0].id}/access_tokens`, {
    method: "POST",
    headers: { "Authorization": `Bearer ${jwt}`, "Accept": "application/vnd.github+json" },
    body: JSON.stringify({})
  });

  if (!tokenResponse.ok) {
    throw new Error(`Get token failed: ${tokenResponse.status}`);
  }

  return (await tokenResponse.json()).token;
}
