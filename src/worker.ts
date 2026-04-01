export default {
  async fetch(request: Request, env: any, ctx: any): Promise<Response> {
    const url = new URL(request.url);
    // API endpoint to serve scraped data (placeholder)
    if (url.pathname === "/api/data") {
      const data = {
        message: "Hello from Cloudflare Worker",
        // TODO: integrate with KV to serve actual scraping_index.json data
      };
      return new Response(JSON.stringify(data), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      });
    }
    // Serve a simple HTML page for root path
    if (url.pathname === "/") {
      const html = `
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1.0" />
          <title>Gare Scraper</title>
        </head>
        <body>
          <h1>Gare Scraper Interface</h1>
          <p>Use the <code>/api/data</code> endpoint to fetch scraped data.</p>
        </body>
        </html>
      `;
      return new Response(html, {
        status: 200,
        headers: {
          "Content-Type": "text/html",
        },
      });
    }
    return new Response("Not Found", { status: 404 });
  },
};