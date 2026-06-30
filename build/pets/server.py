"""tiny dinos -> Hermes pet generator.

A tiny dependency-free HTTP service that renders a dino's pet sprite sheet ON DEMAND
(no need to host the 2.5GB pre-rendered pack) and serves an installable petdex pack.

  python build/pets/server.py            # http://localhost:8017
  PORT=9000 python build/pets/server.py

Routes:
  GET /                              the lookup site (enter a token #)
  GET /api/pet/<id>/pet.json         petdex metadata
  GET /api/pet/<id>/spritesheet.webp petdex sheet (lossy webp, 1536x1872)
  GET /api/pet/<id>/spritesheet_game.webp  + game-only rows
  GET /api/pet/<id>/atlas.json       frame/state descriptor (game engines)
  GET /api/pet/<id>/preview.webp     animated preview (idle->run->jump->wave)
  GET /api/pet/<id>.zip              installable pack: pet.json + spritesheet.webp
  GET /api/manifest                  basic collection info

Renders are ~45ms and cached in-process. Deploy behind any WSGI/reverse proxy, or
containerize; it only needs Python + Pillow + this repo's images/ + metadata/.
"""
import io
import json
import os
import sys
import zipfile
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import animator as A  # noqa: E402
import build_pet as BP  # noqa: E402

SUPPLY = A.common.SUPPLY
SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site", "index.html")


def _webp(img, animated=False, frames=None, durations=None):
    # Lossless m6 for the deliverable sheets: smallest AND pixel-perfect for this
    # crisp art (lossy adds edge noise and is actually larger). The preview is lossy
    # since it's just a thumbnail and animated-lossless would be heavy.
    buf = io.BytesIO()
    if animated:
        frames[0].save(buf, format="WEBP", save_all=True, append_images=frames[1:],
                       duration=durations, loop=0, quality=80, method=4)
    else:
        img.save(buf, format="WEBP", lossless=True, method=6)
    return buf.getvalue()


@lru_cache(maxsize=256)
def render(tok):
    """Render everything for a token once; cache the encoded bytes."""
    layers, is_unique = A.load_layers(tok)
    _, attrs = A.common.load_meta(tok)
    petdex, _ = BP.build_sheet(layers, A.PETDEX_STATES)
    game, meta_rows = BP.build_sheet(layers, A.PETDEX_STATES + A.GAME_STATES)
    pet = BP.pet_json(tok, is_unique, attrs)
    atlas = {"frameWidth": A.FRAME_W, "frameHeight": A.FRAME_H,
             "columns": A.COLS, "states": meta_rows}
    # animated preview: a few states back to back
    pv, durs = [], []
    for st in ("idle", "running-right", "jumping", "waving", "review"):
        n, dur = next((f, d) for s, f, d in A.PETDEX_STATES if s == st)
        for fr in A.frames_for(st, layers):
            pv.append(fr.convert("RGBA"))
            durs.append(max(60, dur // n))
    return {
        "pet.json": json.dumps(pet, indent=2).encode(),
        "atlas.json": json.dumps(atlas, indent=2).encode(),
        "spritesheet.webp": _webp(petdex),
        "spritesheet_game.webp": _webp(game),
        "preview.webp": _webp(None, animated=True, frames=pv, durations=durs),
        "_is_unique": is_unique,
    }


def pack_zip(tok):
    r = render(tok)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"tiny-dino-{tok}/pet.json", r["pet.json"])
        z.writestr(f"tiny-dino-{tok}/spritesheet.webp", r["spritesheet.webp"])
    return buf.getvalue()


CT = {"json": "application/json", "webp": "image/webp", "zip": "application/zip",
      "html": "text/html; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    server_version = "tinydinos-pets/1.0"

    def _send(self, body, ctype, code=200, fname=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if fname:
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _err(self, code, msg):
        self._send(json.dumps({"error": msg}).encode(), CT["json"], code)

    def _tok(self, raw):
        try:
            t = int(raw)
        except ValueError:
            return None
        return t if 1 <= t <= SUPPLY else None

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                with open(SITE, "rb") as f:
                    return self._send(f.read(), CT["html"])
            except FileNotFoundError:
                return self._err(500, "site missing")
        if path == "/api/manifest":
            return self._send(json.dumps({
                "name": "tiny dinos", "supply": SUPPLY,
                "frame": [A.FRAME_W, A.FRAME_H], "grid": [9, A.COLS],
                "petdexStates": [s for s, _, _ in A.PETDEX_STATES],
                "gameStates": [s for s, _, _ in A.GAME_STATES],
            }).encode(), CT["json"])

        if path.startswith("/api/pet/"):
            rest = path[len("/api/pet/"):]
            # /api/pet/<id>.zip
            if rest.endswith(".zip"):
                tok = self._tok(rest[:-4])
                if tok is None:
                    return self._err(404, "bad token")
                return self._send(pack_zip(tok), CT["zip"], fname=f"tiny-dino-{tok}.zip")
            # /api/pet/<id>/<file>
            if "/" in rest:
                tid, fname = rest.split("/", 1)
                tok = self._tok(tid)
                if tok is None:
                    return self._err(404, "bad token")
                r = render(tok)
                if fname in r and not fname.startswith("_"):
                    ext = fname.rsplit(".", 1)[-1]
                    return self._send(r[fname], CT.get(ext, "application/octet-stream"))
                return self._err(404, "no such file")
        return self._err(404, "not found")

    def log_message(self, *a):  # quiet
        pass


def main():
    port = int(os.environ.get("PORT", "8017"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"tiny dinos pet generator on http://localhost:{port}  (supply {SUPPLY})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
