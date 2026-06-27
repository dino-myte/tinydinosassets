"""Enumerate the seasonal tiny dinos collections via the OpenSea API.

For each collection: page through all NFTs, collect token ids and the IPFS
metadata baseURI CID (from metadata_url). Writes build/seasons/manifests/<name>.json.
"""
import json
import os
import time
import urllib.request

KEY = os.environ.get("OPENSEA_API_KEY", "24f26fb26b361eb443c87c832541563a")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "manifests")

COLLECTIONS = {
    "summer": ("tiny-dinos-summer-2022", "0x5a1190759c9e7cf42da401639016f8f60affd465"),
    "winter": ("tiny-dinos-winter-2022", "0x89e83f99bc48b9229ea7f2b9509a995e89c8472f"),
    "halloween": ("tiny-dinos-halloween-2022", "0xc1dcc70e27b187457709e0c72db3df941034ec6f"),
}


def api(path):
    url = "https://api.opensea.io/api/v2/" + path
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"X-API-KEY": KEY, "User-Agent": "tinydinos-audit"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"opensea {path}: {last}")


def meta_cid(metadata_url):
    # https://.../ipfs/<CID>/<id>  ->  <CID>
    if not metadata_url or "/ipfs/" not in metadata_url:
        return None
    return metadata_url.split("/ipfs/", 1)[1].split("/", 1)[0]


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, (slug, contract) in COLLECTIONS.items():
        ids, cids = [], set()
        cursor = None
        while True:
            path = f"collection/{slug}/nfts?limit=200" + (f"&next={cursor}" if cursor else "")
            d = api(path)
            for n in d.get("nfts", []):
                ids.append(int(n["identifier"]))
                c = meta_cid(n.get("metadata_url"))
                if c:
                    cids.add(c)
            cursor = d.get("next")
            print(f"  {name}: {len(ids)} ids so far...", flush=True)
            if not cursor:
                break
            time.sleep(0.4)
        ids = sorted(set(ids))
        # Fall back to the single-NFT endpoint if the listing lacked metadata_url.
        if not cids and ids:
            for probe in ids[:5]:
                d = api(f"chain/ethereum/contract/{contract}/nfts/{probe}")
                c = meta_cid((d.get("nft") or {}).get("metadata_url"))
                if c:
                    cids.add(c)
                    break
                time.sleep(0.4)
        assert len(cids) == 1, f"{name}: expected 1 metadata CID, got {cids}"
        manifest = {"name": name, "slug": slug, "contract": contract,
                    "metaCID": cids.pop(), "count": len(ids), "ids": ids}
        with open(os.path.join(OUT, f"{name}.json"), "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"{name}: {len(ids)} tokens, metaCID={manifest['metaCID']}")


if __name__ == "__main__":
    main()
