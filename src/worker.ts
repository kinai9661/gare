export default {
  async fetch(request: Request, env: any, ctx: any): Promise<Response> {
    const url = new URL(request.url);

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

    // All other paths are served by the [assets] static site (workers-site/)
    // Pass through to the asset handler provided by Cloudflare Workers static assets
    return (env.ASSETS as Fetcher).fetch(request);
  },
};
