"""One-command seasonal pipeline (run after fetch_meta.py + fetch_images.py):
  encode.py     -> on-chain blobs per collection
  reference.py  -> verify SVG rasterises to source image + attributes match,
                   and emit Foundry fixtures
"""
import runpy
import sys

for mod in ["encode", "reference"]:
    print(f"\n=== {mod}.py ===")
    try:
        runpy.run_module(mod, run_name="__main__")
    except SystemExit as e:
        if e.code not in (0, None):
            sys.exit(e.code)
print("\nSEASONAL BUILD COMPLETE")
