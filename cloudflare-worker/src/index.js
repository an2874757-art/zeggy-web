export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const targetUrl = url.searchParams.get("url");

    if (!targetUrl) {
      return new Response("Missing 'url' parameter", { status: 400 });
    }

    let target;
    try {
      target = new URL(targetUrl);
    } catch {
      return new Response("Invalid URL", { status: 400 });
    }

    const allowedHosts = [
      "cloud01.albox.co", "cloud02.albox.co", "cloud03.albox.co", "cloud04.albox.co",
      "cloud05.albox.co", "cloud06.albox.co", "cloud07.albox.co", "cloud08.albox.co",
      "cdn01.albox.co", "cdn02.albox.co", "cdn03.albox.co", "cdn04.albox.co",
      "cdn05.albox.co", "cdn06.albox.co", "cdn07.albox.co", "cdn08.albox.co",
      "cdn6.albox.co", "cdn7.albox.co", "cdn8.albox.co", "cdn9.albox.co", "cdn10.albox.co",
    ];

    if (!allowedHosts.includes(target.hostname)) {
      return new Response("Host not allowed", { status: 403 });
    }

    const headers = new Headers({
      "Referer": "https://an2874757-art.github.io/",
      "Origin": "https://an2874757-art.github.io",
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    };

    try {
      const response = await fetch(targetUrl, {
        method: "GET",
        headers,
        cf: { cacheTtl: 86400, cacheEverything: true },
      });

      if (!response.ok) {
        return new Response("Failed to fetch image", { status: response.status });
      }

      const responseHeaders = new Headers(response.headers);
      responseHeaders.set("Access-Control-Allow-Origin", "*");
      responseHeaders.set("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS");
      responseHeaders.set("Cache-Control", "public, max-age=86400, immutable");
      responseHeaders.delete("Content-Security-Policy");
      responseHeaders.delete("X-Frame-Options");

      return new Response(response.body, { status: 200, headers: responseHeaders });
    } catch (error) {
      return new Response("Proxy error", { status: 502 });
    }
  },
};