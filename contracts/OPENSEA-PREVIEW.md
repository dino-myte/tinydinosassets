# Preview the on-chain renderer on OpenSea

Deploy a **mimic** tiny dinos ERC-721 + the on-chain renderer on a cheap chain,
mint all 10,000, point `baseURI` at the renderer via `web3://`, and view the full
collection on OpenSea — rendered 100% on-chain. Nothing here touches the real
collection.

`src/testnet/TestTinyDinos.sol` mimics the live contract where it matters for
OpenSea: name `tiny dinos`, symbol `dino`, ids `1..10000`, `setBaseURI` onlyOwner,
`tokenURI(id) = baseURI + id`. It uses ERC721A so all 10k batch-mint cheaply while
still emitting a `Transfer` per token (so OpenSea indexes every one).

## Pick a chain

| chain | OpenSea | ~cost for the whole preview (≈37.5M gas) | notes |
|---|---|---|---|
| **Sepolia (testnet)** | testnets.opensea.io | **free** (faucet ETH) | best first pass, zero risk |
| **Base** (mainnet L2) | opensea.io | ~$1–2 | cheap, fast, real OpenSea |
| **Polygon** (mainnet) | opensea.io | ~$0.50 (POL) | cheap, real OpenSea |
| Optimism / Arbitrum | opensea.io | ~$1–3 | also fine |

Recommendation: **Sepolia** to validate rendering for free, then **Base or
Polygon** if you want it on the real opensea.io.

## Prerequisites

```bash
# 1. build the on-chain data (once)
python3 build/build.py

# 2. foundry + deps
export PATH="$HOME/.foundry/bin:$PATH"
cd contracts
forge install foundry-rs/forge-std
forge install chiru-labs/ERC721A

# 3. a funded key on the chosen chain + its RPC
export PRIVATE_KEY=0x...              # deployer = collection owner of the mimic
export RPC=https://sepolia.infura.io/v3/<key>   # or Base/Polygon RPC
```

Sepolia faucets: e.g. sepoliafaucet.com / Alchemy / QuickNode. You need ~0.05
test ETH for the ~37.5M gas.

## Deploy + mint all 10,000 (one command)

```bash
CHAIN=eth forge script script/DeployTestCollection.s.sol \
  --rpc-url $RPC --broadcast --private-key $PRIVATE_KEY
```

This single script: deploys `TestTinyDinos` + `DinoStorage` (+ all blobs, sealed)
+ `DinoRenderer`, mints 10,000 to you (5 batches of 2,000), then sets
`baseURI = web3://<renderer>:<chainId>/metadataJSON/`. It prints all three
addresses and `tokenURI(1)`.

> The `web3://` URL embeds `block.chainid`, so the renderer is referenced on the
> same chain you deployed to — no manual chain config.

## Verify on-chain (before OpenSea)

```bash
NFT=<TestTinyDinos>; REND=<DinoRenderer>
cast call $NFT 'totalSupply()(uint256)' --rpc-url $RPC          # 10000
cast call $NFT 'tokenURI(uint256)(string)' 1 --rpc-url $RPC     # web3://…/metadataJSON/1
cast call $REND 'metadataJSON(uint256)(string)' 751 --rpc-url $RPC | head -c 200   # raw JSON
```

Optionally resolve the web3:// URL through a gateway in a browser:
`https://<renderer>.<chainId>.w3link.io/metadataJSON/1` → should return the JSON,
whose `image` is an inline `data:image/svg+xml;base64,…`.

## View on OpenSea

1. Go to the collection: `https://opensea.io/assets/<chain>/<NFT>/1`
   (testnet: `https://testnets.opensea.io/assets/sepolia/<NFT>/1`).
2. If art doesn't show immediately, open a token and **"Refresh metadata"**
   (OpenSea resolves the web3:// URI server-side and caches it). Allow a few
   minutes for indexing after mint.
3. Spot-check:
   - a gradient background (e.g. #1 red conical gradient),
   - a **landscape** token (#751 night landscape — the one the 16↔1600 fix
     corrected),
   - a **1/1** (#101, #2918, #9845),
   - the **traits** panel matches the metadata.

## Cleanup / iterate

It's a throwaway contract — just stop using it, or redeploy. To re-point the
mimic at a different renderer later: `cast send $NFT 'setBaseURI(string)' '<uri>'
--rpc-url $RPC --private-key $PRIVATE_KEY`.

## Notes

- The mimic differs from the live LayerZero ONFT only in the mint path; the
  `tokenURI`/metadata behaviour OpenSea renders from is identical.
- For the **real** switch (no new contract, no minting — just repoint the live
  721's baseURI), see `RUNBOOK.md`.
