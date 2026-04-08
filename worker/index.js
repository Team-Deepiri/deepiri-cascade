export default {
  async fetch(request, env) {
    if (request.method === "GET") {
      return new Response("deepiri-cascade worker running");
    }

    if (request.method === "POST") {
      const body = await request.json();
      console.log("Webhook received:", body);

      if (body.ref?.startsWith("refs/tags/")) {
        const tag = body.ref.replace("refs/tags/", "");
        const repo = body.repository?.name;
        console.log(`Tag detected: ${repo}@${tag}`);
      }

      return new Response("ok");
    }

    return new Response("Not allowed", { status: 405 });
  },
};
