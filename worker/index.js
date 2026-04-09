/**
 * deepiri-cascade Cloudflare Worker
 */

const GITHUB_API = "https://api.github.com";
const ORG = "team-deepiri";
const TARGET_REPO = "deepiri-cascade";
const EVENT_TYPE = "cascade-trigger";

export default {
  async fetch(request, env) {
    if (request.method === "GET") {
      return new Response("deepiri-cascade worker running", { status: 200 });
    }

    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    try {
      const payload = await request.json();
      const eventType = request.headers.get("X-GitHub-Event");

      console.log("Event:", eventType, "Delivery:", request.headers.get("X-GitHub-Delivery"));

      if (eventType === "repository_dispatch") {
        console.log(
          "repository_dispatch (echo only; cascade runs in GitHub Actions on deepiri-cascade):",
          "action=",
          payload.action,
          "client_payload=",
          JSON.stringify(payload.client_payload || {})
        );
      }

      if (eventType === "create") {
        const { ref_type, ref, repository } = payload;
        const repo = repository?.name || "";

        console.log("Create event - ref_type:", ref_type, "ref:", ref, "repo:", repo);

        if (ref_type !== "tag") {
          return new Response(JSON.stringify({ skipped: "not a tag" }), { status: 200 });
        }

        if (!ref.match(/^v\d+\.\d+\.\d+/)) {
          return new Response(JSON.stringify({ skipped: "not a version tag (need vX.Y.Z)" }), { status: 200 });
        }

        console.log(`>>> Triggering cascade for ${repo} ${ref}`);
        try {
          const jwt = await createJWT(env.GITHUB_APP_ID, env.GITHUB_APP_PRIVATE_KEY);
          const installToken = await getInstallationToken(jwt);
          console.log("[cascade-preview] Scanning org repos for direct dependents (npm / poetry / gitmodules)...");
          const dependents = await fetchDependentsPreview(installToken, ORG, repo);
          console.log(
            `[cascade-preview] ${repo}@${ref} → ${dependents.length} dependent repo(s): ` +
              (dependents.length ? dependents.join(", ") : "(none — Action will also build graph; if this is empty, check npm scope @team-deepiri/ vs @deepiri/)")
          );
          await triggerCascadeDispatch(installToken, repo, ref);
          console.log(">>> Cascade triggered OK");
        } catch (err) {
          console.error(">>> Cascade trigger FAILED:", err.message);
          return new Response(JSON.stringify({ error: err.message }), { status: 500 });
        }

        return new Response(JSON.stringify({ success: true, repo, tag: ref }), { status: 200 });
      }

      return new Response(JSON.stringify({ received: true, event: eventType }), { status: 200 });

    } catch (error) {
      console.error("ERROR:", error.message, error.stack);
      return new Response(error.message, { status: 500 });
    }
  }
};

/**
 * Best-effort mirror of deepiri-cascade Discovery: list org repos that directly
 * depend on sourceRepo (for wrangler tail debugging). The GitHub Action still
 * builds the authoritative graph.
 */
async function fetchDependentsPreview(token, org, sourceRepo) {
  const headers = { ...GH_HEADERS, Authorization: `Bearer ${token}` };
  const repoNames = [];
  for (let page = 1; page <= 20; page++) {
    const res = await fetch(
      `${GITHUB_API}/orgs/${org}/repos?per_page=100&page=${page}&sort=updated`,
      { headers }
    );
    if (!res.ok) {
      console.log("[cascade-preview] list org repos failed:", res.status, await res.text());
      return [];
    }
    const batch = await res.json();
    if (!batch.length) break;
    repoNames.push(...batch.map((r) => r.name));
  }

  const scopedKey = `@${org}/${sourceRepo}`;
  const legacyKey = `@deepiri/${sourceRepo}`;
  const pyRe = new RegExp(
    `github\\.com/${org.replace(/-/g, "\\-")}/${sourceRepo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:\\.git)?`
  );
  const gmRe = new RegExp(
    `${org.replace(/-/g, "\\-")}/${sourceRepo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:\\.git)?`
  );

  async function fileText(repo, path) {
    const res = await fetch(`${GITHUB_API}/repos/${org}/${repo}/contents/${path}`, { headers });
    if (res.status !== 200) return null;
    const data = await res.json();
    if (typeof data.content !== "string" || data.encoding !== "base64") return null;
    return atob(data.content.replace(/\s/g, ""));
  }

  async function repoDepends(name) {
    if (name === sourceRepo) return null;

    const pkgRaw = await fileText(name, "package.json");
    if (pkgRaw) {
      try {
        const j = JSON.parse(pkgRaw);
        for (const section of ["dependencies", "devDependencies"]) {
          const o = j[section];
          if (!o) continue;
          if (scopedKey in o || legacyKey in o) return name;
        }
      } catch {
        /* ignore */
      }
    }

    const pyRaw = await fileText(name, "pyproject.toml");
    if (pyRaw && pyRe.test(pyRaw)) return name;

    const gmRaw = await fileText(name, ".gitmodules");
    if (gmRaw && gmRe.test(gmRaw)) return name;

    return null;
  }

  const out = new Set();
  const batchSize = 8;
  for (let i = 0; i < repoNames.length; i += batchSize) {
    const slice = repoNames.slice(i, i + batchSize);
    const hits = await Promise.all(slice.map((n) => repoDepends(n)));
    for (const h of hits) {
      if (h) out.add(h);
    }
  }
  return Array.from(out).sort();
}

async function triggerCascadeDispatch(installToken, repo, tag) {
  console.log("Calling GitHub API to trigger dispatch...");
  const response = await fetch(`${GITHUB_API}/repos/${ORG}/${TARGET_REPO}/dispatches`, {
    method: "POST",
    headers: {
      ...GH_HEADERS,
      "Authorization": `Bearer ${installToken}`,
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

async function createJWT(appId, privateKeyPem) {
  if (!appId) throw new Error("Missing GITHUB_APP_ID");
  if (!privateKeyPem) throw new Error("Missing GITHUB_APP_PRIVATE_KEY");

  const now = Math.floor(Date.now() / 1000);
  const header = base64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const payload = base64url(JSON.stringify({ iss: parseInt(appId), iat: now - 60, exp: now + 540 }));
  const message = `${header}.${payload}`;

  return signWithRSA(message, privateKeyPem);
}

function base64url(str) {
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function signWithRSA(message, privateKeyPem) {
  const pemBody = privateKeyPem
    .replace(/-----BEGIN RSA PRIVATE KEY-----|-----BEGIN PRIVATE KEY-----/g, "")
    .replace(/-----END RSA PRIVATE KEY-----|-----END PRIVATE KEY-----/g, "")
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

  return `${message}.${base64url(String.fromCharCode(...new Uint8Array(signature)))}`;
}

const GH_HEADERS = {
  "Accept": "application/vnd.github+json",
  "User-Agent": "deepiri-cascade-worker/1.0",
};

async function getInstallationToken(jwt) {
  const response = await fetch(`${GITHUB_API}/app/installations`, {
    headers: { ...GH_HEADERS, "Authorization": `Bearer ${jwt}` }
  });

  if (!response.ok) {
    throw new Error(`Get installations failed: ${response.status} ${await response.text()}`);
  }

  const installations = await response.json();

  if (!installations || installations.length === 0) {
    throw new Error("No installations found - is the App installed on the org?");
  }

  const tokenResponse = await fetch(`${GITHUB_API}/app/installations/${installations[0].id}/access_tokens`, {
    method: "POST",
    headers: { ...GH_HEADERS, "Authorization": `Bearer ${jwt}` },
    body: JSON.stringify({})
  });

  if (!tokenResponse.ok) {
    throw new Error(`Get token failed: ${tokenResponse.status} ${await tokenResponse.text()}`);
  }

  return (await tokenResponse.json()).token;
}
