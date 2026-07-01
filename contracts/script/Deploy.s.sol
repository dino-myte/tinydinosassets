// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {DinoStorage} from "../src/DinoStorage.sol";
import {DinoRenderer} from "../src/DinoRenderer.sol";
import {Web3Url} from "../src/lib/Web3Url.sol";

/// @notice Deploys DinoStorage + DinoRenderer and loads the on-chain blobs.
///
/// Usage (per chain):
///   CHAIN=eth forge script script/Deploy.s.sol \
///     --rpc-url <RPC> --broadcast --private-key <KEY>
///
/// CHAIN must be the folder name of the deployment chain (eth, avax, bnb, poly,
/// arb, ftm, opt) — it becomes the metadata "current-chain" value.
///
/// After deploy, point the live ERC-721's baseURI at the renderer via web3://:
///   setBaseURI("web3://<renderer>:<chainId>/metadataJSON/")
/// so tokenURI(id) = baseURI + id resolves on-chain (EIP-4804/6860).
contract Deploy is Script {
    uint256 internal constant CHUNK = 24000; // multiple of 5

    function run() external {
        bytes memory sprites = vm.readFileBinary("../build/out/sprites.bin");
        bytes memory offsets = vm.readFileBinary("../build/out/spriteOffsets.bin");
        bytes memory tokens = vm.readFileBinary("../build/out/tokens.bin");

        vm.startBroadcast();

        DinoStorage store = new DinoStorage();
        store.setSprites(sprites);
        store.setOffsets(offsets);
        for (uint256 off = 0; off < tokens.length; off += CHUNK) {
            uint256 end = off + CHUNK > tokens.length ? tokens.length : off + CHUNK;
            bytes memory chunk = new bytes(end - off);
            for (uint256 i = 0; i < chunk.length; i++) chunk[i] = tokens[off + i];
            store.addTokenChunk(chunk);
        }
        store.seal();

        DinoRenderer renderer = new DinoRenderer(store);

        vm.stopBroadcast();

        console2.log("chainId       :", block.chainid);
        console2.log("DinoStorage   :", address(store));
        console2.log("DinoRenderer  :", address(renderer));
        console2.log("set baseURI to:", Web3Url.metadataBaseURI(address(renderer), block.chainid));
    }
}
