export default {
  async fetch(request: Request, env: any, ctx: any): Promise<Response> {
    const url = new URL(request.url);

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
        },
      });
    }

    // API endpoint – return scraped data summary
    if (url.pathname === "/api/data") {
      const data = {
        message: "Gare Scraper API is running",
        status: "ok",
        // When KV is bound, replace this with KV reads of scraping_index.json
      };
      return new Response(JSON.stringify(data), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      });
    }

    // Auth config API – GET /api/auth
    if (url.pathname === "/api/auth" && request.method === "GET") {
      // Return stored auth config from KV (if bound) or empty
      const authConfig = env.AUTH_STORE
        ? await env.AUTH_STORE.get("grok_auth", "json")
        : { cookie: "", token: "" };
      return new Response(JSON.stringify(authConfig || { cookie: "", token: "" }), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      });
    }

    // Auth config API – POST /api/auth (save auth config)
    if (url.pathname === "/api/auth" && request.method === "POST") {
      try {
        const body = await request.json();
        const { cookie, token } = body;
        
        if (env.AUTH_STORE) {
          await env.AUTH_STORE.put("grok_auth", JSON.stringify({ cookie, token }));
        }
        
        return new Response(JSON.stringify({ success: true }), {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        });
      } catch (e) {
        return new Response(JSON.stringify({ error: e.message }), {
          status: 400,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        });
      }
    }

    // All other paths are served by the [assets] static site (workers-site/)
    // Pass through to the asset handler provided by Cloudflare Workers static assets
    return (env.ASSETS as Fetcher).fetch(request);
  },
};
