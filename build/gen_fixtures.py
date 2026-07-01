"""Generate test fixtures for the Foundry differential test.

Because the Python reference renderer is proven pixel- and metadata-exact vs the
original collection, asserting the Solidity renderer's output equals these
fixtures transitively proves the Solidity renderer is exact too.

Outputs (contracts/test/fixtures/):
  hashes_eth.json   parallel arrays for all 10,000 tokens (eth deployment):
                    ids[], svgHash[], jsonHash[], uriHash[] (keccak256, bytes32)
  sample.json       full svg/json/uri strings for a representative subset,
                    plus token #1 rendered on every chain (current-chain check).
"""
import base64
import json
import os

from Crypto.Hash import keccak

import reference_render as R
from common import CHAINS, DESCRIPTION, ROOT, SUPPLY
from encoding import ATTR_ORDER

OUT = os.path.join(ROOT, "contracts", "test", "fixtures")


def _assert_no_escape(s):
    assert '"' not in s and "\\" not in s, f"unexpected JSON-special char in: {s!r}"


def metadata_json(tok):
    """Exact compact JSON the Solidity renderer emits (no whitespace). Chain-
    independent: no current-chain; chain is only the static 'minted on' attr."""
    t = R.decode_token(tok)
    svg = R.build_svg(R.composite_grid(tok))
    image = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    if t["unique"]:
        attrs = [("1/1", t["one"]), ("minted on", t["minton"])]
    else:
        attrs = [(c, R.M["values"][c][t["locals"][c]]) for c in ATTR_ORDER]
        attrs.append(("minted on", t["minton"]))
    for _, v in attrs:
        _assert_no_escape(v)
    parts = []
    parts.append('{"name":"tiny dinos #%d"' % tok)
    parts.append(',"description":"%s"' % DESCRIPTION)
    parts.append(',"tokenId":%d' % tok)
    parts.append(',"attributes":[')
    parts.append(",".join(
        '{"trait_type":"%s","value":"%s"}' % (tt, v) for tt, v in attrs))
    parts.append('],"image":"%s"}' % image)
    return "".join(parts)


def token_uri(tok):
    j = metadata_json(tok)
    return "data:application/json;base64," + base64.b64encode(j.encode()).decode()


def kec(s):
    h = keccak.new(digest_bits=256)
    h.update(s.encode())
    return "0x" + h.hexdigest()


def main():
    R.load_blobs()
    os.makedirs(OUT, exist_ok=True)
    _assert_no_escape(DESCRIPTION)

    ids, svgH, jsonH, uriH = [], [], [], []
    for tok in range(1, SUPPLY + 1):
        svg = R.build_svg(R.composite_grid(tok))
        j = metadata_json(tok)
        u = "data:application/json;base64," + base64.b64encode(j.encode()).decode()
        ids.append(tok)
        svgH.append(kec(svg))
        jsonH.append(kec(j))
        uriH.append(kec(u))
        if tok % 2000 == 0:
            print(f"  ...hashed {tok}", flush=True)

    with open(os.path.join(OUT, "hashes_eth.json"), "w") as f:
        json.dump({"ids": ids, "svgHash": svgH, "jsonHash": jsonH, "uriHash": uriH}, f)

    # representative sample with full strings
    orders_raw = {int(k): v for k, v in
                  json.load(open(os.path.join(ROOT, "build", "orders.json"))).items()}
    by_order = {}
    for tok, o in orders_raw.items():
        if o == "UNIQUE":
            continue
        key = tuple(o)
        by_order.setdefault(key, tok)  # first token per order
    sample_ids = sorted(set(
        [1, 2, 10000, SUPPLY]
        + list(by_order.values())                       # one per render order
        + R.M["unique_tokens"]                           # all uniques (incl. #10001)
        + [11, 101, 299, 311]                            # alpha (day-landscape) tokens
    ))
    # flat parallel arrays so Foundry's vm.parseJson*Array can read them directly
    s_ids, s_svg, s_json, s_uri = [], [], [], []
    for tok in sample_ids:
        s_ids.append(tok)
        s_svg.append(R.build_svg(R.composite_grid(tok)))
        s_json.append(metadata_json(tok))
        s_uri.append(token_uri(tok))

    with open(os.path.join(OUT, "sample.json"), "w") as f:
        json.dump({"ids": s_ids, "svg": s_svg, "json": s_json, "uri": s_uri}, f, indent=2)

    # ---- trait fixtures: keccak of each sprite's 1024-byte RGBA (matches traitRGBA) ----
    from common import VIS, load_original, load_sprite, px_list
    M = R.M
    cat_base, values = M["cat_base"], M["values"]

    def rgba_bytes(pixels):
        b = bytearray()
        for (r, g, b_, a) in pixels:
            b += bytes((r, g, b_, a))
        return bytes(b)

    t_gids, t_hash, t_name = [], [], []
    for cat in VIS:
        for vid, val in enumerate(values[cat]):
            t_gids.append(cat_base[cat] + vid)
            t_hash.append("0x" + keccak.new(digest_bits=256)
                          .update(rgba_bytes(px_list(load_sprite(cat, val)))).hexdigest())
            t_name.append(f"{cat}/{val}")
    for uidx, utok in enumerate(M["unique_tokens"]):
        t_gids.append(M["n_composite_sprites"] + uidx)
        t_hash.append("0x" + keccak.new(digest_bits=256)
                      .update(rgba_bytes(px_list(load_original(utok)))).hexdigest())
        t_name.append(f"unique/{utok}")
    with open(os.path.join(OUT, "traits.json"), "w") as f:
        json.dump({"gids": t_gids, "rgbaHash": t_hash, "names": t_name}, f)

    print(f"wrote {OUT}/hashes_eth.json ({SUPPLY} tokens), sample.json "
          f"({len(s_ids)} tokens), traits.json ({len(t_gids)} sprites)")


if __name__ == "__main__":
    main()
