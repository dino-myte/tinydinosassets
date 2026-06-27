# tiny dinos — live ERC-721 contracts (the ones to repoint)

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

## Open detail before deploy

`tokenURI(id) = baseURI + id` produces a clean `web3://…/metadataJSON/<id>` URL
(good — no `.json` suffix to fight). The remaining thing to pin down is the exact
EIP-4804 return handling so the resolved body is served as `application/json`
(manual-mode `?returns` vs. an EIP-5219-style resource response). The renderer
already returns the JSON string from `metadataJSON(id)`; this is a URL-format
decision, not a data/rendering one.
