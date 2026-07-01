// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {TestNFTDeployer} from "../src/testnet/TestNFTDeployer.sol";
import {TestTinyDinos} from "../src/testnet/TestTinyDinos.sol";

contract TestNFTDeployerTest is Test {
    address internal operator = address(0xB4A2);
    TestNFTDeployer internal helper;
    TestTinyDinos internal nft;

    string internal constant BASE_URI =
        "web3://0xb375319914a50ba59d6f18102f6789b3c0ae9c55:1/metadataJSON/";

    function setUp() public {
        helper = new TestNFTDeployer(operator);
        nft = helper.nft();
        assertEq(nft.owner(), address(helper), "helper owns nft");
    }

    function test_MintAndPoint_endToEnd() public {
        vm.startPrank(operator);
        for (uint256 minted = 0; minted < 10001; minted += 2000) {
            uint256 q = minted + 2000 > 10001 ? 10001 - minted : 2000;
            helper.exec(address(nft), abi.encodeWithSignature("mint(uint256)", q));
        }
        helper.exec(address(nft), abi.encodeWithSignature("setBaseURI(string)", BASE_URI));
        vm.stopPrank();

        assertEq(nft.totalSupply(), 10001, "supply");
        assertEq(nft.ownerOf(1), address(helper));
        assertEq(nft.ownerOf(10001), address(helper));
        assertEq(nft.tokenURI(1), string.concat(BASE_URI, "1"), "tokenURI form");
        assertEq(nft.tokenURI(8891), string.concat(BASE_URI, "8891"));
    }

    function test_Exec_onlyOperator() public {
        vm.expectRevert("not operator");
        helper.exec(address(nft), abi.encodeWithSignature("mint(uint256)", 1));
    }
}
