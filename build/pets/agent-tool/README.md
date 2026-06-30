# tiny dinos as an OpenSea Agent Tool (ERC-8257), gated by holding a dino

Feasibility + plan for listing the pet generator in OpenSea's **Agent Tool Registry**
(ERC-8257) so any AI agent can discover & call "turn my tiny dino into a Hermes pet",
gated to dino holders.

## 1. What the registry is (ERC-8257)

A **permissionless onchain registry on Base** for AI-agent tools. A tool =
**one focused REST endpoint** + a JCS-canonical **manifest** served at
`/.well-known/ai-tool/<slug>.json` on the **same origin** as the endpoint
(subdomains don't count — mismatch ⇒ deregistration).

- Build/register with `@opensea/tool-sdk` (TypeScript/Node): `init` → `deploy`
  (Vercel / Cloudflare Workers / Express) → `register --network base`.
- Manifest fields: `type`, `name`, `description`, `endpoint`, `inputs`/`outputs`
  (JSON Schema), `image` (1:1), `featuredImage` (16:9), `tags`, `creatorAddress`.
- Discovery: REST `GET /api/v2/tools`, `/search`, `/{chain}/{registry}/{tool_id}`;
  an MCP server (`search_tools`/`get_tool`/`get_wallet_tools`); and `opensea tools …` CLI.
- Access control via `IAccessPredicate.hasAccess(toolId, account, data)` — supports
  ERC-721/1155 ownership, trait gating, subscriptions, pay-per-call (x402 USDC).
- Auth/invocation = **x402 402-challenge**: caller POSTs with no auth → server
  returns `402` `PaymentRequirements`; for a free/gated tool the caller signs a
  **zero-value** EIP-3009 `TransferWithAuthorization` (USDC domain on Base) and
  retries with `X-Payment`; server `ecrecover`s the **caller wallet address** and
  runs the predicate. (Paid tools set a USDC amount; facilitator settles only after
  access passes.)

## 2. Gating: native nft-gate on Ethereum mainnet (DECISION — locked)

**Register the tool on `--network mainnet` and gate with the native predicate on the
Ethereum tiny dinos collection** `0xd9b78a2f1dafc8bb9c60961790d2beefebee56f4` (chainId 1):

```
npx @opensea/tool-sdk register \
  --metadata https://<origin>/.well-known/ai-tool/tiny-dino-pet.json \
  --network mainnet \
  --nft-gate 0xd9b78a2f1dafc8bb9c60961790d2beefebee56f4
```

The registry supports both Base (default) and **mainnet**. Registering on mainnet puts
the canonical `ERC721OwnerPredicate` **on Ethereum, co-located with our collection**, so
it reads ownership **directly** — no custom handler check, no RPC plumbing. The registry
enforces gating *before* our endpoint is invoked, and we get its collection enrichment
(name / image / floor price).

(Earlier draft gated in-handler because it assumed the tool had to live on Base, where a
predicate can't read L1. Registering on mainnet removes that constraint — so
`ownership.ts` is now an **optional fallback**, not the primary path.)

- **Any-holder (chosen):** the `ERC721OwnerPredicate` grants iff `balanceOf(caller) > 0`.
- **Token-specific (optional):** would need a custom predicate keyed on `tokenId` (the
  stock owner-predicate is collection-level), or the in-handler `ownsDino()` fallback.

Tradeoffs to confirm: (a) **mainnet registration costs L1 gas** (one-time; Base is cheaper
but can't read the ETH collection); (b) verify the **registry is deployed on mainnet** and
note the address; (c) the free x402 zero-value challenge uses the **mainnet USDC** EIP-3009
domain (signature only — no settlement, no gas for callers).

Omnichain note: dinos are omnichain (eth/avax/bnb/poly/arb/ftm/opt; a token lives on one
chain at a time). Gating on the ETH contract recognizes holders whose token is **currently
on Ethereum**; bridged-away tokens won't pass until back on ETH. Accepted.

## 3. The CC0 question (decide this first)

tiny dinos are **CC0**, and so are these derived pets — and every pet is **also
public on R2** (the static site) and regenerable by anyone. So **hard-gating the
art is leaky and off-ethos.** Better framings:

- **Holder perk / official channel (recommended):** the registry-listed tool is the
  *authenticated, official* way to mint *your* dino as a Hermes pet — it proves the
  invoker owns the dino and stamps provenance. The free CC0 generator stays public.
- **Holder-only extras:** ownership unlocks a personalized `pet.json` (custom name,
  "owned by 0x…"), exclusive animation variants, or an on-chain "claimed" record.
- **Soft gate + optional tip:** free for holders (zero-value), non-holders pay a tiny
  x402 USDC fee — funds a treasury, keeps CC0 spirit.

Recommendation: gate the **tool/action** (provenance + agent-ecosystem discovery),
not the bytes.

## 4. Architecture (reuses everything we built)

```
agent (Hermes/Claude/etc.)
   │  ERC-8257 discovery + x402 invoke
   ▼
Cloudflare Worker  (same origin as the site, e.g. https://dinomyte.xyz)
   ├─ GET /.well-known/ai-tool/tiny-dino-pet.json   (manifest)
   └─ POST /api/pet                                  (the tool endpoint)
        - predicateGate runs the registry's 402 challenge + native
          ERC721OwnerPredicate on Ethereum (registered --network mainnet
          --nft-gate <ETH collection>). Caller is a verified holder by the
          time our code runs.
        - handler just returns the pet (assets live on the same R2 origin):
            { slug, petJsonUrl, spritesheetUrl, gameSpritesheetUrl, zipUrl }
```

- **Same-origin** requirement is satisfied by serving the manifest *and* `/api/pet`
  from the one Worker on the apex domain. (Don't split site→`www`, api→`api`.)
- Rendering is already done — the Worker just **verifies ownership and returns the
  R2 URLs** (or streams the zip from R2). No Python at runtime. (For a personalized
  pet.json we'd template it in the Worker.)
- This ties straight into the chosen **Cloudflare R2 + Pages/Workers** hosting.

## 5. Status — IMPLEMENTED & LIVE (registration pending)

Built on the real **`@opensea/tool-sdk` v0.25** (no reinventing). Implementation lives in
`build/pets/src/tool.ts` and is wired into the Worker (`src/worker.ts`):
- `defineManifest` + `createWellKnownHandler` → serves the manifest at
  **`https://dinomyte.xyz/.well-known/ai-tool/tiny-dino-pet.json`** (live, `tool-sdk verify`
  passes; hash `0x0429…95d9`).
- `predicateGate` + `toCloudflareHandler` → **`POST /api/pet`** (registry-enforced gate).
  Needs `compatibility_flags = ["nodejs_compat"]` (SDK uses viem/keccak). Bundle is
  ~234 KiB gzip — **fits the Workers free plan**.
- `image`/`featuredImage` = `/icon-512.png` + `/banner-16x9.png` (mfer-dino brand art, live).
- Until `TOOL_ID` is set, `/api/pet` returns `503 tool_not_registered` (graceful).

**Registry facts (verified on-chain):** `ToolRegistry` + `ERC721OwnerPredicate` are deployed
on chains `[1, 8453, 360, 2741]` — including **Ethereum mainnet (1)** at
`0x265B…2cf1` / `0xc872…8379`. So registering `--network mainnet` co-locates the predicate
with the ETH dinos collection and reads ownership directly.

### To go live (needs a funded **Ethereum mainnet** wallet for gas — one-time):
```bash
cd build/pets
# 1. register on mainnet, gate by the ETH dinos collection -> prints the toolId
PRIVATE_KEY=0x<owner-key> RPC_URL=https://ethereum-rpc.publicnode.com \
  npx tool-sdk register \
  --metadata https://dinomyte.xyz/.well-known/ai-tool/tiny-dino-pet.json \
  --network mainnet \
  --nft-gate 0xd9b78a2f1dafc8bb9c60961790d2beefebee56f4
# 2. wire the assigned id into the Worker, then redeploy
npx wrangler secret put TOOL_ID      # paste the toolId
npx wrangler deploy
# 3. confirm discovery + the 402 gate flow
npx tool-sdk verify https://dinomyte.xyz/.well-known/ai-tool/tiny-dino-pet.json
```
(`--dry-run` on `register` prints the plan without transacting. Gas is the only cost;
holders pay nothing — they sign a free zero-value authorization.)

## 6. Open / optional later
- **Token-specific** gating (own #X to mint #X's pet) — the stock owner-predicate is
  collection-level; would need a custom predicate or in-handler `ownerOf` check.
- **Personalized `pet.json`** (owner address / custom name) templated in the handler.
- **x402 tip** for non-holders (`x402Gate` + `x402UsdcPricing`) if you ever want revenue.
