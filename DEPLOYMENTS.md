# tiny dinos — live ERC-721 contracts (the ones to repoint)

> **Scope note:** this applies to the seasonal collections too. The seasonal
> collections (e.g. `tiny dinos: summer 2022` at
> `0x5a1190759c9e7cf42da401639016f8f60affd465` on Ethereum, 269 minted, sparse
> ids 97–9963, same owner `0xde7f…d666`, same `tokenURI = baseURI + id` shape)
> are **already-live original contracts, exactly like the OG collections**. The
> plan for each is identical: deploy the (Seasonal)Renderer on the collection's
> chain, then the owner repoints the existing contract via `setBaseURI`. The
> Base seasonal deployments under `deployments/` are previews/mimics, not the
> real collections. The seasonal storage encodes all 10,001 ids (a superset of
> the sparse minted set), so the renderer serves every minted id correctly.

The collection is a LayerZero omnichain ERC-721 (`tinydinos`, ticker `DINO`,
Solidity v0.8.11, OpenZeppelin 4.4.1). A token exists on exactly one chain at a
time; its metadata `current-chain` reflects where it currently is. Every contract
exposes:

- `setBaseURI(string) onlyOwner`
- `tokenURI(id)` = `string.concat(baseURI, id)` — **no suffix**, just the id
- shared `owner()` across all chains: `0xde7fce3a1cba4a705f299ce41d163017f165d666`

So the on-chain switch is, per chain (run by the owner):

```
setBaseURI("web3://<RendererAddress>:<chainId>/metadataJSON/")
```

Then `tokenURI(id)` = `web3://<Renderer>:<chainId>/metadataJSON/<id>` resolves to
`DinoRenderer.metadataJSON(id)` (EIP-4804/6860), fully on-chain.

| chain | chainId | contract address | setBaseURI | verified name |
|-------|--------:|------------------|:----------:|---------------|
| eth   | 1       | `0xd9b78a2f1dafc8bb9c60961790d2beefebee56f4` | ✅ | tinydinos |
| avax  | 43114   | `0xaaeef52ad4695b8e3b758215ca6bbca4d7680c62` | ✅ | tinydinos |
| bnb   | 56      | `0xaaeef52ad4695b8e3b758215ca6bbca4d7680c62` | ✅ | tinydinos |
| poly  | 137     | `0xaaeef52ad4695b8e3b758215ca6bbca4d7680c62` | ✅ | tinydinos |
| arb   | 42161   | `0xaaeef52ad4695b8e3b758215ca6bbca4d7680c62` | ✅ | tinydinos |
| ftm   | 250     | `0xaaeef52ad4695b8e3b758215ca6bbca4d7680c62` | ✅ | tinydinos |
| opt   | 10      | `0xaaeef52ad4695b8e3b758215ca6bbca4d7680c62` | ✅ | tinydinos |

ETH has its own address; the other six share `0xaaee…0c62` (LayerZero
same-address deploy — identical bytecode/owner). Sources verified on Etherscan v2
(eth, poly, arb directly; the rest are the same shared bytecode).

Current ETH `tokenURI(1)` (pre-switch):
`ipfs://QmZPSjZKMjDUcqGuy6xS2EDQsJVFLyGHj3LUM2DkmCEfHo/1`

## Return handling — RESOLVED (2026-07-01, tested against the live Base deploys)

`tokenURI(id) = baseURI + id` produces a clean `web3://…/metadataJSON/<id>` URL
(good — no `.json` suffix to fight). The EIP-4804 return-handling question is
settled: use the **plain path, no `?returns`**. Verified through the public
w3link gateway against the live Base contracts:

- plain `…/metadataJSON/<id>` → the gateway returns the **raw JSON string
  bytes** directly (exactly the OpenSea-recommended form). `?returns=(string)`
  is actively worse — it wraps the body as an ABI-decoded JSON array
  (`["{\"name\":…"]`).
- worst-case gas fits with ample headroom: genesis #8891 = 3.96M gas
  (`metadataJSON`, measured via `cast estimate` on Base); summer #4271 = 7.63M.
  Both resolve HTTP 200 in ~0.8s through w3link, JSON parses, embedded SVG
  decodes.
- the gateway serves an empty `content-type` header rather than
  `application/json`, but the live summer collection already indexes and
  renders on OpenSea through this exact URL form, so this is empirically fine.

So the baseURI format at the top of this file is final — no URL change needed
before the 7-chain repoint.
