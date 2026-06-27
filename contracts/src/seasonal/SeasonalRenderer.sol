// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {SeasonalStorage} from "./SeasonalStorage.sol";
import {Base64} from "../lib/Base64.sol";

/// @notice Fully on-chain renderer for a seasonal tiny dinos collection.
/// Each token is one stored 16x16 sprite (no compositing). metadataJSON(id)
/// returns raw JSON with an inline base64 SVG image (web3:// target).
contract SeasonalRenderer {
    SeasonalStorage public immutable store;
    string public name;        // e.g. "tiny dinos: summer 2022"
    string public description;

    bytes16 internal constant HEX = "0123456789abcdef";

    constructor(SeasonalStorage _store, string memory _name, string memory _desc) {
        store = _store;
        name = _name;
        description = _desc;
    }

    function tokenURI(uint256 id) external view returns (string memory) {
        return string.concat(
            "data:application/json;base64,", Base64.encode(bytes(metadataJSON(id)))
        );
    }

    function metadataJSON(uint256 id) public view returns (string memory) {
        uint256 idx = _idxOf(id);
        string memory image = string.concat(
            "data:image/svg+xml;base64,", Base64.encode(bytes(imageSVG(id)))
        );
        return string.concat(
            '{"name":"', name, " #", _utoa(id),
            '","description":"', description,
            '","tokenId":', _utoa(id),
            ',"attributes":[', _attributes(idx),
            '],"image":"', image, '"}'
        );
    }

    function imageSVG(uint256 id) public view returns (string memory) {
        uint256 idx = _idxOf(id);
        uint32[256] memory grid = _sprite(store.sprites(), _spriteOffset(store.offsets(), idx));
        bytes memory buf = new bytes(24000);
        uint256 n = _append(
            buf, 0,
            bytes("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' shape-rendering='crispEdges'>")
        );
        for (uint256 y = 0; y < 16; y++) {
            uint256 x = 0;
            while (x < 16) {
                uint32 c = grid[y * 16 + x];
                uint256 x2 = x;
                while (x2 < 16 && grid[y * 16 + x2] == c) x2++;
                n = _append(buf, n, _rect(x, y, x2 - x, c));
                x = x2;
            }
        }
        n = _append(buf, n, bytes("</svg>"));
        assembly { mstore(buf, n) }
        return string(buf);
    }

    // ---- lookup ----

    function _idxOf(uint256 id) internal view returns (uint256) {
        bytes memory ids = store.ids();
        uint256 n = ids.length / 2;
        uint256 lo = 0;
        uint256 hi = n;
        while (lo < hi) {
            uint256 mid = (lo + hi) / 2;
            uint256 v = (uint256(uint8(ids[mid * 2])) << 8) | uint8(ids[mid * 2 + 1]);
            if (v == id) return mid;
            if (v < id) lo = mid + 1;
            else hi = mid;
        }
        revert("unknown token");
    }

    // ---- attributes ----

    function _attributes(uint256 idx) internal view returns (string memory out) {
        bytes memory rec = store.records();
        bytes memory recOff = store.recOffsets();
        bytes memory cats = store.cats();
        bytes memory vals = store.vals();
        uint256 o = _u32(recOff, idx);
        uint256 num = uint8(rec[o]);
        o += 1;
        for (uint256 i = 0; i < num; i++) {
            uint256 ci = uint8(rec[o]);
            uint256 vi = (uint256(uint8(rec[o + 1])) << 8) | uint8(rec[o + 2]);
            o += 3;
            out = string.concat(
                out, i == 0 ? "" : ",",
                '{"trait_type":"', _split(cats, ci), '","value":"', _split(vals, vi), '"}'
            );
        }
    }

    // ---- sprite decode (RLE) ----

    function _spriteOffset(bytes memory offs, uint256 idx) internal pure returns (uint256) {
        return _u32(offs, idx);
    }

    function _u32(bytes memory b, uint256 i) internal pure returns (uint256) {
        uint256 p = i * 4;
        return (uint256(uint8(b[p])) << 24) | (uint256(uint8(b[p + 1])) << 16)
            | (uint256(uint8(b[p + 2])) << 8) | uint256(uint8(b[p + 3]));
    }

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
            uint256 count = uint8(blob[o]);
            uint32 color = pal[uint8(blob[o + 1])];
            o += 2;
            for (uint256 k = 0; k < count; k++) px[filled++] = color;
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
