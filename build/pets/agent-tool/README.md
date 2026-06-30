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
Cloudflare Worker  (same origin as the site, e.g. https://dinomyte.gg)
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

## 5. What it takes (concretely)

1. Decide gate model (token-specific vs any-holder) + CC0 framing (perk vs hard vs tip).
2. A **Base wallet with a little ETH for gas** to `register` onchain (registration is
   the only onchain action; holders pay no gas — they just sign off-chain).
3. Scaffold: `npx @opensea/tool-sdk init tiny-dino-pet` → fill `manifest.ts`
   (see `manifest.ts` sketch) + `handler.ts` (cross-chain gate, see sketches).
4. Reliable **RPC endpoints for all 7 chains** (eth/arb/opt/poly common; avax/bnb/ftm
   need a provider — public RPCs + a fallback list; or a multi-chain provider key).
5. Deploy the Worker same-origin with the manifest; then register on **mainnet** with
   the native gate:
   `PRIVATE_KEY=… npx @opensea/tool-sdk register --metadata https://<origin>/.well-known/ai-tool/tiny-dino-pet.json --network mainnet --nft-gate 0xd9b78a2f1dafc8bb9c60961790d2beefebee56f4`
   (capture the assigned `toolId` → set as `TOOL_ID` for `predicateGate`).
6. Verify: `opensea tools search "tiny dino"`, then the 402 invoke flow end-to-end.

**Effort:** ~1 focused day once a domain + Cloudflare are live; the fiddly part is
robust 7-chain RPC ownership checks (caching + fallbacks).

## 6. Open decisions
- Gate model: **token-specific** (provenance) vs any-holder (convenience)?
- CC0 framing: **holder perk** vs hard-gate vs free-for-holders + tip?
- Output: return **R2 URLs** vs stream the installable zip vs a personalized pet.json?
- Register now (needs a funded Base wallet) or after the site/domain is live?

Sketches in this folder (`manifest.ts`, `handler.ts`, `ownership.ts`) are a runnable
starting point, not deployed.
