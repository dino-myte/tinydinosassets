// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {SeasonalStorage} from "../src/seasonal/SeasonalStorage.sol";
import {SeasonalRenderer} from "../src/seasonal/SeasonalRenderer.sol";
import {SeasonalDinos721} from "../src/seasonal/SeasonalDinos721.sol";
import {Web3Url} from "../src/lib/Web3Url.sol";

/// @notice Deploy one seasonal collection (ids 1..count): storage + renderer +
/// mimic 721, mint the contiguous id range, point baseURI at the renderer.
///
///   SEASON=summer forge script script/DeploySeasonal.s.sol \
///     --rpc-url <RPC> --broadcast --private-key <KEY> --slow
contract DeploySeasonal is Script {
    uint256 internal constant MINT_BATCH = 2000;

    function run() external {
        string memory season = vm.envString("SEASON");
        string memory disp = _displayName(season);
        string memory desc = _description(season);
        string memory base = string.concat("../build/seasons/out_b/", season, "/");
        string memory mf = vm.readFile(string.concat(base, "manifest.json"));

        uint256 count = vm.parseJsonUint(mf, ".count");

        vm.startBroadcast();
        SeasonalStorage store = new SeasonalStorage();

        for (uint256 i = 0; i < vm.parseJsonUint(mf, ".nSpriteChunks"); i++) {
            store.addSpriteChunk(vm.readFileBinary(string.concat(base, "sprites/", _pad4(i), ".bin")));
        }
        for (uint256 i = 0; i < vm.parseJsonUint(mf, ".nDataChunks"); i++) {
            store.addDataChunk(vm.readFileBinary(string.concat(base, "data/", _pad4(i), ".bin")));
        }
        for (uint256 i = 0; i < vm.parseJsonUint(mf, ".nLocChunks"); i++) {
            store.addLocChunk(vm.readFileBinary(string.concat(base, "loc/", _pad4(i), ".bin")));
        }
        store.setBlobs(
            vm.readFileBinary(string.concat(base, "spriteLoc.bin")),
            vm.readFileBinary(string.concat(base, "corrPalette.bin")),
            bytes(vm.readFile(string.concat(base, "cats.txt"))),
            bytes(vm.readFile(string.concat(base, "vals.txt"))),
            bytes(vm.readFile(string.concat(base, "one.txt")))
        );
        store.setMeta(count, vm.parseJsonUint(mf, ".locPerChunk"), _u16x9(mf, ".catBase"), _u8x9(mf, ".alphaIdx"));
        store.seal();

        SeasonalRenderer renderer = new SeasonalRenderer(store, disp, desc);

        SeasonalDinos721 nft = new SeasonalDinos721(disp, "dino");
        for (uint256 from = 1; from <= count; from += MINT_BATCH) {
            uint256 qty = from + MINT_BATCH > count + 1 ? count + 1 - from : MINT_BATCH;
            nft.mintRange(from, qty);
        }
        string memory baseURI = Web3Url.metadataBaseURI(address(renderer), block.chainid);
        nft.setBaseURI(baseURI);
        vm.stopBroadcast();

        console2.log("season        :", season);
        console2.log("SeasonalStorage :", address(store));
        console2.log("SeasonalRenderer:", address(renderer));
        console2.log("SeasonalDinos721:", address(nft));
        console2.log("count         :", count);
        console2.log("baseURI       :", baseURI);
        console2.log("tokenURI(1)   :", nft.tokenURI(1));
    }

    function _u16x9(string memory mf, string memory key) internal pure returns (uint16[9] memory a) {
        uint256[] memory v = vm.parseJsonUintArray(mf, key);
        for (uint256 i = 0; i < 9; i++) a[i] = uint16(v[i]);
    }

    function _u8x9(string memory mf, string memory key) internal pure returns (uint8[9] memory a) {
        uint256[] memory v = vm.parseJsonUintArray(mf, key);
        for (uint256 i = 0; i < 9; i++) a[i] = uint8(v[i]);
    }

    function _displayName(string memory s) internal pure returns (string memory) {
        bytes32 h = keccak256(bytes(s));
        if (h == keccak256("summer")) return "tiny dinos: summer 2022";
        if (h == keccak256("winter")) return "tiny dinos: winter 2022";
        if (h == keccak256("halloween")) return "tiny dinos: halloween 2022";
        revert("unknown season");
    }

    function _description(string memory s) internal pure returns (string memory) {
        bytes32 h = keccak256(bytes(s));
        if (h == keccak256("summer")) return "one of 10k tiny dinos ready for summer vibes";
        if (h == keccak256("winter")) return "one of 10k tiny dinos ready for winter vibes";
        if (h == keccak256("halloween")) return "one of 10k tiny dinos ready for halloween vibes";
        revert("unknown season");
    }

    function _pad4(uint256 v) internal pure returns (string memory) {
        bytes memory s = new bytes(4);
        for (uint256 i = 0; i < 4; i++) { s[3 - i] = bytes1(uint8(48 + (v % 10))); v /= 10; }
        return string(s);
    }
}
