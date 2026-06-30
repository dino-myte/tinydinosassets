// SKETCH — OPTIONAL FALLBACK. Not used by the primary design.
// Primary path gates via the REGISTRY's native ERC721OwnerPredicate by registering on
// `--network mainnet --nft-gate <ETH collection>` (see README). Keep this only if we
// ever register on Base (where the predicate can't read L1) and must verify in-handler,
// or to add token-specific gating the stock owner-predicate doesn't support.

import { createPublicClient, http, getAddress } from "viem";
import { mainnet } from "viem/chains";

// tiny dinos ERC-721 on Ethereum mainnet (chainId 1).
export const DINOS_ETH = getAddress(
  "0xd9b78a2f1dafc8bb9c60961790d2beefebee56f4",
);

// Use a reliable RPC (set via env). Public fallback shown.
const RPC = process.env.ETH_RPC_URL ?? "https://eth.llamarpc.com";
const client = createPublicClient({ chain: mainnet, transport: http(RPC) });

const ERC721 = [
  { type: "function", name: "balanceOf", stateMutability: "view",
    inputs: [{ name: "owner", type: "address" }], outputs: [{ type: "uint256" }] },
  { type: "function", name: "ownerOf", stateMutability: "view",
    inputs: [{ name: "tokenId", type: "uint256" }], outputs: [{ type: "address" }] },
] as const;

/** Any-holder gate (chosen): does `account` hold >=1 tiny dino on Ethereum? */
export async function holdsAnyDino(account: `0x${string}`): Promise<boolean> {
  const bal = await client.readContract({
    address: DINOS_ETH, abi: ERC721, functionName: "balanceOf", args: [account],
  });
  return bal > 0n;
}

/** Optional token-specific gate: does `account` own this exact dino on Ethereum? */
export async function ownsDino(
  account: `0x${string}`, tokenId: number,
): Promise<boolean> {
  try {
    const owner = await client.readContract({
      address: DINOS_ETH, abi: ERC721, functionName: "ownerOf",
      args: [BigInt(tokenId)],
    });
    return getAddress(owner) === getAddress(account);
  } catch {
    return false; // ownerOf reverts if the token isn't currently on Ethereum
  }
}
