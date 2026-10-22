/**
 * ZEEGY BOX — خادم Deno Deploy (خدمة واحدة: تطبيق ثابت + بروكسي API) ✓
 * - /api/*  → يُمرَّر إلى المصدر ويُعاد مع ترويسات CORS مفتوحة (سفاري/آيفون ✓)
 * - البقية  → ملفات ثابتة مع SPA fallback إلى index.html
 */
// @ts-nocheck
import { serveDir } from "https://deno.land/std@0.224.0/http/file_server.ts";

const UPSTREAM = "https://cinema.albox.co";
const PUBLIC_DIR = new URL("./public/", import.meta.url);
const INDEX_HTML = new URL("./public/index.html", import.meta.url);

const corsBase: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,PATCH,HEAD,OPTIONS",
  "Access-Control-Allow-Credentials": "true",
  "Access-Control-Max-Age": "86400",
};

function json(msg: unknown, status = 200): Response {
  return new Response(JSON.stringify(msg), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...corsBase },
  });
}

Deno.serve(async (req: Request) => {
  const u = new URL(req.url);

  /* ---- CORS preflight ---- */
  if (req.method === "OPTIONS") {
    const h = new Headers(corsBase);
    const reqH = req.headers.get("Access-Control-Request-Headers");
    h.set("Access-Control-Allow-Headers", reqH ?? "Content-Type,Authorization,App-Version,Device-Store,Accept-Language,User-Agent");
    return new Response(null, { status: 204, headers: h });
  }

  /* ---- بروكسي API ---- */
  if (u.pathname === "/api" || u.pathname.startsWith("/api/")) {
    // نمرر المسار كما هو بعد /api  (المتصفح يطلب /api/v4/... فسيصبح upstream /api/v4/...)
    const pass = UPSTREAM + u.pathname + u.search;

    const headers = new Headers();
    for (const [k, v] of req.headers) {
      const kk = k.toLowerCase();
      if (["host", "connection", "cookie", "referer", "origin", "accept-encoding", "content-length"].includes(kk)) continue;
      headers.set(k, v);
    }
    // UA افتراضي ملائم إن غاب
    if (!headers.get("user-agent")) {
      headers.set("User-Agent", "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/122 Mobile Safari/537.36");
    }

    let body: BodyInit | undefined;
    if (!["GET", "HEAD"].includes(req.method)) {
      body = await req.arrayBuffer();
    }

    let res: Response;
    try {
      res = await fetch(pass, {
        method: req.method,
        headers,
        body,
        redirect: "follow",
      });
    } catch (_e) {
      return json({ error: "proxy_unreachable" }, 502);
    }

    const out = new Headers(res.headers);
    out.delete("content-encoding"); // Deno يفك الضغط تلقائياً — حذف الترويسة لتبقى متسقة
    out.delete("content-length");
    out.delete("transfer-encoding");
    for (const [k, v] of Object.entries(corsBase)) out.set(k, v);
    const reqH = req.headers.get("Access-Control-Request-Headers");
    out.set("Access-Control-Allow-Headers", reqH ?? "Content-Type,Authorization,App-Version,Device-Store,Accept-Language,User-Agent");
    out.set("Cache-Control", "no-store");
    return new Response(res.body, { status: res.status, headers: out });
  }

  /* ---- صحة الخدمة ---- */
  if (u.pathname === "/healthz") {
    return json({ ok: true, service: "zeggy-web" });
  }

  /* ---- تطبيق ثابت + SPA fallback ---- */
  const resp = await serveDir(req, { fsPath: decodeURIComponent(PUBLIC_DIR.pathname), showIndex: true });
  if (resp.status === 404) {
    try {
      const html = await Deno.readTextFile(INDEX_HTML);
      return new Response(html, {
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "no-store",
          ...corsBase,
        },
      });
    } catch (_e) {
      return resp;
    }
  }
  return resp;
});
