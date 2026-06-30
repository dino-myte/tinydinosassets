// dinomyte.xyz Worker — single origin for the site, the pet assets, and the
// (future) OpenSea agent tool. See ../wrangler.toml and ../HOSTING.md.

interface R2Object {
  body: ReadableStream;
  httpEtag: string;
  writeHttpMetadata(headers: Headers): void;
}
interface Env {
  ASSETS: { fetch(req: Request): Promise<Response> };
  PETS: { get(key: string): Promise<R2Object | null> };
}

const IMMUTABLE = "public, max-age=31536000, immutable";

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const path = url.pathname;

    // 1) pet assets — stream from the private R2 bucket
    //    e.g. /pets/tiny-dino-33/spritesheet.webp
    if (path.startsWith("/pets/")) {
      const key = decodeURIComponent(path.slice(1)); // drop leading "/"
      const obj = await env.PETS.get(key);
      if (!obj) return new Response("not found", { status: 404 });
      const headers = new Headers();
      obj.writeHttpMetadata(headers); // content-type set at upload time
      headers.set("etag", obj.httpEtag);
      headers.set("cache-control", IMMUTABLE);
      headers.set("access-control-allow-origin", "*");
      return new Response(obj.body, { headers });
    }

    // 2) OpenSea agent tool endpoint (ERC-8257) — wired up in agent-tool/.
    //    Stubbed until the tool is registered (needs the gated handler + toolId).
    if (path === "/api/pet" && req.method === "POST") {
      return Response.json(
        { error: "not_implemented", hint: "agent tool not registered yet" },
        { status: 501 },
      );
    }

    // 3) everything else (index.html, /.well-known/ai-tool/*, etc.) -> static assets
    return env.ASSETS.fetch(req);
  },
};
