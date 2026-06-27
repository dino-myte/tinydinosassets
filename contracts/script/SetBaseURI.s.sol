// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {Web3Url} from "../src/lib/Web3Url.sol";

interface ITinyDinos {
    function owner() external view returns (address);
    function setBaseURI(string calldata uri) external;
    function tokenURI(uint256 tokenId) external view returns (string memory);
}

/// @notice Owner-only: repoint a live tiny dinos ERC-721 at the deployed renderer.
///
/// Run with the OWNER key (0xde7fce3a1cba4a705f299ce41d163017f165d666) once the
/// renderer is deployed on that chain:
///   NFT=<live721> RENDERER=<deployedRenderer> \
///   forge script script/SetBaseURI.s.sol --rpc-url <RPC> --broadcast --private-key <OWNER_KEY>
///
/// Sets baseURI = web3://<renderer>:<chainId>/metadataJSON/ so that
/// tokenURI(id) resolves to DinoRenderer.metadataJSON(id) (raw JSON).
contract SetBaseURI is Script {
    function run() external {
        ITinyDinos nft = ITinyDinos(vm.envAddress("NFT"));
        address renderer = vm.envAddress("RENDERER");
        string memory baseURI = Web3Url.metadataBaseURI(renderer, block.chainid);

        console2.log("chainId   :", block.chainid);
        console2.log("nft       :", address(nft));
        console2.log("owner     :", nft.owner());
        console2.log("new baseURI:", baseURI);
        console2.log("before    :", nft.tokenURI(1));

        vm.startBroadcast();
        nft.setBaseURI(baseURI);
        vm.stopBroadcast();

        console2.log("after     :", nft.tokenURI(1));
    }
}
