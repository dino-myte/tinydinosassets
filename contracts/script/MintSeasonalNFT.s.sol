// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {SeasonalNFT721A} from "../src/seasonal/SeasonalNFT721A.sol";
import {Web3Url} from "../src/lib/Web3Url.sol";

/// @notice Deploy a gas-efficient ERC721A mimic for an already-deployed seasonal
/// renderer, mint the full contiguous set, and point baseURI at the renderer.
///
///   RENDERER=0x.. NAME="tiny dinos: summer 2022" COUNT=10001 \
///   forge script script/MintSeasonalNFT.s.sol --rpc-url <RPC> --broadcast --private-key <KEY> --slow
contract MintSeasonalNFT is Script {
    uint256 internal constant MINT_BATCH = 2000;

    function run() external {
        address renderer = vm.envAddress("RENDERER");
        string memory name = vm.envString("NAME");
        uint256 count = vm.envUint("COUNT");

        vm.startBroadcast();
        SeasonalNFT721A nft = new SeasonalNFT721A(name, "dino");
        for (uint256 minted = 0; minted < count; minted += MINT_BATCH) {
            uint256 q = minted + MINT_BATCH > count ? count - minted : MINT_BATCH;
            nft.mint(q);
        }
        string memory baseURI = Web3Url.metadataBaseURI(renderer, block.chainid);
        nft.setBaseURI(baseURI);
        vm.stopBroadcast();

        console2.log("SeasonalNFT721A:", address(nft));
        console2.log("totalSupply   :", nft.totalSupply());
        console2.log("baseURI       :", baseURI);
        console2.log("tokenURI(1)   :", nft.tokenURI(1));
    }
}
