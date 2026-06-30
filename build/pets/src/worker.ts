// dinomyte.xyz Worker — single origin for the site, the pet assets, and the
// (future) OpenSea agent tool. See ../wrangler.toml and ../HOSTING.md.

import { SLUG, handleWellKnown, handleInvoke } from "./tool";

interface R2Object {
  body: ReadableStream;
  httpEtag: string;
  writeHttpMetadata(headers: Headers): void;
}
interface RateLimiter { limit(o: { key: string }): Promise<{ success: boolean }> }
interface Env {
  ASSETS: { fetch(req: Request): Promise<Response> };
  PETS: { get(key: string): Promise<R2Object | null> };
  RATE_LIMITER?: RateLimiter;
  TOOL_ID?: string;
  ETH_RPC_URL?: string;
}
interface Ctx { waitUntil(p: Promise<unknown>): void }

const IMMUTABLE = "public, max-age=31536000, immutable";
const MIME: Record<string, string> = {
  webp: "image/webp", json: "application/json", zip: "application/zip",
  png: "image/png", gif: "image/gif",
};

export default {
  async fetch(req: Request, env: Env, ctx: Ctx): Promise<Response> {
    const url = new URL(req.url);

    // canonicalize: www.dinomyte.xyz -> dinomyte.xyz (301, preserve path + query)
    if (url.hostname === "www.dinomyte.xyz") {
      url.hostname = "dinomyte.xyz";
      return Response.redirect(url.toString(), 301);
    }

    const path = url.pathname;

    // 1) pet assets — served from the edge cache; R2 is read at most ONCE per file
    //    per colo, then cached (immutable). This keeps R2 Class B ops near zero
    //    regardless of traffic (egress is free on R2).  e.g. /pets/tiny-dino-33/spritesheet.webp
    if (path.startsWith("/pets/")) {
      const cache = (globalThis as { caches: { default: Cache } }).caches.default;
      const hit = await cache.match(req);
      if (hit) return hit;

      // Cache miss = the only path that hits R2. Rate-limit it per IP so a scripted
      // miss-storm can't run up ops; cached/normal browsing above is never throttled.
      if (env.RATE_LIMITER) {
        const ip = req.headers.get("cf-connecting-ip") ?? "anon";
        const { success } = await env.RATE_LIMITER.limit({ key: ip });
        if (!success) {
          return new Response("slow down", {
            status: 429, headers: { "retry-after": "10" },
          });
        }
      }

      const key = decodeURIComponent(path.slice(1)); // drop leading "/"
      const obj = await env.PETS.get(key);
      if (!obj) return new Response("not found", { status: 404 });
      const headers = new Headers();
      obj.writeHttpMetadata(headers); // content-type if R2 stored one at upload
      if (!headers.has("content-type")) {
        const ext = key.split(".").pop() ?? "";
        headers.set("content-type", MIME[ext] ?? "application/octet-stream");
      }
      headers.set("etag", obj.httpEtag);
      headers.set("cache-control", IMMUTABLE);
      headers.set("access-control-allow-origin", "*");
      const res = new Response(obj.body, { headers });
      if (req.method === "GET") ctx.waitUntil(cache.put(req, res.clone()));
      return res;
    }

    // 2) OpenSea agent tool (ERC-8257), built on @opensea/tool-sdk (see ./tool.ts)
    //    - GET /.well-known/ai-tool/<slug>.json : the tool manifest
    //    - POST /api/pet : registry-gated invocation (ETH dinos ownership)
    if (path === `/.well-known/ai-tool/${SLUG}.json`) {
      return handleWellKnown(req);
    }
    if (path === "/api/pet" && req.method === "POST") {
      return handleInvoke(req, env, ctx);
    }

    // 3) everything else (index.html, /.well-known/ai-tool/*, etc.) -> static assets
    return env.ASSETS.fetch(req);
  },
};
