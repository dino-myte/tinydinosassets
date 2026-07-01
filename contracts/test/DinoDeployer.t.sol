// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {DinoDeployer} from "../src/DinoDeployer.sol";
import {DinoStorage} from "../src/DinoStorage.sol";
import {DinoRenderer} from "../src/DinoRenderer.sol";

/// @notice Replicates the managed-wallet mainnet deploy flow exactly: helper and
/// renderer created through the canonical CREATE2 proxy, blobs loaded through the
/// helper by the operator, then output asserted against the proven fixtures.
contract DinoDeployerTest is Test {
    address internal constant CREATE2_PROXY = 0x4e59b44847b379578588920cA78FbF26c0B4956C;
    // runtime code of the deterministic-deployment-proxy (Arachnid), as on mainnet
    bytes internal constant PROXY_CODE =
        hex"7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffe03601600081602082378035828234f58015156039578182fd5b8082525050506014600cf3";

    uint256 internal constant CHUNK = 24000;
    address internal operator = address(0xB4A2);

    DinoStorage internal store;
    DinoRenderer internal renderer;

    function setUp() public {
        vm.etch(CREATE2_PROXY, PROXY_CODE);

        // tx1: CREATE2 proxy -> DinoDeployer(operator)
        bytes32 salt = keccak256("tinydinos-genesis");
        bytes memory initcode =
            abi.encodePacked(type(DinoDeployer).creationCode, abi.encode(operator));
        (bool ok1, bytes memory ret1) = CREATE2_PROXY.call(abi.encodePacked(salt, initcode));
        require(ok1, "helper create2 failed");
        DinoDeployer helper = DinoDeployer(address(bytes20(ret1)));
        assertEq(helper.operator(), operator, "operator");
        store = helper.store();
        assertEq(store.owner(), address(helper), "helper must own storage");

        // tx2-7: operator loads blobs through the helper, then seals
        vm.startPrank(operator);
        helper.setSprites(vm.readFileBinary("../build/out/sprites.bin"));
        helper.setOffsets(vm.readFileBinary("../build/out/spriteOffsets.bin"));
        bytes memory tokens = vm.readFileBinary("../build/out/tokens.bin");
        for (uint256 off = 0; off < tokens.length; off += CHUNK) {
            uint256 end = off + CHUNK > tokens.length ? tokens.length : off + CHUNK;
            bytes memory c = new bytes(end - off);
            for (uint256 i = 0; i < c.length; i++) c[i] = tokens[off + i];
            helper.addTokenChunk(c);
        }
        helper.seal();
        vm.stopPrank();

        // tx8: CREATE2 proxy -> DinoRenderer(store)
        bytes memory rInit =
            abi.encodePacked(type(DinoRenderer).creationCode, abi.encode(address(store)));
        (bool ok2, bytes memory ret2) = CREATE2_PROXY.call(abi.encodePacked(salt, rInit));
        require(ok2, "renderer create2 failed");
        renderer = DinoRenderer(address(bytes20(ret2)));
    }

    function test_DeployedViaHelper_matchesFixtures() public view {
        assertTrue(store.frozen(), "sealed");
        assertEq(store.owner(), address(0), "ownerless");
        assertEq(store.totalTokens(), 10001, "count");

        string memory j = vm.readFile("./test/fixtures/hashes_eth.json");
        bytes32[] memory svgH = vm.parseJsonBytes32Array(j, ".svgHash");
        bytes32[] memory jsonH = vm.parseJsonBytes32Array(j, ".jsonHash");
        for (uint256 i = 0; i < svgH.length; i += 419) {
            uint256 id = i + 1;
            assertEq(keccak256(bytes(renderer.imageSVG(id))), svgH[i], "svg");
            assertEq(keccak256(bytes(renderer.metadataJSON(id))), jsonH[i], "json");
        }
    }

    function test_Helper_onlyOperator() public {
        bytes32 salt = keccak256("x");
        bytes memory initcode =
            abi.encodePacked(type(DinoDeployer).creationCode, abi.encode(operator));
        (bool ok, bytes memory ret) = CREATE2_PROXY.call(abi.encodePacked(salt, initcode));
        require(ok, "create2");
        DinoDeployer h = DinoDeployer(address(bytes20(ret)));
        vm.expectRevert("not operator");
        h.setSprites(hex"00");
        vm.expectRevert("not operator");
        h.seal();
    }
}
