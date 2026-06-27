"""Fetch ids + traits for the seasonal collections from the OpenSea API.

Writes build/seasons/data/<name>/tokens.json = [{"id": int, "attrs": {cat: val}}].
Traits are the only fully-recoverable metadata for winter/halloween (their
tinydinos.fun metadata API is offline); summer traits also come from here and are
cross-checked against IPFS later.
"""
import json
import os
import time
import urllib.request

KEY = os.environ.get("OPENSEA_API_KEY", "24f26fb26b361eb443c87c832541563a")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

SLUGS = {
    "summer": "tiny-dinos-summer-2022",
    "winter": "tiny-dinos-winter-2022",
    "halloween": "tiny-dinos-halloween-2022",
}
# canonical visual categories (same 9 as the genesis collection), output order
ATTR_ORDER = ["background", "body", "chest", "eyes", "face", "feet", "hands", "head", "spikes"]


def api(path):
    url = "https://api.opensea.io/api/v2/" + path
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, headers={"X-API-KEY": KEY, "User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"opensea {path}: {last}")


def main():
    for name, slug in SLUGS.items():
        out_dir = os.path.join(DATA, name)
        os.makedirs(out_dir, exist_ok=True)
        tokens, cursor = [], None
        img_urls = {}
        while True:
            path = f"collection/{slug}/nfts?limit=200" + (f"&next={cursor}" if cursor else "")
            d = api(path)
            for n in d.get("nfts", []):
                tid = int(n["identifier"])
                attrs = {t["trait_type"]: t["value"] for t in (n.get("traits") or [])}
                tokens.append({"id": tid, "attrs": attrs})
                img_urls[tid] = n.get("image_url")
            cursor = d.get("next")
            if not cursor:
                break
            time.sleep(0.4)
        tokens.sort(key=lambda t: t["id"])
        # sanity: which categories appear
        cats = sorted({c for t in tokens for c in t["attrs"]})
        with open(os.path.join(out_dir, "tokens.json"), "w") as f:
            json.dump(tokens, f)
        with open(os.path.join(out_dir, "image_urls.json"), "w") as f:
            json.dump(img_urls, f)
        print(f"{name}: {len(tokens)} tokens | categories={cats}")


if __name__ == "__main__":
    main()
