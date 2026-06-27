# Deployment runbook — repoint tiny dinos to the on-chain renderer

Per chain: deploy `DinoStorage` + `DinoRenderer`, then have the **owner** repoint
the live ERC-721's `baseURI` at it via `web3://`. Nothing about the tokens, supply,
or ownership changes — only where `tokenURI` reads its data from.

## What I need from you to execute

| input | why | notes |
|---|---|---|
| **RPC URLs** for the 7 chains | broadcast txs | set `ETH_RPC_URL`, `AVAX_RPC_URL`, `BNB_RPC_URL`, `POLY_RPC_URL`, `ARB_RPC_URL`, `FTM_RPC_URL`, `OPT_RPC_URL` |
| **Deployer key** (any funded EOA) | deploys Storage+Renderer | ~23M gas/chain (see below). Does **not** need to be the owner |
| **Owner key** `0xde7fce3a…d666` | calls `setBaseURI` | the only address allowed to repoint; one EOA across all chains |
| `ETHERSCAN_API_KEY` (optional) | contract verification | Etherscan v2, one key all chains |

I cannot hold or use those keys — you run the broadcast commands (or hand me a
throwaway funded key for a testnet dry run). Everything else is built and tested.

## Pre-flight (already green)

```bash
python3 build/build.py          # 10k pixel + 70k metadata exact
cd contracts && forge test      # 7/7 incl. all-10k + deploy-flow
```

`forge test` already proves, against the real blobs:
- the renderer reproduces all 10,000 tokens (pixels + metadata),
- repointing `baseURI` makes `tokenURI(id)` resolve to
  `web3://<renderer>:<chainId>/metadataJSON/<id>` (`DeployFlow.t.sol`),
- `metadataJSON` returns raw JSON (OpenSea's recommended web3:// form).

## Per-chain procedure (example: eth)

```bash
export PATH="$HOME/.foundry/bin:$PATH"
cd contracts

# 1) deploy Storage + Renderer (deployer key)
CHAIN=eth forge script script/Deploy.s.sol \
  --rpc-url eth --broadcast --private-key $DEPLOYER_KEY --verify
# -> logs DinoStorage, DinoRenderer, and the exact baseURI to set

# 2) owner repoints the live 721 (owner key)
NFT=0xd9b78a2f1dafc8bb9c60961790d2beefebee56f4 \
RENDERER=<DinoRenderer from step 1> \
forge script script/SetBaseURI.s.sol \
  --rpc-url eth --broadcast --private-key $OWNER_KEY
# -> prints tokenURI(1) before (ipfs://…) and after (web3://…/metadataJSON/1)
```

`CHAIN` and the `NFT` address per chain come from `deployments/live.json`. Chain
names map to `[rpc_endpoints]` in `foundry.toml`.

## Gas / cost

Deploy (Storage with all blobs via SSTORE2 + Renderer): **~22.8M gas / chain**
(measured on anvil). `setBaseURI` is a single small tx. The data is ~58 KB,
split into SSTORE2 chunks ≤24 KB; `DinoStorage.seal()` makes it permanently
immutable. On L2s/sidechains (avax/bnb/poly/arb/ftm/opt) this is a few cents to a
few dollars; eth mainnet is the only pricey one (~23M gas at prevailing gwei).

## Verification (after each chain)

```bash
# tokenURI now points at the renderer
cast call $NFT 'tokenURI(uint256)(string)' 1 --rpc-url eth
# the resolved metadata is valid raw JSON with an inline svg image
cast call $RENDERER 'metadataJSON(uint256)(string)' 1 --rpc-url eth | head -c 200
```

Then resolve the `web3://` URL through a gateway (e.g. `https://<renderer>.<chainId>.w3link.io/metadataJSON/1`)
and trigger an OpenSea metadata refresh on a couple of tokens to confirm the
image + traits render.

## Recommended rollout

1. **Testnet dry run** (Sepolia, or any chain’s testnet) with a throwaway key —
   full Deploy + a mock SetBaseURI — to rehearse end to end.
2. **One cheap mainnet chain first** (e.g. polygon): deploy, repoint, verify on
   OpenSea, eyeball a handful of tokens incl. a snow/night-landscape one and a
   1/1.
3. **Roll out the remaining chains**. `current-chain` is set per deployment, so
   each chain’s renderer is constructed with its own chain name.

## Rollback

`setBaseURI` is re-callable by the owner, so reverting is one tx:

```bash
cast send $NFT 'setBaseURI(string)' \
  'ipfs://QmZPSjZKMjDUcqGuy6xS2EDQsJVFLyGHj3LUM2DkmCEfHo/' \
  --rpc-url eth --private-key $OWNER_KEY
```

(Storage/Renderer are immutable once sealed, but nothing references them until
`baseURI` points back at them.)
