// SKETCH — OpenSea Agent Tool (ERC-8257) manifest for the tiny-dino pet generator.
// Starting point, not deployed. Verify field names against @opensea/tool-sdk.
//
//   npx @opensea/tool-sdk init tiny-dino-pet
// then adapt this. Manifest is served at /.well-known/ai-tool/tiny-dino-pet.json
// on the SAME origin as `endpoint` (apex domain, e.g. https://dinomyte.gg).

import { defineManifest } from "@opensea/tool-sdk";

export const ORIGIN = "https://dinomyte.gg"; // TODO: your apex domain
export const ASSETS = `${ORIGIN}/pets`;       // R2 public assets base

export const manifest = defineManifest({
  type: "https://ercs.ethereum.org/ERCS/erc-8257#tool-manifest-v1",
  name: "tiny-dino-pet",
  description:
    "Turn your tiny dino (CC0 NFT) into an animated Hermes/petdex desktop pet. " +
    "Returns a ready-to-install sprite-sheet pack. Gated to holders of the tiny " +
    "dinos Ethereum collection.",
  endpoint: `${ORIGIN}/api/pet`,
  inputs: {
    type: "object",
    properties: {
      tokenId: { type: "integer", minimum: 1, maximum: 10001,
                 description: "tiny dino token id (1-10001)" },
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
  image: `${ASSETS}/../branding/icon-512.png`,        // TODO 1:1 icon
  featuredImage: `${ASSETS}/../branding/banner-16x9.png`, // TODO 16:9 banner
  tags: ["nft", "image", "ai"],
  creatorAddress: "0xde7fce3a1cba4a705f299ce41d163017f165d666", // dinos owner
});
