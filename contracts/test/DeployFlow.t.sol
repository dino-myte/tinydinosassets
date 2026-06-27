// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {DinoStorage} from "../src/DinoStorage.sol";
import {DinoRenderer} from "../src/DinoRenderer.sol";
import {Web3Url} from "../src/lib/Web3Url.sol";
import {MockTinyDinos} from "./mocks/MockTinyDinos.sol";

/// @notice End-to-end proof of the on-chain switch, with a mock of the live
/// `tinydinos` ERC-721: deploy Storage + Renderer, load the real blobs, repoint
/// the 721's baseURI to the web3:// pointer, and assert the resulting
/// tokenURI(id) resolves to web3://<renderer>:<chainId>/metadataJSON/<id> and
/// that metadataJSON(id) is raw JSON (the OpenSea-recommended form).
contract DeployFlowTest is Test {
    uint256 internal constant CHUNK = 24000;
    uint256 internal constant CHAIN_ID = 1; // eth deployment in this proof

    DinoStorage internal store;
    DinoRenderer internal renderer;
    MockTinyDinos internal nft;

    function setUp() public {
        // 1. existing collection (owner-controlled, IPFS baseURI today)
        nft = new MockTinyDinos();
        nft.setBaseURI("ipfs://QmZPSjZKMjDUcqGuy6xS2EDQsJVFLyGHj3LUM2DkmCEfHo/");

        // 2. deploy the on-chain data + renderer
        store = new DinoStorage();
        store.setSprites(vm.readFileBinary("../build/out/sprites.bin"));
        store.setOffsets(vm.readFileBinary("../build/out/spriteOffsets.bin"));
        bytes memory tokens = vm.readFileBinary("../build/out/tokens.bin");
        for (uint256 off = 0; off < tokens.length; off += CHUNK) {
            uint256 end = off + CHUNK > tokens.length ? tokens.length : off + CHUNK;
            store.addTokenChunk(_slice(tokens, off, end));
        }
        store.seal();
        renderer = new DinoRenderer(store, "eth");
    }

    function test_RepointBaseURI_resolvesToRenderer() public {
        // 3. the owner switches baseURI to the web3:// pointer
        string memory baseURI = Web3Url.metadataBaseURI(address(renderer), CHAIN_ID);
        nft.setBaseURI(baseURI);

        // tokenURI(id) on the live contract now yields the web3:// URL
        for (uint256 i = 0; i < 3; i++) {
            uint256 id = [uint256(1), 751, 10000][i];
            string memory expected =
                string.concat(baseURI, vm.toString(id)); // web3://<r>:1/metadataJSON/<id>
            assertEq(nft.tokenURI(id), expected, "tokenURI != web3:// pointer");
        }
    }

    function test_MetadataJSON_isRawJson() public view {
        // 4. what the web3:// URL resolves to: raw JSON (not a data: URI)
        string memory j = renderer.metadataJSON(1);
        bytes memory b = bytes(j);
        assertEq(b[0], bytes1("{"), "metadataJSON must start with '{' (raw JSON)");
        assertEq(b[b.length - 1], bytes1("}"), "metadataJSON must end with '}'");
        assertTrue(_contains(j, '"name":"tiny dinos #1"'), "missing name");
        assertTrue(_contains(j, '"image":"data:image/svg+xml;base64,'), "image not inline svg");
        // must NOT be the discouraged data:application/json wrapper
        assertTrue(!_contains(j, "data:application/json"), "should not wrap JSON in a data URI");
    }

    function test_baseURI_format() public view {
        string memory baseURI = Web3Url.metadataBaseURI(address(renderer), CHAIN_ID);
        assertTrue(_contains(baseURI, "web3://"), "missing scheme");
        assertTrue(_contains(baseURI, ":1/metadataJSON/"), "missing chainId/path");
    }

    // ---- helpers ----
    function _slice(bytes memory d, uint256 s, uint256 e) internal pure returns (bytes memory o) {
        o = new bytes(e - s);
        for (uint256 i = 0; i < o.length; i++) o[i] = d[s + i];
    }

    function _contains(string memory hay, string memory needle) internal pure returns (bool) {
        bytes memory h = bytes(hay);
        bytes memory n = bytes(needle);
        if (n.length > h.length) return false;
        for (uint256 i = 0; i <= h.length - n.length; i++) {
            bool ok = true;
            for (uint256 j = 0; j < n.length; j++) {
                if (h[i + j] != n[j]) {
                    ok = false;
                    break;
                }
            }
            if (ok) return true;
        }
        return false;
    }
}
