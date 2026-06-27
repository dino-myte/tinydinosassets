"""Audit the LIVE Base deployment against the canonical assets.

Reads directly from Base mainnet (robust across several public RPCs) and checks:
  1. STORAGE bytes — the SSTORE2 blobs on-chain are byte-identical to build/out
     (sprites + offsets + token records). This alone proves every token's data
     and every sprite's pixels are exact on-chain.
  2. TRAITS (live) — renderer.traitRGBA(gid) for all 120 sprites == canonical
     trait PNGs / unique images.
  3. IMAGES + ATTRIBUTES (live) — renderer.metadataJSON(id) for a sample: decode
     the on-chain SVG and pixel-compare to canonical; attributes == metadata/eth.

Env AUDIT_STEP (default 50 -> 200 token sample) controls the metadataJSON sample;
AUDIT_STEP=1 audits all 10,000 live (slow).
"""
import base64
import json
import os
import re
import sys
import time
import urllib.request

from Crypto.Hash import keccak
from PIL import Image

from common import VIS, load_meta, load_original, load_sprite, px_list
from encoding import ATTR_ORDER

STORE = "0x44Ee00a054782aEBEe68762803fe813040110C4f"
RENDERER = "0x3A10c274aB131a7A0397e75dB4Ec4448AE6B3BF3"
RPCS = [
    "https://base-rpc.publicnode.com",
    "https://base.drpc.org",
    "https://mainnet.base.org",
]
OUT = os.path.join(os.path.dirname(__file__), "out")


def sel(sig):
    h = keccak.new(digest_bits=256)
    h.update(sig.encode())
    return h.hexdigest()[:8]


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    for attempt in range(6):
        ep = RPCS[attempt % len(RPCS)]
        try:
            req = urllib.request.Request(ep, data=body, headers={
                "content-type": "application/json",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            })
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.load(r)
            if "result" in d:
                return d["result"]
            last = d.get("error")
        except Exception as e:
            last = e
        time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"rpc {method} failed: {last}")


def call(to, sig, *uint_args):
    data = "0x" + sel(sig) + "".join(f"{a:064x}" for a in uint_args)
    return rpc("eth_call", [{"to": to, "data": data}, "latest"])


def dec_addr(res):
    return "0x" + res[-40:]


def dec_bytes(res):
    h = res[2:]
    ln = int(h[64:128], 16)
    return bytes.fromhex(h[128:128 + ln * 2])


def get_code_bytes(addr):
    h = rpc("eth_getCode", [addr, "latest"])
    b = bytes.fromhex(h[2:])
    assert b and b[0] == 0, "expected SSTORE2 STOP prefix"
    return b[1:]


RECT = re.compile(r"<rect x='(\d+)' y='(\d+)' width='(\d+)' height='1' fill='#([0-9a-f]{6}(?:[0-9a-f]{2})?)'/>")


def raster(svg):
    g = [None] * 256
    for m in RECT.finditer(svg):
        x, y, w, hexc = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        r, gn, b = int(hexc[0:2], 16), int(hexc[2:4], 16), int(hexc[4:6], 16)
        a = int(hexc[6:8], 16) if len(hexc) == 8 else 255
        for xx in range(x, x + w):
            g[y * 16 + xx] = (r, gn, b, a)
    return g


def main():
    M = json.load(open(os.path.join(OUT, "manifest.json")))
    fails = 0

    # 1. STORAGE bytes
    print("== 1. on-chain storage bytes vs local build/out ==")
    sp = dec_addr(call(STORE, "spritesPtr()"))
    op = dec_addr(call(STORE, "offsetsPtr()"))
    chunks = [dec_addr(call(STORE, "tokenPtrs(uint256)", i)) for i in range(3)]
    frozen = int(call(STORE, "frozen()"), 16) == 1
    sprites = open(os.path.join(OUT, "sprites.bin"), "rb").read()
    offsets = open(os.path.join(OUT, "spriteOffsets.bin"), "rb").read()
    tokens = open(os.path.join(OUT, "tokens.bin"), "rb").read()
    ok_sp = get_code_bytes(sp) == sprites
    ok_op = get_code_bytes(op) == offsets
    ok_tok = b"".join(get_code_bytes(c) for c in chunks) == tokens
    for label, ok, n in [("sprites.bin", ok_sp, len(sprites)),
                         ("spriteOffsets.bin", ok_op, len(offsets)),
                         ("tokens.bin", ok_tok, len(tokens))]:
        print(f"   {label:18} on-chain == local: {ok}  ({n:,} bytes)")
        fails += not ok
    print(f"   storage sealed/immutable: {frozen}")
    fails += not frozen

    # 2. TRAITS (live)
    print("== 2. live traits (renderer.traitRGBA) vs canonical ==")
    tbad = 0
    cat_base, values = M["cat_base"], M["values"]
    for cat in VIS:
        for vid, val in enumerate(values[cat]):
            gid = cat_base[cat] + vid
            raw = dec_bytes(call(RENDERER, "traitRGBA(uint256)", gid))
            got = [(raw[k], raw[k + 1], raw[k + 2], raw[k + 3]) for k in range(0, 1024, 4)]
            if got != px_list(load_sprite(cat, val)):
                tbad += 1; print(f"   MISMATCH {cat}/{val}")
    for uidx, utok in enumerate(M["unique_tokens"]):
        gid = M["n_composite_sprites"] + uidx
        raw = dec_bytes(call(RENDERER, "traitRGBA(uint256)", gid))
        got = [(raw[k], raw[k + 1], raw[k + 2], raw[k + 3]) for k in range(0, 1024, 4)]
        if got != px_list(load_original(utok)):
            tbad += 1; print(f"   MISMATCH unique #{utok}")
    print(f"   traits exact: {120 - tbad}/120 (105 traits + 15 uniques)")
    fails += tbad

    # 3. IMAGES + ATTRIBUTES (live sample)
    step = int(os.environ.get("AUDIT_STEP", "50"))
    ids = sorted(set(list(range(1, 10001, step)) + M["unique_tokens"] + [751, 2918, 3657]))
    print(f"== 3. live metadataJSON: {len(ids)} tokens (image px + attributes) ==")
    ibad = abad = 0
    for k, tok in enumerate(ids):
        j = dec_bytes(call(RENDERER, "metadataJSON(uint256)", tok)).decode()
        meta = json.loads(j)
        svg = base64.b64decode(meta["image"].split(",", 1)[1]).decode()
        if raster(svg) != px_list(load_original(tok)):
            ibad += 1; print(f"   image MISMATCH #{tok}")
        src, _ = load_meta(tok, "eth")
        if meta["attributes"] != src["attributes"] or meta["name"] != src["name"]:
            abad += 1; print(f"   attrs MISMATCH #{tok}")
        if (k + 1) % 50 == 0:
            print(f"   ...{k + 1}/{len(ids)}", flush=True)
    print(f"   images exact:     {len(ids) - ibad}/{len(ids)}")
    print(f"   attributes exact: {len(ids) - abad}/{len(ids)}")
    fails += ibad + abad

    print("\n" + ("LIVE AUDIT PASSED — Base deployment matches canonical"
                  if fails == 0 else f"{fails} FAILURES"))
    sys.exit(0 if fails == 0 else 1)


if __name__ == "__main__":
    main()
