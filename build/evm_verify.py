"""Execute the compiled Solidity on a local py-evm and verify against fixtures.

Deploys DinoStorage + DinoRenderer, loads the real build blobs, then checks the
renderer's imageSVG / metadataJSON / tokenURI against the Python-generated
fixtures (which are proven exact vs the original collection).
"""
import glob
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

import solcx
from eth_tester import EthereumTester, PyEVMBackend
from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider

from common import ROOT

CONTRACTS = os.path.join(ROOT, "contracts")
OUT = os.path.join(ROOT, "build", "out")
FIX = os.path.join(CONTRACTS, "test", "fixtures")


def compile_all():
    solcx.set_solc_version("0.8.24")
    os.chdir(CONTRACTS)
    sources = {f: {"content": open(f).read()}
               for f in glob.glob("src/**/*.sol", recursive=True)}
    inp = {
        "language": "Solidity", "sources": sources,
        "settings": {
            "viaIR": True, "optimizer": {"enabled": True, "runs": 200},
            "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}},
        },
    }
    out = solcx.compile_standard(inp, allow_paths=".")
    errs = [e for e in out.get("errors", []) if e["severity"] == "error"]
    if errs:
        for e in errs:
            print(e["formattedMessage"])
        sys.exit(1)

    def pick(name):
        for f, cs in out["contracts"].items():
            if name in cs:
                c = cs[name]
                return c["abi"], c["evm"]["bytecode"]["object"]
        raise KeyError(name)

    return pick("DinoStorage"), pick("DinoRenderer")


def main():
    (st_abi, st_bin), (rd_abi, rd_bin) = compile_all()

    genesis = PyEVMBackend.generate_genesis_params(overrides={"gas_limit": 10**9})
    t = EthereumTester(PyEVMBackend(genesis_parameters=genesis))
    w3 = Web3(EthereumTesterProvider(t))
    acct = w3.eth.accounts[0]
    w3.eth.default_account = acct
    TX = {"from": acct, "gas": 900_000_000}

    def deploy(abi, b, args=()):
        c = w3.eth.contract(abi=abi, bytecode=b)
        tx = c.constructor(*args).transact(TX)
        addr = w3.eth.get_transaction_receipt(tx)["contractAddress"]
        return w3.eth.contract(address=addr, abi=abi)

    print("deploying DinoStorage + loading blobs...")
    store = deploy(st_abi, st_bin)
    sprites = open(os.path.join(OUT, "sprites.bin"), "rb").read()
    offsets = open(os.path.join(OUT, "spriteOffsets.bin"), "rb").read()
    tokens = open(os.path.join(OUT, "tokens.bin"), "rb").read()
    store.functions.setSprites(sprites).transact(TX)
    store.functions.setOffsets(offsets).transact(TX)
    CHUNK = 24000
    for off in range(0, len(tokens), CHUNK):
        store.functions.addTokenChunk(tokens[off:off + CHUNK]).transact(TX)
    store.functions.seal().transact(TX)
    assert store.functions.totalTokens().call() == 10000

    renderer = deploy(rd_abi, rd_bin, (store.address,))

    # ---- sample fixtures: full-string comparison ----
    sample = json.load(open(os.path.join(FIX, "sample.json")))
    fails = 0
    for k, tok in enumerate(sample["ids"]):
        gsvg = renderer.functions.imageSVG(tok).call()
        gjson = renderer.functions.metadataJSON(tok).call()
        guri = renderer.functions.tokenURI(tok).call()
        if gsvg != sample["svg"][k]:
            fails += 1; print(f"  SVG mismatch token {tok}")
        if gjson != sample["json"][k]:
            fails += 1; print(f"  JSON mismatch token {tok}")
        if guri != sample["uri"][k]:
            fails += 1; print(f"  URI mismatch token {tok}")
    print(f"sample ({len(sample['ids'])} tokens): {'OK' if fails == 0 else f'{fails} FAILURES'}")

    # ---- broad sweep: keccak over every Nth token vs hashes_eth.json ----
    H = json.load(open(os.path.join(FIX, "hashes_eth.json")))
    step = int(os.environ.get("EVM_STEP", "200"))  # default ~50 tokens; EVM_STEP=1 for all
    swept = 0
    for i in range(0, 10000, step):
        tok = i + 1
        gsvg = renderer.functions.imageSVG(tok).call()
        gh = "0x" + w3.keccak(text=gsvg).hex() if False else "0x" + Web3.keccak(gsvg.encode()).hex()
        if gh != H["svgHash"][i]:
            fails += 1; print(f"  sweep SVG hash mismatch token {tok}")
        swept += 1
    print(f"keccak sweep (every {step}th token, {swept} tokens): "
          f"{'OK' if fails == 0 else 'FAILURES'}")

    print("\n" + ("EVM VERIFICATION PASSED" if fails == 0 else "EVM VERIFICATION FAILED"))
    sys.exit(0 if fails == 0 else 1)


if __name__ == "__main__":
    main()
