// SKETCH — the tool endpoint handler (POST /api/pet). Not deployed.
// Gating is enforced by the REGISTRY: we register on mainnet with --nft-gate <ETH
// collection>, and `predicateGate` delegates the 402 check to the onchain
// ToolRegistry (ERC721OwnerPredicate on Ethereum). So by the time our handler runs,
// the caller is already a verified holder — we just return the pack. Assets live on
// the same R2 origin as the static site. Verify SDK API names against @opensea/tool-sdk.

import { createToolHandler, predicateGate } from "@opensea/tool-sdk";
import { z } from "zod";
import { manifest, ASSETS } from "./manifest";

const inputSchema = z.object({ tokenId: z.number().int().min(1).max(10001) });
const outputSchema = z.object({
  slug: z.string(), petJsonUrl: z.string(), spritesheetUrl: z.string(),
  gameSpritesheetUrl: z.string(), zipUrl: z.string(), installCmd: z.string(),
});

// Registry-enforced gate. toolId is assigned at `register`; rpcUrl reads mainnet so
// the SDK can run the 402 challenge + ERC721OwnerPredicate check before our handler.
const gate = predicateGate({
  toolId: BigInt(process.env.TOOL_ID ?? "0"),
  rpcUrl: process.env.ETH_RPC_URL ?? "https://eth.llamarpc.com",
});

export const handler = createToolHandler({
  manifest,
  inputSchema,
  outputSchema,
  gates: [gate],
  handler: async (input, _ctx) => {
    const id = input.tokenId;
    const slug = `tiny-dino-${id}`;
    const base = `${ASSETS}/${slug}`;
    return {
      slug,
      petJsonUrl: `${base}/pet.json`,
      spritesheetUrl: `${base}/spritesheet.webp`,
      gameSpritesheetUrl: `${base}/spritesheet_game.webp`,
      zipUrl: `${base}/pet.zip`,
      installCmd: `curl -L ${base}/pet.zip -o ${slug}.zip && unzip ${slug}.zip -d ~/.codex/pets/`,
    };
  },
});
