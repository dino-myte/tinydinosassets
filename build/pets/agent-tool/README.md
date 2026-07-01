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

### To go live (one-time, needs a funded **Ethereum mainnet** wallet for gas)

The SDK supports several wallet providers (`privy`, `turnkey`, `fireblocks`, `bankr`,
`private-key`); `createWalletFromEnv()` auto-selects by which env vars are set. The
wallet is used ONLY for `register` / `update-metadata` — the deployed tool's runtime
(`predicateGate`) does read-only calls and needs no wallet.

**Option A — Bankr managed wallet (chosen; no private key on disk).**
`api.bankr.bot`, auth `X-API-Key: $BANKR_API_KEY`, signs/submits via `/wallet/sign`
+ `/wallet/submit`. Setup at `bankr.bot/api-keys`:
1. Create an API key with the **Wallet API** capability enabled.
2. Turn on the **IP allowlist** and add the public IP of the machine that runs
   `register` (this Mac = `108.64.14.41`). Optionally set low wallet spend caps — it
   only needs gas.
3. Get the wallet address (`curl https://api.bankr.bot/wallet/me -H "X-API-Key: $BANKR_API_KEY"`)
   and **fund it with a little ETH on mainnet** for the one registration tx.
```bash
cd build/pets
export BANKR_API_KEY=...           # Wallet-API key (keep out of shared transcripts)
# dry-run first (validates key + IP allowlist + prints plan; no tx):
npx tool-sdk register --metadata https://dinomyte.xyz/.well-known/ai-tool/tiny-dino-pet.json \
  --network mainnet --nft-gate 0xd9b78a2f1dafc8bb9c60961790d2beefebee56f4 --dry-run
# real run (Bankr broadcasts the tx; costs gas) -> prints the toolId:
npx tool-sdk register --metadata https://dinomyte.xyz/.well-known/ai-tool/tiny-dino-pet.json \
  --network mainnet --nft-gate 0xd9b78a2f1dafc8bb9c60961790d2beefebee56f4
```

**Option B — raw private key (fallback).**
```bash
PRIVATE_KEY=0x<key> RPC_URL=https://ethereum-rpc.publicnode.com \
  npx tool-sdk register --metadata https://dinomyte.xyz/.well-known/ai-tool/tiny-dino-pet.json \
  --network mainnet --nft-gate 0xd9b78a2f1dafc8bb9c60961790d2beefebee56f4
```

**After registration (either option):**
```bash
npx wrangler secret put TOOL_ID      # paste the toolId it printed
npx wrangler deploy                  # /api/pet flips 503 -> live 402-gated
npx tool-sdk verify https://dinomyte.xyz/.well-known/ai-tool/tiny-dino-pet.json
```
Gas is the only cost; holders pay nothing (they sign a free zero-value authorization).

**Bankr IP-allowlist caveats:** the allowlisted IP must be the egress IP that reaches
`api.bankr.bot` from wherever `register` runs. Residential IPv4 can change on an ISP
lease renewal; this Mac also has IPv6 (privacy addresses rotate), so force IPv4 when
calling Bankr (or allowlist the `/64` prefix if Bankr accepts CIDR). Bankr Club
(~$20/mo in BNKR) or Max Mode is a prerequisite to use the account.

## 6. Open / optional later
- **Token-specific** gating (own #X to mint #X's pet) — the stock owner-predicate is
  collection-level; would need a custom predicate or in-handler `ownerOf` check.
- **Personalized `pet.json`** (owner address / custom name) templated in the handler.
- **x402 tip** for non-holders (`x402Gate` + `x402UsdcPricing`) if you ever want revenue.

## 7. How agents call the tool (LIVE — tool id 54)

**Discover** it in OpenSea's registry:
```
GET  https://api.opensea.io/api/v2/tools/search?query=tiny+dino          # x-api-key header
GET  https://api.opensea.io/api/v2/tools/1/0x265BB2DBFC0A8165C9A1941Eb1372F349baD2cf1/54
# or the MCP tools (search_tools / get_tool) or:  opensea tools search "tiny dino"
```

**Invoke** it. Gating uses the standard **402 + zero-value EIP-3009** flow (tool-sdk ≥ 0.26):
the caller signs a *free* zero-value authorization proving wallet control, and the gate checks
that wallet holds a tiny dino on Ethereum. Use `eip3009AuthenticatedFetch` — it handles the
402 challenge, signs, and retries automatically:

```ts
import { eip3009AuthenticatedFetch } from "@opensea/tool-sdk";
import { privateKeyToAccount } from "viem/accounts";

const account = privateKeyToAccount(process.env.PRIVATE_KEY); // a dino-holding wallet
// managed wallets work too:  const account = await createBankrAccount(process.env.BANKR_API_KEY);

const res = await eip3009AuthenticatedFetch("https://dinomyte.xyz/api/pet", {
  account,
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ tokenId: 2139 }),
});
// 200 -> { slug, spritesheetUrl, gameSpritesheetUrl, zipUrl, installCmd, ... }  (holder)
// 403 -> "access predicate denied"  (signature valid, but wallet holds no dino)
// 402 -> only if the caller doesn't sign (eip3009AuthenticatedFetch does this for you)
```

The returned `zipUrl` is a ready-to-install petdex pack (`pet.json` + `spritesheet.webp`);
drop it in the pets dir (`~/.codex/pets/` or `~/.hermes/pets/`) — see the `installCmd` field.
Note: **SIWE / `authenticatedFetch` was removed in 0.26** — callers must use the EIP-3009 path
(which is also what makes usage reporting fire).
