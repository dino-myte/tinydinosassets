"""Derive each token's exact bottom->top source-over layer order.

For every non-unique token we find an ordering of its present trait sprites that,
composited source-over, reproduces the original PNG pixel-for-pixel. Strategy:
pairwise "who is on top" evidence -> per-token topological sort -> verify;
fall back to a full permutation search for the rare ambiguous token.

Output: build/orders.json mapping tokenId -> list of category names in draw
order (bottom first). Uniques are recorded as "UNIQUE".
"""
import collections
import itertools
import json
import os
import sys

from common import (CAT_INDEX, ROOT, SUPPLY, VIS, composite_pixels, is_unique,
                    load_meta, load_original, load_sprite, px_list)

OUT = os.path.join(ROOT, "build", "orders.json")


def _composite_matches(layers_px, orig):
    return composite_pixels(layers_px) == orig


def solve_token(tok):
    _, attrs = load_meta(tok)
    if is_unique(attrs):
        return "UNIQUE"
    present = [c for c in VIS if attrs.get(c) is not None]
    spr_px = {c: px_list(load_sprite(c, attrs[c])) for c in present}
    orig = px_list(load_original(tok))
    opaque = {c: {i for i, p in enumerate(spr_px[c]) if p[3] > 0} for c in present}

    # Pairwise above-constraints from clean evidence: a pixel where exactly one
    # of the two sprites is fully opaque AND equals the original -> it's on top.
    indeg = {c: 0 for c in present}
    edges = set()  # (below, above)
    for c1, c2 in itertools.combinations(present, 2):
        common = opaque[c1] & opaque[c2]
        if not common:
            continue
        t1 = t2 = 0
        for i in common:
            a1 = spr_px[c1][i][3] == 255 and orig[i] == spr_px[c1][i]
            a2 = spr_px[c2][i][3] == 255 and orig[i] == spr_px[c2][i]
            if a1 and not a2:
                t1 += 1
            elif a2 and not a1:
                t2 += 1
        if t1 > t2 and t1:
            edges.add((c2, c1))  # c1 above c2
        elif t2 > t1 and t2:
            edges.add((c1, c2))  # c2 above c1
    for _, ab in edges:
        indeg[ab] += 1

    # Kahn topo sort, tie-break by canonical category order for determinism.
    avail = sorted([c for c in present if indeg[c] == 0], key=lambda c: CAT_INDEX[c])
    order, e = [], set(edges)
    while avail:
        n = avail.pop(0)
        order.append(n)
        for edge in [x for x in e if x[0] == n]:
            e.discard(edge)
            indeg[edge[1]] -= 1
            if indeg[edge[1]] == 0:
                avail.append(edge[1])
        avail.sort(key=lambda c: CAT_INDEX[c])

    if len(order) == len(present) and _composite_matches([spr_px[c] for c in order], orig):
        return order

    # Fallback: exhaustive permutation search (rare; few layers in practice).
    for perm in itertools.permutations(present):
        if _composite_matches([spr_px[c] for c in perm], orig):
            return list(perm)
    return None


def main():
    orders = {}
    failed = []
    for tok in range(1, SUPPLY + 1):
        r = solve_token(tok)
        if r is None:
            failed.append(tok)
        else:
            orders[tok] = r
        if tok % 1000 == 0:
            print(f"  ...{tok}", flush=True)

    if failed:
        print(f"FAILED to solve {len(failed)} tokens: {failed[:30]}", file=sys.stderr)
        sys.exit(1)

    with open(OUT, "w") as f:
        json.dump(orders, f)

    uniques = [t for t, v in orders.items() if v == "UNIQUE"]
    distinct = collections.Counter(
        tuple(v) for v in orders.values() if v != "UNIQUE")
    print(f"solved {len(orders)} tokens, {len(uniques)} uniques, 0 failures")
    print(f"distinct render orders: {len(distinct)}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
