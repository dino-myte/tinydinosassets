"""Direct check: Solidity imageSVG output -> rasterize -> compare to repo PNGs.

Closes the transitive gap: instead of comparing Solidity output to Python
fixtures, this takes the ACTUAL Solidity SVG (executed on py-evm), rasterizes it,
and asserts pixel-equality against images/dinos/16x16/original/<id>.png.

Env: EVM_STEP (default 200 -> ~50 tokens). EVM_STEP=1 checks all 10,000.
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")

from PIL import Image

import evm_verify as E
import reference_render as R
from common import DINO_DIR


def main():
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
        addr = w3.eth.get_transaction_receipt(tx)["contractAddress"]
        return w3.eth.contract(address=addr, abi=abi)

    OUT = os.path.join(os.path.dirname(DINO_DIR), "..", "..", "build", "out")
    OUT = os.path.join(E.OUT)
    store = deploy(st_abi, st_bin)
    store.functions.setSprites(open(os.path.join(E.OUT, "sprites.bin"), "rb").read()).transact(TX)
    store.functions.setOffsets(open(os.path.join(E.OUT, "spriteOffsets.bin"), "rb").read()).transact(TX)
    tokens = open(os.path.join(E.OUT, "tokens.bin"), "rb").read()
    for off in range(0, len(tokens), 24000):
        store.functions.addTokenChunk(tokens[off:off + 24000]).transact(TX)
    store.functions.seal().transact(TX)
    renderer = deploy(rd_abi, rd_bin, (store.address, "eth"))

    step = int(os.environ.get("EVM_STEP", "200"))
    checked = fails = 0
    for i in range(0, 10000, step):
        tok = i + 1
        # ACTUAL Solidity SVG, executed on the EVM:
        svg = renderer.functions.imageSVG(tok).call()
        # rasterize it back to a 16x16 RGBA grid:
        grid = R.rasterize_svg(svg)
        # the PNG that ships in the repo:
        png = list(Image.open(os.path.join(DINO_DIR, f"{tok}.png")).convert("RGBA").getdata())
        checked += 1
        if grid != png:
            fails += 1
            print(f"  MISMATCH token {tok}")
            # show first differing pixel
            for j in range(256):
                if grid[j] != png[j]:
                    print(f"    px {j}: solidity={grid[j]} png={png[j]}")
                    break
        if checked % 25 == 0:
            print(f"  ...checked {checked} (token {tok})", flush=True)

    print(f"\nSolidity-SVG vs repo-PNG: {checked - fails}/{checked} pixel-exact "
          f"(every {step}th token)")
    print("PASSED" if fails == 0 else "FAILED")
    sys.exit(0 if fails == 0 else 1)


if __name__ == "__main__":
    main()
