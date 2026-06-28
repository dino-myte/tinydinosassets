"""Audit the LIVE Base summer deployment (option B).

1. STORAGE BYTES — read every on-chain blob from SeasonalStorage and assert it is
   byte-identical to the locally-verified build/seasons/out_b/summer blobs, and
   that storage is sealed. Since reference_b.py proved decoding those exact blobs
   reconstructs all 10,001 images + traits exactly, byte-identity proves the live
   contract renders all 10,001 exactly.
2. LIVE RENDER — call the live renderer's metadataJSON, decode the SVG, rasterise,
   and compare pixel-for-pixel to the source 16x16 + attributes to source metadata.
   AUDIT_STEP=1 audits all 10,001; default samples.
"""
import base64
import json
import os
import re
import struct
import sys
import time
import urllib.request

from Crypto.Hash import keccak
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out_b", "summer")
REC = json.load(open(os.path.join(ROOT, "contracts", "deployments", "summer-base.json")))
STORE = REC["contracts"]["SeasonalStorage"]
REND = REC["contracts"]["SeasonalRenderer"]
RPCS = [
    "https://base-rpc.publicnode.com",
    "https://base.drpc.org",
    "https://mainnet.base.org",
    "https://base.meowrpc.com",
    "https://base.blockpi.network/v1/rpc/public",
    "https://1rpc.io/base",
    "https://base-mainnet.public.blastapi.io",
]


def sel(s):
    h = keccak.new(digest_bits=256); h.update(s.encode()); return h.hexdigest()[:8]


_tl = __import__("threading").local()


def rpc(method, params, gw0=0):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    n = len(RPCS)
    for a in range(24):
        try:
            req = urllib.request.Request(RPCS[(gw0 + a) % n], data=body,
                                         headers={"content-type": "application/json", "User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.load(r)
            if "result" in d:
                return d["result"]
            last = d.get("error")
        except Exception as e:
            last = e
        time.sleep(min(2.0, 0.2 * (a + 1)))
    raise RuntimeError(f"rpc {method}: {last}")


def call(to, sig, *uints, gw0=0):
    data = "0x" + sel(sig) + "".join(f"{a:064x}" for a in uints)
    return rpc("eth_call", [{"to": to, "data": data}, "latest"], gw0=gw0)


def dec_bytes(res):
    h = res[2:]
    ln = int(h[64:128], 16)
    return bytes.fromhex(h[128:128 + ln * 2])


def dec_str(res):
    return dec_bytes(res).decode()


RECT = re.compile(r"<rect x='(\d+)' y='(\d+)' width='(\d+)' height='1' fill='#([0-9a-f]{6}(?:[0-9a-f]{2})?)'/>")


def raster(svg):
    g = [None] * 256
    for m in RECT.finditer(svg):
        x, y, w, hx = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        r, gn, b = int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)
        a = int(hx[6:8], 16) if len(hx) == 8 else 255
        for xx in range(x, x + w):
            g[y * 16 + xx] = (r, gn, b, a)
    return g


def grid16(tid):
    im = Image.open(os.path.join(ROOT, "images", "seasons", "summer", "1600x1600", f"{tid}.png")).convert("RGBA")
    w, h = im.size; cw, ch = w // 16, h // 16; p = im.load()
    return [p[sx * cw + cw // 2, sy * ch + ch // 2] for sy in range(16) for sx in range(16)]


def main():
    M = json.load(open(os.path.join(OUT, "manifest.json")))
    fails = 0

    print("== 1. on-chain storage bytes vs local verified blobs ==")
    checks = []
    for i in range(M["nSpriteChunks"]):
        checks.append((f"sprites/{i:04d}.bin", dec_bytes(call(STORE, "spriteChunk(uint256)", i))))
    checks.append(("spriteLoc.bin", dec_bytes(call(STORE, "spriteLoc()"))))
    for i in range(M["nDataChunks"]):
        checks.append((f"data/{i:04d}.bin", dec_bytes(call(STORE, "dataChunk(uint256)", i))))
    for i in range(M["nLocChunks"]):
        checks.append((f"loc/{i:04d}.bin", dec_bytes(call(STORE, "locChunk(uint256)", i))))
    checks.append(("corrPalette.bin", dec_bytes(call(STORE, "corrPalette()"))))
    checks.append(("cats.txt", dec_bytes(call(STORE, "cats()"))))
    checks.append(("vals.txt", dec_bytes(call(STORE, "vals()"))))
    checks.append(("one.txt", dec_bytes(call(STORE, "one()"))))
    bad_bytes = 0
    total_bytes = 0
    for rel, onchain in checks:
        local = open(os.path.join(OUT, rel), "rb").read()
        total_bytes += len(onchain)
        if onchain != local:
            bad_bytes += 1
            print(f"   MISMATCH {rel}: on-chain {len(onchain)}B vs local {len(local)}B")
    frozen = int(call(STORE, "frozen()"), 16) == 1
    print(f"   {len(checks)} blobs, {total_bytes:,} bytes: {'ALL byte-identical' if bad_bytes==0 else f'{bad_bytes} MISMATCH'}")
    print(f"   storage sealed/immutable: {frozen}")
    fails += bad_bytes + (0 if frozen else 1)

    print("== 2. live render + traits vs source ==")
    step = int(os.environ.get("AUDIT_STEP", "100"))
    one_ids = set()
    ids = sorted(set(range(1, M["count"] + 1, step)))
    # always include all 1/1 tokens + first/last
    for tid in range(1, M["count"] + 1):
        if "1/1" in {a["trait_type"] for a in json.load(open(os.path.join(ROOT, "metadata", "seasons", "summer", str(tid))))["attributes"]}:
            one_ids.add(tid)
    ids = sorted(set(ids) | one_ids | {1, M["count"]})
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    lock = threading.Lock()
    prog = [0]

    def check(tid):
        meta = json.loads(dec_str(call(REND, "metadataJSON(uint256)", tid, gw0=tid % len(RPCS))))
        svg = base64.b64decode(meta["image"].split(",", 1)[1]).decode()
        img_ok = raster(svg) == grid16(tid)
        src = json.load(open(os.path.join(ROOT, "metadata", "seasons", "summer", str(tid))))
        got = {a["trait_type"]: a["value"] for a in meta["attributes"]}
        want = {a["trait_type"]: a["value"] for a in src["attributes"]}
        attr_ok = got == want and meta["name"] == f'{M["displayName"]} #{tid}'
        with lock:
            prog[0] += 1
            if prog[0] % 500 == 0:
                print(f"   ...{prog[0]}/{len(ids)}", flush=True)
        return tid, img_ok, attr_ok, got, want

    img_bad = attr_bad = 0
    with ThreadPoolExecutor(max_workers=16) as ex:
        for f in as_completed([ex.submit(check, t) for t in ids]):
            tid, img_ok, attr_ok, got, want = f.result()
            if not img_ok:
                img_bad += 1; print(f"   image MISMATCH #{tid}")
            if not attr_ok:
                attr_bad += 1; print(f"   trait MISMATCH #{tid}: {got} vs {want}")
    print(f"   live render exact: {len(ids)-img_bad}/{len(ids)}  traits exact: {len(ids)-attr_bad}/{len(ids)} "
          f"(incl. all {len(one_ids)} 1/1 tokens)")
    fails += img_bad + attr_bad

    print("\n" + ("LIVE AUDIT PASSED — every summer NFT is pixel-perfect + traits exact"
                  if fails == 0 else f"{fails} FAILURES"))
    sys.exit(0 if fails == 0 else 1)


if __name__ == "__main__":
    main()
