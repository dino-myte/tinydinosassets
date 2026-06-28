// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {SeasonalStorage} from "../src/seasonal/SeasonalStorage.sol";
import {SeasonalRenderer} from "../src/seasonal/SeasonalRenderer.sol";

/// @notice Differential test for the seasonal renderer (summer, ids 1..count),
/// option B: composite shared trait sprites + correction overlay. Loads the real
/// blobs and asserts imageSVG/metadataJSON match the Python fixtures (proven to
/// rasterise to the source images + carry the right traits).
contract SeasonalTest is Test {
    string internal constant DESC = "one of 10k tiny dinos ready for summer vibes";

    SeasonalStorage internal store;
    SeasonalRenderer internal renderer;

    function setUp() public {
        string memory base = "../build/seasons/out_b/summer/";
        string memory mf = vm.readFile(string.concat(base, "manifest.json"));

        store = new SeasonalStorage();
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
        store.setMeta(
            vm.parseJsonUint(mf, ".count"), vm.parseJsonUint(mf, ".locPerChunk"),
            _u16x9(mf, ".catBase"), _u8x9(mf, ".alphaIdx")
        );
        store.seal();
        renderer = new SeasonalRenderer(store, "tiny dinos: summer 2022", DESC);
    }

    function test_Summer_Sample() public view { _check(307); }

    /// Full sweep (heavy): forge test --match-test test_Summer_AllTokens
    function test_Summer_AllTokens() public view { _check(1); }

    function _check(uint256 step) internal view {
        string memory j = vm.readFile("./test/fixtures/seasons/summer.json");
        bytes32[] memory svgH = vm.parseJsonBytes32Array(j, ".svgHash");
        bytes32[] memory jsonH = vm.parseJsonBytes32Array(j, ".jsonHash");
        assertEq(store.totalTokens(), svgH.length, "count");

        uint256 fmp;
        assembly { fmp := mload(0x40) }
        for (uint256 i = 0; i < svgH.length; i += step) {
            uint256 id = i + 1;
            require(keccak256(bytes(renderer.imageSVG(id))) == svgH[i], "svg");
            require(keccak256(bytes(renderer.metadataJSON(id))) == jsonH[i], "json");
            assembly { mstore(0x40, fmp) }
        }
    }

    function _u16x9(string memory mf, string memory key) internal pure returns (uint16[9] memory a) {
        uint256[] memory v = vm.parseJsonUintArray(mf, key);
        for (uint256 i = 0; i < 9; i++) a[i] = uint16(v[i]);
    }
    function _u8x9(string memory mf, string memory key) internal pure returns (uint8[9] memory a) {
        uint256[] memory v = vm.parseJsonUintArray(mf, key);
        for (uint256 i = 0; i < 9; i++) a[i] = uint8(v[i]);
    }
    function _pad4(uint256 v) internal pure returns (string memory) {
        bytes memory s = new bytes(4);
        for (uint256 i = 0; i < 4; i++) { s[3 - i] = bytes1(uint8(48 + (v % 10))); v /= 10; }
        return string(s);
    }
}
