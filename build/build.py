"""One-command build + verify pipeline for the on-chain renderer.

Runs, in order:
  1. solve_orders.py      derive each token's exact layer order  -> orders.json
  2. extract.py           encode on-chain blobs                  -> out/*.bin, manifest
  3. gen_solidity.py      generate contracts/src/DinoData.sol
  4. gen_fixtures.py      generate contracts/test/fixtures/*
  5. reference_render.py  prove 10,000/10,000 pixel + metadata exact

After this, run the Solidity differential test (see contracts/README.md):
  cd contracts && forge test
"""
import runpy
import sys

STEPS = [
    ("solve_orders", "deriving per-token layer orders"),
    ("extract", "encoding on-chain blobs"),
    ("gen_solidity", "generating DinoData.sol"),
    ("gen_fixtures", "generating test fixtures"),
    ("reference_render", "verifying 10k pixel + metadata exact"),
]


def main():
    for mod, desc in STEPS:
        print(f"\n=== {mod}.py — {desc} ===")
        try:
            runpy.run_module(mod, run_name="__main__")
        except SystemExit as e:
            if e.code not in (0, None):
                print(f"step {mod} failed with exit code {e.code}")
                sys.exit(e.code)
    print("\nALL BUILD STEPS COMPLETE ✅")


if __name__ == "__main__":
    main()
