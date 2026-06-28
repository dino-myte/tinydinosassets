// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {SeasonalStorage} from "./SeasonalStorage.sol";
import {Base64} from "../lib/Base64.sol";

/// @notice Fully on-chain renderer for a seasonal tiny dinos collection (ids
/// 1..count). Each token is one stored 16x16 sprite + its attributes, packed in a
/// combined record. metadataJSON(id) returns raw JSON with an inline base64 SVG
/// image (the web3:// target). Reads only the one ~24KB chunk holding the token.
contract SeasonalRenderer {
    SeasonalStorage public immutable store;
    uint256 public immutable count;
    uint256 public immutable locPerChunk;
    string public name;
    string public description;

    bytes16 internal constant HEX = "0123456789abcdef";

    constructor(SeasonalStorage _store, string memory _name, string memory _desc) {
        store = _store;
        count = _store.count();
        locPerChunk = _store.locPerChunk();
        name = _name;
        description = _desc;
    }

    function tokenURI(uint256 id) external view returns (string memory) {
        return string.concat(
            "data:application/json;base64,", Base64.encode(bytes(metadataJSON(id)))
        );
    }

    function metadataJSON(uint256 id) public view returns (string memory) {
        (bytes memory data, uint256 off) = _record(id);
        string memory image = string.concat(
            "data:image/svg+xml;base64,", Base64.encode(bytes(imageSVG(id)))
        );
        return string.concat(
            '{"name":"', name, " #", _utoa(id),
            '","description":"', description,
            '","tokenId":', _utoa(id),
            ',"attributes":[', _attributes(data, off),
            '],"image":"', image, '"}'
        );
    }

    function imageSVG(uint256 id) public view returns (string memory) {
        (bytes memory data, uint256 off) = _record(id);
        uint256 n = uint8(data[off]); // skip attrs to reach the sprite
        uint32[256] memory grid = _sprite(data, off + 1 + 3 * n);

        bytes memory buf = new bytes(24000);
        uint256 m = _append(
            buf, 0,
            bytes("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' shape-rendering='crispEdges'>")
        );
        for (uint256 y = 0; y < 16; y++) {
            uint256 x = 0;
            while (x < 16) {
                uint32 c = grid[y * 16 + x];
                uint256 x2 = x;
                while (x2 < 16 && grid[y * 16 + x2] == c) x2++;
                m = _append(buf, m, _rect(x, y, x2 - x, c));
                x = x2;
            }
        }
        m = _append(buf, m, bytes("</svg>"));
        assembly { mstore(buf, m) }
        return string(buf);
    }

    // ---- record lookup ----

    function _record(uint256 id) internal view returns (bytes memory data, uint256 off) {
        require(id >= 1 && id <= count, "unknown token");
        uint256 idx = id - 1;
        bytes memory loc = store.locChunk(idx / locPerChunk);
        uint256 p = (idx % locPerChunk) * 4;
        uint256 chunkIdx = (uint256(uint8(loc[p])) << 8) | uint8(loc[p + 1]);
        off = (uint256(uint8(loc[p + 2])) << 8) | uint8(loc[p + 3]);
        data = store.dataChunk(chunkIdx);
    }

    function _attributes(bytes memory data, uint256 off) internal view returns (string memory out) {
        bytes memory cats = store.cats();
        bytes memory vals = store.vals();
        uint256 num = uint8(data[off]);
        uint256 o = off + 1;
        for (uint256 i = 0; i < num; i++) {
            uint256 ci = uint8(data[o]);
            uint256 vi = (uint256(uint8(data[o + 1])) << 8) | uint8(data[o + 2]);
            o += 3;
            out = string.concat(
                out, i == 0 ? "" : ",",
                '{"trait_type":"', _split(cats, ci), '","value":"', _split(vals, vi), '"}'
            );
        }
    }

    // ---- sprite decode (RLE) ----

    function _sprite(bytes memory blob, uint256 o) internal pure returns (uint32[256] memory px) {
        uint256 plen = uint8(blob[o]);
        if (plen == 0) plen = 256;
        o++;
        uint32[] memory pal = new uint32[](plen);
        for (uint256 i = 0; i < plen; i++) {
            pal[i] = (uint32(uint8(blob[o])) << 24) | (uint32(uint8(blob[o + 1])) << 16)
                | (uint32(uint8(blob[o + 2])) << 8) | uint32(uint8(blob[o + 3]));
            o += 4;
        }
        uint256 filled = 0;
        while (filled < 256) {
            uint256 cnt = uint8(blob[o]);
            uint32 color = pal[uint8(blob[o + 1])];
            o += 2;
            for (uint256 k = 0; k < cnt; k++) px[filled++] = color;
        }
    }

    // ---- string helpers ----

    function _split(bytes memory blob, uint256 idx) internal pure returns (string memory) {
        uint256 start = 0;
        uint256 field = 0;
        for (uint256 i = 0; i <= blob.length; i++) {
            if (i == blob.length || blob[i] == 0x0a) {
                if (field == idx) {
                    bytes memory out = new bytes(i - start);
                    for (uint256 j = start; j < i; j++) out[j - start] = blob[j];
                    return string(out);
                }
                field++;
                start = i + 1;
            }
        }
        revert("idx");
    }

    function _rect(uint256 x, uint256 y, uint256 w, uint32 c) internal pure returns (bytes memory) {
        uint256 a = c & 0xFF;
        bytes memory fill = a == 255
            ? abi.encodePacked("#", _h2((c >> 24) & 0xFF), _h2((c >> 16) & 0xFF), _h2((c >> 8) & 0xFF))
            : abi.encodePacked("#", _h2((c >> 24) & 0xFF), _h2((c >> 16) & 0xFF), _h2((c >> 8) & 0xFF), _h2(a));
        return abi.encodePacked(
            "<rect x='", _utoa(x), "' y='", _utoa(y), "' width='", _utoa(w),
            "' height='1' fill='", fill, "'/>"
        );
    }

    function _h2(uint256 b) internal pure returns (bytes memory) {
        return abi.encodePacked(HEX[(b >> 4) & 0xF], HEX[b & 0xF]);
    }

    function _utoa(uint256 v) internal pure returns (string memory) {
        if (v == 0) return "0";
        uint256 d;
        uint256 t = v;
        while (t != 0) { d++; t /= 10; }
        bytes memory s = new bytes(d);
        while (v != 0) { s[--d] = bytes1(uint8(48 + (v % 10))); v /= 10; }
        return string(s);
    }

    function _append(bytes memory buf, uint256 n, bytes memory data) private pure returns (uint256) {
        uint256 len = data.length;
        assembly {
            let dst := add(add(buf, 0x20), n)
            let src := add(data, 0x20)
            for { let i := 0 } lt(i, len) { i := add(i, 0x20) } {
                mstore(add(dst, i), mload(add(src, i)))
            }
        }
        return n + len;
    }
}
