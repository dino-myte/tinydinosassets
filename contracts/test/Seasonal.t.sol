// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {SeasonalStorage} from "../src/seasonal/SeasonalStorage.sol";
import {SeasonalRenderer} from "../src/seasonal/SeasonalRenderer.sol";

/// @notice Differential test for the seasonal renderer (summer). Loads the real
/// blobs, then asserts imageSVG/metadataJSON match the Python fixtures (which are
/// verified to rasterise to the source images + carry the correct traits).
contract SeasonalTest is Test {
    uint256 internal constant CHUNK = 24000;
    string internal constant DESC = "one of 10k tiny dinos ready for summer vibes";

    SeasonalStorage internal store;
    SeasonalRenderer internal renderer;

    function setUp() public {
        string memory base = "../build/seasons/out/summer/";
        bytes memory sprites = vm.readFileBinary(string.concat(base, "sprites.bin"));

        store = new SeasonalStorage();
        for (uint256 off = 0; off < sprites.length; off += CHUNK) {
            uint256 end = off + CHUNK > sprites.length ? sprites.length : off + CHUNK;
            store.addSpriteChunk(_slice(sprites, off, end));
        }
        store.setBlobs(
            vm.readFileBinary(string.concat(base, "spriteOffsets.bin")),
            vm.readFileBinary(string.concat(base, "ids.bin")),
            vm.readFileBinary(string.concat(base, "records.bin")),
            vm.readFileBinary(string.concat(base, "recordOffsets.bin")),
            bytes(vm.readFile(string.concat(base, "cats.txt"))),
            bytes(vm.readFile(string.concat(base, "vals.txt")))
        );
        store.seal();
        renderer = new SeasonalRenderer(store, "tiny dinos: summer 2022", DESC);
    }

    function test_Summer_AllTokens() public view {
        string memory j = vm.readFile("./test/fixtures/seasons/summer.json");
        uint256[] memory ids = vm.parseJsonUintArray(j, ".ids");
        bytes32[] memory svgH = vm.parseJsonBytes32Array(j, ".svgHash");
        bytes32[] memory jsonH = vm.parseJsonBytes32Array(j, ".jsonHash");

        assertEq(store.totalTokens(), ids.length, "count");
        uint256 fmp;
        assembly { fmp := mload(0x40) }
        for (uint256 i = 0; i < ids.length; i++) {
            require(keccak256(bytes(renderer.imageSVG(ids[i]))) == svgH[i], "svg");
            require(keccak256(bytes(renderer.metadataJSON(ids[i]))) == jsonH[i], "json");
            assembly { mstore(0x40, fmp) }
        }
    }

    function _slice(bytes memory d, uint256 s, uint256 e) internal pure returns (bytes memory o) {
        o = new bytes(e - s);
        for (uint256 i = 0; i < o.length; i++) o[i] = d[s + i];
    }
}
