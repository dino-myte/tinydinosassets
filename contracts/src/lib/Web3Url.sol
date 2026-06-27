// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

/// @notice Builds the EIP-4804 web3:// baseURI that the live ERC-721's
/// `setBaseURI` is pointed at. With `tokenURI(id) = baseURI + id`, this yields
///   web3://<renderer>:<chainId>/metadataJSON/<id>
/// which resolves to DinoRenderer.metadataJSON(id) (raw JSON, per OpenSea).
library Web3Url {
    function metadataBaseURI(address renderer, uint256 chainId)
        internal
        pure
        returns (string memory)
    {
        return string.concat(
            "web3://", _hexAddr(renderer), ":", _toString(chainId), "/metadataJSON/"
        );
    }

    function _hexAddr(address a) private pure returns (string memory) {
        bytes16 hexsym = "0123456789abcdef";
        bytes20 b = bytes20(a);
        bytes memory out = new bytes(42);
        out[0] = "0";
        out[1] = "x";
        for (uint256 i = 0; i < 20; i++) {
            out[2 + i * 2] = hexsym[uint8(b[i]) >> 4];
            out[3 + i * 2] = hexsym[uint8(b[i]) & 0x0f];
        }
        return string(out);
    }

    function _toString(uint256 v) private pure returns (string memory) {
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
