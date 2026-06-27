"""Fetch the FULL summer collection (all 10,001 ids) from IPFS, concurrently, and
save the raw files into the repo (so the originals live on GitHub):

  images/seasons/summer/1600x1600/<id>.png   raw IPFS image bytes
  metadata/seasons/summer/<id>               raw IPFS metadata JSON

Concurrent (thread pool, gateway-rotating), resumable. The 16x16 + on-chain
encoding are derived from these committed raw files by encode.py.
"""
import io
import json
import os
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
IMG_DIR = os.path.join(ROOT, "images", "seasons", "summer", "1600x1600")
META_DIR = os.path.join(ROOT, "metadata", "seasons", "summer")

META_CID = "QmeBjpU8UZedsHc2SULDuBe48rBfwmZCLwvX5tgqKKHCXW"
IMG_CID = "QmbFVxGLk8zLfwpNyaGDrPdFMdNmvBtULtUWorsJ5BHPFT"
SUPPLY = 10001
GATEWAYS = [
    "https://gateway.pinata.cloud/ipfs",
    "https://dweb.link/ipfs",
    "https://flk-ipfs.xyz/ipfs",
    "https://4everland.io/ipfs",
    "https://w3s.link/ipfs",
    "https://ipfs.io/ipfs",
    "https://trustless-gateway.link/ipfs",
    "https://cloudflare-ipfs.com/ipfs",
]
WORKERS = int(os.environ.get("WORKERS", "24"))

_lock = threading.Lock()
_done = [0]
_fail = [0]


def _fetch(path, gw0, validate):
    n = len(GATEWAYS)
    for k in range(n):
        gw = GATEWAYS[(gw0 + k) % n]
        try:
            req = urllib.request.Request(f"{gw}/{path}", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = r.read()
            validate(data)
            return data
        except Exception:
            continue
    return None


def _valid_json(d):
    json.loads(d)


def _valid_png(d):
    im = Image.open(io.BytesIO(d))
    im.convert("RGBA").load()
    assert im.size[0] % 16 == 0 and im.size[1] % 16 == 0


def work(tid):
    ip = os.path.join(IMG_DIR, f"{tid}.png")
    mp = os.path.join(META_DIR, str(tid))
    gw0 = (tid * 7) % len(GATEWAYS)
    ok = True
    if not os.path.exists(mp):
        m = _fetch(f"{META_CID}/{tid}", gw0, _valid_json)
        if m:
            with open(mp, "wb") as f:
                f.write(m)
        else:
            ok = False
    if not os.path.exists(ip):
        raw = _fetch(f"{IMG_CID}/{tid}.png", gw0 + 1, _valid_png)
        if raw:
            with open(ip, "wb") as f:
                f.write(raw)
        else:
            ok = False
    with _lock:
        if ok:
            _done[0] += 1
        else:
            _fail[0] += 1
        tot = _done[0] + _fail[0]
        if tot % 200 == 0:
            print(f"  {tot}/{len(TODO)} done={_done[0]} fail={_fail[0]}", flush=True)
    return tid, ok


def main():
    os.makedirs(IMG_DIR, exist_ok=True)
    os.makedirs(META_DIR, exist_ok=True)
    global TODO
    TODO = [t for t in range(1, SUPPLY + 1)
            if not (os.path.exists(os.path.join(IMG_DIR, f"{t}.png"))
                    and os.path.exists(os.path.join(META_DIR, str(t))))]
    print(f"to fetch: {len(TODO)} (already have {SUPPLY - len(TODO)})", flush=True)
    failed = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(work, t) for t in TODO]
        for f in as_completed(futs):
            tid, ok = f.result()
            if not ok:
                failed.append(tid)
    print(f"DONE: images={len(os.listdir(IMG_DIR))} meta={len(os.listdir(META_DIR))} "
          f"failed={len(failed)}")
    if failed:
        print("failed ids (rerun to retry):", failed[:50])
        sys.exit(1)


if __name__ == "__main__":
    main()
