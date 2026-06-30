// OpenSea Agent Tool (ERC-8257) for the tiny-dino pet generator — built on the
// real @opensea/tool-sdk (no reinventing). Gating is registry-enforced: we register
// on Ethereum mainnet (chain 1, where the ToolRegistry + ERC721OwnerPredicate live)
// with --nft-gate on the ETH tiny dinos collection, so the predicate reads ownership
// directly. predicateGate runs the 402 challenge + registry staticcall before our
// handler; the handler then just returns the (CC0) pet pack URLs from our R2 origin.
import { defineManifest, createWellKnownHandler, predicateGate, deriveSlug } from "@opensea/tool-sdk";
import { toCloudflareHandler } from "@opensea/tool-sdk/cloudflare";
import { mainnet } from "viem/chains";
import { z } from "zod";

const ORIGIN = "https://dinomyte.xyz";
// tiny dinos ERC-721 on Ethereum mainnet (the gated collection — see DEPLOYMENTS.md).
export const DINOS_ETH = "0xd9b78a2f1dafc8bb9c60961790d2beefebee56f4";

export const manifest = defineManifest({
  name: "tiny-dino-pet",
  description:
    "Turn your tiny dino (CC0 NFT) into an animated Hermes / petdex desktop pet. " +
    "Returns a ready-to-install sprite-sheet pack (idle, run, jump, wave + more). " +
    "Gated to holders of the tiny dinos Ethereum collection.",
  endpoint: `${ORIGIN}/api/pet`,
  inputs: {
    type: "object",
    properties: {
      tokenId: {
        type: "integer", minimum: 1, maximum: 10001,
        description: "tiny dino token id (1–10001)",
      },
    },
    required: ["tokenId"],
  },
  outputs: {
    type: "object",
    properties: {
      slug: { type: "string" },
      petJsonUrl: { type: "string" },
      spritesheetUrl: { type: "string" },
      gameSpritesheetUrl: { type: "string" },
      zipUrl: { type: "string" },
      installCmd: { type: "string" },
    },
  },
  image: `${ORIGIN}/icon-512.png`,
  featuredImage: `${ORIGIN}/banner-16x9.png`,
  tags: ["nft", "image", "ai"],
  creatorAddress: "0xde7fce3a1cba4a705f299ce41d163017f165d666", // dinos owner
});

export const SLUG = deriveSlug(manifest.name); // "tiny-dino-pet"

const inputSchema = z.object({ tokenId: z.number().int().min(1).max(10001) });
const outputSchema = z.object({
  slug: z.string(), petJsonUrl: z.string(), spritesheetUrl: z.string(),
  gameSpritesheetUrl: z.string(), zipUrl: z.string(), installCmd: z.string(),
});

interface ToolEnv { TOOL_ID?: string; ETH_RPC_URL?: string }

export function toolRegistered(env: ToolEnv): boolean {
  return !!env.TOOL_ID && env.TOOL_ID !== "0";
}

// GET /.well-known/ai-tool/tiny-dino-pet.json — static manifest, no gating.
const wellKnown = createWellKnownHandler(manifest);
export function handleWellKnown(req: Request): Response {
  return wellKnown(req);
}

// POST /api/pet — registry-gated invocation (predicateGate enforces ETH ownership).
export function handleInvoke(
  req: Request, env: ToolEnv, ctx: { waitUntil?: (p: Promise<unknown>) => void },
): Promise<Response> {
  if (!toolRegistered(env)) {
    return Promise.resolve(Response.json(
      { error: "tool_not_registered", hint: "set TOOL_ID after `tool-sdk register`" },
      { status: 503 },
    ));
  }
  const gate = predicateGate({
    toolId: BigInt(env.TOOL_ID as string),
    chain: mainnet,
    rpcUrl: env.ETH_RPC_URL, // undefined -> SDK uses mainnet public RPC
  });
  const tool = toCloudflareHandler({
    manifest, inputSchema, outputSchema, gates: [gate],
    handler: async (input) => {
      const slug = `tiny-dino-${input.tokenId}`;
      const base = `${ORIGIN}/pets/${slug}`;
      return {
        slug,
        petJsonUrl: `${base}/pet.json`,
        spritesheetUrl: `${base}/spritesheet.webp`,
        gameSpritesheetUrl: `${base}/spritesheet_game.webp`,
        zipUrl: `${base}/pet.zip`,
        installCmd:
          `curl -L ${base}/pet.zip -o ${slug}.zip && unzip ${slug}.zip -d ~/.codex/pets/`,
      };
    },
  });
  return tool.fetch(req, env as Record<string, string | undefined>, ctx);
}
