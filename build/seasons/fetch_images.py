"""Fetch + downsample each seasonal token to a 16x16 PNG.

  summer            -> IPFS 1600x1600 blocky art -> exact 16x16 (cell centres)
  winter/halloween  -> OpenSea resized image -> approximate 16x16 (cell-region mode)

Resumable: skips tokens already saved. Set SEASON_ONLY=name to do one collection,
SEASON_LIMIT=n to cap (for testing).
"""
import collections
import json
import os
import time
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# summer images live under one IPFS directory CID (from token metadata).
SUMMER_IMG_CID = "QmbFVxGLk8zLfwpNyaGDrPdFMdNmvBtULtUWorsJ5BHPFT"
GATEWAYS = ["https://gateway.pinata.cloud/ipfs", "https://dweb.link/ipfs",
            "https://flk-ipfs.xyz/ipfs", "https://4everland.io/ipfs"]


def http_get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_ipfs(path):
    last = None
    for gw in GATEWAYS:
        try:
            return http_get(f"{gw}/{path}")
        except Exception as e:
            last = e
            time.sleep(0.3)
    raise RuntimeError(f"ipfs {path}: {last}")


def downsample_exact(im):
    """Blocky 1600 (or NxN multiple of 16) -> 16x16 by cell-centre sampling."""
    im = im.convert("RGBA")
    w, h = im.size
    cw, ch = w // 16, h // 16
    p = im.load()
    out = Image.new("RGBA", (16, 16))
    op = out.load()
    for sy in range(16):
        for sx in range(16):
            op[sx, sy] = p[sx * cw + cw // 2, sy * ch + ch // 2]
    return out


def downsample_mode(im):
    """Resized/lossy image -> 16x16 by the most-common colour in each cell's
    central region (robust to compression artefacts at cell edges)."""
    im = im.convert("RGBA")
    w, h = im.size
    p = im.load()
    out = Image.new("RGBA", (16, 16))
    op = out.load()
    for sy in range(16):
        for sx in range(16):
            x0, x1 = sx * w // 16, (sx + 1) * w // 16
            y0, y1 = sy * h // 16, (sy + 1) * h // 16
            mx, my = (x0 + x1) // 2, (y0 + y1) // 2
            r = max(2, (x1 - x0) // 4)
            cnt = collections.Counter()
            for yy in range(max(y0, my - r), min(y1, my + r)):
                for xx in range(max(x0, mx - r), min(x1, mx + r)):
                    cnt[p[xx, yy]] += 1
            op[sx, sy] = cnt.most_common(1)[0][0]
    return out


def main():
    import io
    only = os.environ.get("SEASON_ONLY")
    limit = int(os.environ.get("SEASON_LIMIT", "0"))
    for name in (["summer", "winter", "halloween"] if not only else [only]):
        ddir = os.path.join(DATA, name)
        tokens = json.load(open(os.path.join(ddir, "tokens.json")))
        img_urls = json.load(open(os.path.join(ddir, "image_urls.json")))
        out = os.path.join(ddir, "img16")
        os.makedirs(out, exist_ok=True)
        ids = [t["id"] for t in tokens]
        if limit:
            ids = ids[:limit]
        done = fail = 0
        for i, tid in enumerate(ids):
            dst = os.path.join(out, f"{tid}.png")
            if os.path.exists(dst):
                done += 1
                continue
            try:
                if name == "summer":
                    raw = fetch_ipfs(f"{SUMMER_IMG_CID}/{tid}.png")
                    im = Image.open(io.BytesIO(raw))
                    small = downsample_exact(im)
                else:
                    raw = http_get(img_urls[str(tid)])
                    im = Image.open(io.BytesIO(raw))
                    small = downsample_mode(im)
                small.save(dst)
                done += 1
            except Exception as e:
                fail += 1
                print(f"  {name} #{tid} FAIL: {str(e)[:60]}")
            if (i + 1) % 25 == 0:
                print(f"  {name}: {i + 1}/{len(ids)} ({done} ok, {fail} fail)", flush=True)
        print(f"{name}: {done}/{len(ids)} images ready, {fail} failed")


if __name__ == "__main__":
    main()
