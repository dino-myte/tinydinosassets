// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {TestTinyDinos} from "../src/testnet/TestTinyDinos.sol";
import {DinoStorage} from "../src/DinoStorage.sol";
import {DinoRenderer} from "../src/DinoRenderer.sol";
import {Web3Url} from "../src/lib/Web3Url.sol";

/// @notice One-shot testnet preview: deploy a mimic ERC-721 + the on-chain
/// renderer, mint all 10,000 tokens, and point the 721 at the renderer via
/// web3://. After this runs, the collection is fully visible on OpenSea for the
/// deployed chain, rendered entirely on-chain.
///
///   CHAIN=eth forge script script/DeployTestCollection.s.sol \
///     --rpc-url <RPC> --broadcast --private-key <KEY>
///
/// CHAIN sets the metadata "current-chain" value (cosmetic for a preview).
contract DeployTestCollection is Script {
    uint256 internal constant CHUNK = 24000;     // token-blob chunk bytes (<=24KB)
    uint256 internal constant MINT_BATCH = 2000; // tokens per mint tx
    uint256 internal constant SUPPLY = 10001;    // 1..10000 + the bonus 1/1 "bug" (#10001)

    function run() external {
        bytes memory sprites = vm.readFileBinary("../build/out/sprites.bin");
        bytes memory offsets = vm.readFileBinary("../build/out/spriteOffsets.bin");
        bytes memory tokens = vm.readFileBinary("../build/out/tokens.bin");

        vm.startBroadcast();

        // 1. the mimic ERC-721 (name "tiny dinos", symbol "dino", ids start at 1)
        TestTinyDinos nft = new TestTinyDinos();

        // 2. on-chain data + renderer
        DinoStorage store = new DinoStorage();
        store.setSprites(sprites);
        store.setOffsets(offsets);
        for (uint256 off = 0; off < tokens.length; off += CHUNK) {
            uint256 end = off + CHUNK > tokens.length ? tokens.length : off + CHUNK;
            store.addTokenChunk(_slice(tokens, off, end));
        }
        store.seal();
        DinoRenderer renderer = new DinoRenderer(store);

        // 3. mint all 10,000 (batched) to the deployer
        for (uint256 minted = 0; minted < SUPPLY; minted += MINT_BATCH) {
            uint256 q = minted + MINT_BATCH > SUPPLY ? SUPPLY - minted : MINT_BATCH;
            nft.mint(q);
        }

        // 4. repoint baseURI at the renderer (web3://, raw JSON)
        string memory baseURI = Web3Url.metadataBaseURI(address(renderer), block.chainid);
        nft.setBaseURI(baseURI);

        vm.stopBroadcast();

        console2.log("chainId       :", block.chainid);
        console2.log("TestTinyDinos :", address(nft));
        console2.log("DinoStorage   :", address(store));
        console2.log("DinoRenderer  :", address(renderer));
        console2.log("totalSupply   :", nft.totalSupply());
        console2.log("baseURI       :", baseURI);
        console2.log("tokenURI(1)   :", nft.tokenURI(1));
    }

    function _slice(bytes memory d, uint256 s, uint256 e) internal pure returns (bytes memory o) {
        o = new bytes(e - s);
        for (uint256 i = 0; i < o.length; i++) o[i] = d[s + i];
    }
}
