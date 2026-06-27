// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

/// @notice Minimal stand-in for the live `tinydinos` ERC-721, reproducing the
/// exact baseURI/tokenURI behaviour we verified on-chain:
///   setBaseURI(string) onlyOwner
///   tokenURI(id) = bytes(baseURI).length > 0 ? string.concat(baseURI, id) : ""
/// (the live contract uses `abi.encodePacked(baseURI, tokenId.toString())`).
contract MockTinyDinos {
    address public owner;
    string public baseURI;

    constructor() {
        owner = msg.sender;
    }

    function setBaseURI(string calldata uri) external {
        require(msg.sender == owner, "not owner");
        baseURI = uri;
    }

    function tokenURI(uint256 tokenId) external view returns (string memory) {
        if (bytes(baseURI).length == 0) return "";
        return string.concat(baseURI, _toString(tokenId));
    }

    function _toString(uint256 v) internal pure returns (string memory) {
        if (v == 0) return "0";
        uint256 d;
        uint256 t = v;
        while (t != 0) {
            d++;
            t /= 10;
        }
        bytes memory s = new bytes(d);
        while (v != 0) {
            s[--d] = bytes1(uint8(48 + (v % 10)));
            v /= 10;
        }
        return string(s);
    }
}
