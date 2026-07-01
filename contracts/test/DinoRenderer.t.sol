// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {DinoStorage} from "../src/DinoStorage.sol";
import {DinoRenderer} from "../src/DinoRenderer.sol";

/// @notice Differential test: the Solidity renderer must reproduce, byte-for-byte,
/// the output of the Python reference renderer — which is itself proven pixel- and
/// metadata-exact against the original 10,000-token collection (build/reference_render.py).
/// So passing here transitively proves the on-chain renderer is exact.
contract DinoRendererTest is Test {
    DinoStorage internal store;
    DinoRenderer internal renderer; // "eth" deployment

    uint256 internal constant CHUNK = 24000; // bytes per token chunk (multiple of 5)

    function setUp() public {
        store = new DinoStorage();

        bytes memory sprites = vm.readFileBinary("../build/out/sprites.bin");
        bytes memory offsets = vm.readFileBinary("../build/out/spriteOffsets.bin");
        bytes memory tokens = vm.readFileBinary("../build/out/tokens.bin");

        store.setSprites(sprites);
        store.setOffsets(offsets);
        for (uint256 off = 0; off < tokens.length; off += CHUNK) {
            uint256 end = off + CHUNK > tokens.length ? tokens.length : off + CHUNK;
            store.addTokenChunk(_slice(tokens, off, end));
        }
        store.seal();

        renderer = new DinoRenderer(store);

        assertEq(store.totalTokens(), 10001, "token count");
    }

    /// Full-collection coverage via keccak hashes (heavy). Run explicitly:
    ///   forge test --match-test test_AllTokens -vv
    function test_AllTokens() public view {
        string memory j = vm.readFile("./test/fixtures/hashes_eth.json");
        bytes32[] memory svgH = vm.parseJsonBytes32Array(j, ".svgHash");
        bytes32[] memory jsonH = vm.parseJsonBytes32Array(j, ".jsonHash");
        bytes32[] memory uriH = vm.parseJsonBytes32Array(j, ".uriHash");

        // Snapshot the free-memory pointer AFTER the arrays are allocated, then
        // reset to it each iteration. Each token's strings are discarded, so this
        // keeps memory flat instead of growing quadratically over 10,000 tokens.
        uint256 fmp;
        assembly {
            fmp := mload(0x40)
        }
        for (uint256 i = 0; i < svgH.length; i++) {
            uint256 id = i + 1;
            require(keccak256(bytes(renderer.imageSVG(id))) == svgH[i], "svg");
            require(keccak256(bytes(renderer.metadataJSON(id))) == jsonH[i], "json");
            require(keccak256(bytes(renderer.tokenURI(id))) == uriH[i], "uri");
            assembly {
                mstore(0x40, fmp)
            }
        }
    }

    /// Fast default check: a representative sample with full-string assertions
    /// (covers all 5 render orders, all 15 uniques, and alpha/day-landscape tokens).
    function test_Sample() public view {
        string memory j = vm.readFile("./test/fixtures/sample.json");
        uint256[] memory ids = vm.parseJsonUintArray(j, ".ids");
        string[] memory svg = vm.parseJsonStringArray(j, ".svg");
        string[] memory json = vm.parseJsonStringArray(j, ".json");
        string[] memory uri = vm.parseJsonStringArray(j, ".uri");

        for (uint256 i = 0; i < ids.length; i++) {
            uint256 id = ids[i];
            assertEq(renderer.imageSVG(id), svg[i], _msg("svg", id));
            assertEq(renderer.metadataJSON(id), json[i], _msg("json", id));
            assertEq(renderer.tokenURI(id), uri[i], _msg("uri", id));
        }
    }

    /// Every stored trait sprite (105 trait images + 15 unique flattened dinos)
    /// must decode on-chain to exactly the source PNG (keccak of 1024-byte RGBA).
    function test_Traits() public view {
        string memory j = vm.readFile("./test/fixtures/traits.json");
        uint256[] memory gids = vm.parseJsonUintArray(j, ".gids");
        bytes32[] memory h = vm.parseJsonBytes32Array(j, ".rgbaHash");
        for (uint256 i = 0; i < gids.length; i++) {
            assertEq(keccak256(renderer.traitRGBA(gids[i])), h[i], _msg("trait", gids[i]));
        }
    }

    // ---- helpers ----

    function _slice(bytes memory data, uint256 start, uint256 end)
        internal
        pure
        returns (bytes memory out)
    {
        out = new bytes(end - start);
        for (uint256 i = 0; i < out.length; i++) {
            out[i] = data[start + i];
        }
    }

    function _msg(string memory kind, uint256 id) internal pure returns (string memory) {
        return string.concat(kind, " mismatch token ", vm.toString(id));
    }
}
