"""Comprehensive on-chain verification: execute the ACTUAL Solidity on py-evm and
compare every kind of output to the CANONICAL repo PNGs (the 1600x1600 set, which
is pixel-identical to the minted IPFS images).

Checks:
  A. dinos (grid)   — renderer.imageSVG -> rasterize 16 -> canonical 16-grid
                      (downsample of images/dinos/1600x1600/original)
  B. dinos (FULL)   — renderer.imageSVG rasterized at 1600x1600, compared
                      pixel-for-pixel to images/dinos/1600x1600/original
  C. traits         — renderer.traitRGBA -> canonical 16-grid of each trait
                      (images/traits/1600x1600/<cat>/<val>.png); uniques -> dino
  D. tokenURI JSON  — renderer.tokenURI -> base64-decode -> metadata/eth

Env EVM_STEP (default 200) samples the per-token loops (A, B-grid, D).
B does a FULL 1600x1600 pixel compare on a small subset (incl. outliers).
"""
import base64
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

from PIL import Image

import evm_verify as E
import reference_render as R
from common import (CHAINS, DINO_DIR, TRAIT_DIR, VIS, load_meta, load_original,
                    load_sprite, px_list)

# Tokens with the largest 16<->1600 divergence (snow/night landscape) — the
# outliers the fix must now render exactly at full resolution.
OUTLIER_TOKENS = [751, 2918, 3657]
FULL_RES_SAMPLE = [1, 2, 9, 100] + OUTLIER_TOKENS


def deploy_all():
    (st_abi, st_bin), (rd_abi, rd_bin) = E.compile_all()
    from eth_tester import EthereumTester, PyEVMBackend
    from web3 import Web3
    from web3.providers.eth_tester import EthereumTesterProvider

    genesis = PyEVMBackend.generate_genesis_params(overrides={"gas_limit": 10**9})
    w3 = Web3(EthereumTesterProvider(EthereumTester(PyEVMBackend(genesis_parameters=genesis))))
    acct = w3.eth.accounts[0]
    w3.eth.default_account = acct
    TX = {"from": acct, "gas": 900_000_000}

    def deploy(abi, b, args=()):
        c = w3.eth.contract(abi=abi, bytecode=b)
        tx = c.constructor(*args).transact(TX)
        return w3.eth.contract(address=w3.eth.get_transaction_receipt(tx)["contractAddress"], abi=abi)

    store = deploy(st_abi, st_bin)
    store.functions.setSprites(open(os.path.join(E.OUT, "sprites.bin"), "rb").read()).transact(TX)
    store.functions.setOffsets(open(os.path.join(E.OUT, "spriteOffsets.bin"), "rb").read()).transact(TX)
    tokens = open(os.path.join(E.OUT, "tokens.bin"), "rb").read()
    for off in range(0, len(tokens), 24000):
        store.functions.addTokenChunk(tokens[off:off + 24000]).transact(TX)
    store.functions.seal().transact(TX)
    renderer = deploy(rd_abi, rd_bin, (store.address, "eth"))
    return renderer, (rd_abi, rd_bin), store, deploy


def upscale_to_1600(grid16):
    """Expand a 16x16 grid to a 1600x1600 image (each cell -> 100x100 block)."""
    big = Image.new("RGBA", (1600, 1600))
    bp = big.load()
    for sy in range(16):
        for sx in range(16):
            c = grid16[sy * 16 + sx]
            for dy in range(100):
                for dx in range(100):
                    bp[sx * 100 + dx, sy * 100 + dy] = c
    return big


def main():
    R.M = json.load(open(os.path.join(E.OUT, "manifest.json")))
    R.load_blobs()
    renderer, (rd_abi, rd_bin), store, deploy = deploy_all()
    step = int(os.environ.get("EVM_STEP", "200"))
    fails = 0

    # ---- A: dinos 16-grid vs canonical ----
    a_ck = a_bad = 0
    for i in range(0, 10000, step):
        tok = i + 1
        g = R.rasterize_svg(renderer.functions.imageSVG(tok).call())
        a_ck += 1
        if g != px_list(load_original(tok)):
            a_bad += 1; fails += 1; print(f"  A grid mismatch token {tok}")
    print(f"A. dinos grid (Solidity SVG -> canonical 16-grid): {a_ck - a_bad}/{a_ck} exact")

    # ---- B: FULL 1600x1600 pixel-for-pixel vs canonical PNG ----
    b_ck = b_bad = 0
    for tok in FULL_RES_SAMPLE:
        g = R.rasterize_svg(renderer.functions.imageSVG(tok).call())
        rendered = list(upscale_to_1600(g).getdata())
        canon = list(Image.open(os.path.join(DINO_DIR, f"{tok}.png")).convert("RGBA").getdata())
        b_ck += 1
        if rendered != canon:
            b_bad += 1; fails += 1
            nd = sum(1 for a, b in zip(rendered, canon) if a != b)
            print(f"  B FULL-RES mismatch token {tok}: {nd} of 2,560,000 px differ")
    print(f"B. dinos FULL 1600x1600 (Solidity SVG upscaled -> canonical PNG): "
          f"{b_ck - b_bad}/{b_ck} pixel-exact  (incl. outliers {OUTLIER_TOKENS})")

    # ---- C: traits ----
    M = R.M
    cat_base, values = M["cat_base"], M["values"]
    c_ck = c_bad = 0
    for cat in VIS:
        for vid, val in enumerate(values[cat]):
            gid = cat_base[cat] + vid
            raw = renderer.functions.traitRGBA(gid).call()
            got = [(raw[k], raw[k + 1], raw[k + 2], raw[k + 3]) for k in range(0, 1024, 4)]
            c_ck += 1
            if got != px_list(load_sprite(cat, val)):
                c_bad += 1; fails += 1; print(f"  C trait mismatch {cat}/{val}")
    for uidx, utok in enumerate(M["unique_tokens"]):
        gid = M["n_composite_sprites"] + uidx
        raw = renderer.functions.traitRGBA(gid).call()
        got = [(raw[k], raw[k + 1], raw[k + 2], raw[k + 3]) for k in range(0, 1024, 4)]
        c_ck += 1
        if got != px_list(load_original(utok)):
            c_bad += 1; fails += 1; print(f"  C unique mismatch token {utok}")
    print(f"C. traits (Solidity traitRGBA -> canonical): {c_ck - c_bad}/{c_ck} exact "
          f"(105 traits + 15 uniques)")

    # ---- D: tokenURI JSON ----
    d_ck = d_bad = 0
    for i in range(0, 10000, step):
        tok = i + 1
        uri = renderer.functions.tokenURI(tok).call()
        meta = json.loads(base64.b64decode(uri.split(",", 1)[1]))
        src, _ = load_meta(tok, "eth")
        d_ck += 1
        if not (meta["name"] == src["name"] and meta["description"] == src["description"]
                and meta["tokenId"] == src["tokenId"] and meta["attributes"] == src["attributes"]
                and meta["current-chain"] == src["current-chain"]
                and meta["image"].startswith("data:image/svg+xml;base64,")):
            d_bad += 1; fails += 1; print(f"  D tokenURI mismatch token {tok}")
    print(f"D. tokenURI JSON (Solidity -> decode -> metadata/eth): {d_ck - d_bad}/{d_ck} exact")
    pc_bad = 0
    for chain in CHAINS:
        r = deploy(rd_abi, rd_bin, (store.address, chain))
        meta = json.loads(base64.b64decode(r.functions.tokenURI(1).call().split(",", 1)[1]))
        if meta["current-chain"] != chain:
            pc_bad += 1; fails += 1
    print(f"   per-chain current-chain via tokenURI: {len(CHAINS) - pc_bad}/{len(CHAINS)} correct")

    print("\n" + ("ALL SOLIDITY CHECKS PASSED" if fails == 0 else f"{fails} FAILURES"))
    sys.exit(0 if fails == 0 else 1)


if __name__ == "__main__":
    main()
