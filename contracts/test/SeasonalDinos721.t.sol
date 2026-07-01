// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {SeasonalDinos721} from "../src/seasonal/SeasonalDinos721.sol";

contract Receiver {
    function onERC721Received(address, address, uint256, bytes calldata)
        external
        pure
        returns (bytes4)
    {
        return this.onERC721Received.selector;
    }
}

contract WrongReceiver {
    function onERC721Received(address, address, uint256, bytes calldata)
        external
        pure
        returns (bytes4)
    {
        return 0xdeadbeef;
    }
}

contract NonReceiver {}

/// @notice ERC-721 safety of the seasonal mimic 721: safe transfers to contracts
/// must be acknowledged via onERC721Received, else revert.
contract SeasonalDinos721Test is Test {
    SeasonalDinos721 internal nft;
    address internal alice = address(0xA11CE);

    function setUp() public {
        nft = new SeasonalDinos721("tiny dinos: test", "dino");
        nft.mintRange(1, 10);
    }

    function test_SafeTransfer_toEOA() public {
        nft.safeTransferFrom(address(this), alice, 1);
        assertEq(nft.ownerOf(1), alice);
    }

    function test_SafeTransfer_toReceiver() public {
        address r = address(new Receiver());
        nft.safeTransferFrom(address(this), r, 2);
        assertEq(nft.ownerOf(2), r);
    }

    function test_SafeTransfer_toNonReceiver_reverts() public {
        address r = address(new NonReceiver());
        vm.expectRevert("unsafe receiver");
        nft.safeTransferFrom(address(this), r, 3);
        assertEq(nft.ownerOf(3), address(this));
    }

    function test_SafeTransfer_wrongMagic_reverts() public {
        address r = address(new WrongReceiver());
        vm.expectRevert("unsafe receiver");
        nft.safeTransferFrom(address(this), r, 4);
    }

    function test_PlainTransfer_toNonReceiver_allowed() public {
        // per spec, unsafe transferFrom does NOT check the receiver
        address r = address(new NonReceiver());
        nft.transferFrom(address(this), r, 5);
        assertEq(nft.ownerOf(5), r);
    }

    function test_SafeTransfer_notAuthorized_reverts() public {
        vm.prank(alice);
        vm.expectRevert("not authorized");
        nft.safeTransferFrom(address(this), alice, 6);
    }
}
