// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {SeasonalStorage} from "./SeasonalStorage.sol";
import {Base64} from "../lib/Base64.sol";

/// @notice Fully on-chain renderer for a seasonal tiny dinos collection (ids
/// 1..count), genesis-style: composite the 9 shared trait sprites in layer order,
/// then overlay a small per-token correction table (the art's alpha-blended edges).
/// metadataJSON(id) returns raw JSON with an inline base64 SVG (web3:// target).
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
        return string.concat("data:application/json;base64,", Base64.encode(bytes(metadataJSON(id))));
    }

    function metadataJSON(uint256 id) public view returns (string memory) {
        (bytes memory data, uint256 off) = _record(id);
        string memory image =
            string.concat("data:image/svg+xml;base64,", Base64.encode(bytes(imageSVG(id))));
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
        uint32[256] memory canvas;

        uint8 flag = uint8(data[off]);
        off += 1;
        if (flag == 0) {
            uint16[9] memory base = store.catBaseArr();
            bytes memory loc = store.spriteLoc();
            for (uint256 c = 0; c < 9; c++) {
                uint256 gid = uint256(base[c]) + uint8(data[off + c]); // valIdx for category c
                uint256 lp = gid * 4;
                uint256 chunkIdx = (uint256(uint8(loc[lp])) << 8) | uint8(loc[lp + 1]);
                uint256 localOff = (uint256(uint8(loc[lp + 2])) << 8) | uint8(loc[lp + 3]);
                _paint(canvas, store.spriteChunk(chunkIdx), localOff);
            }
            off += 9;
        } else {
            off += 1; // oneIdx (no sprite)
        }

        uint256 numCorr = (uint256(uint8(data[off])) << 8) | uint8(data[off + 1]);
        off += 2;
        if (numCorr > 0) {
            bytes memory pal = store.corrPalette();
            for (uint256 i = 0; i < numCorr; i++) {
                uint256 p = uint8(data[off]);
                uint256 cid = (uint256(uint8(data[off + 1])) << 8) | uint8(data[off + 2]);
                off += 3;
                uint256 q = cid * 4;
                canvas[p] = (uint32(uint8(pal[q])) << 24) | (uint32(uint8(pal[q + 1])) << 16)
                    | (uint32(uint8(pal[q + 2])) << 8) | uint32(uint8(pal[q + 3]));
            }
        }

        return _svg(canvas);
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

    // ---- attributes ----

    function _attributes(bytes memory data, uint256 off) internal view returns (string memory out) {
        uint8 flag = uint8(data[off]);
        if (flag == 1) {
            string memory v = _split(store.one(), uint8(data[off + 1]));
            return string.concat('{"trait_type":"1/1","value":"', v, '"}');
        }
        bytes memory cats = store.cats();
        bytes memory vals = store.vals();
        uint8[9] memory a = store.alphaIdxArr();
        for (uint256 k = 0; k < 9; k++) {
            uint256 ci = a[k];
            uint256 vi = uint8(data[off + 1 + ci]); // localValIdx for category ci
            out = string.concat(
                out, k == 0 ? "" : ",",
                '{"trait_type":"', _split(cats, ci), '","value":"', _splitCat(vals, ci, vi), '"}'
            );
        }
    }

    // ---- sprite paint (RLE, source-over for opaque sprites) ----

    function _paint(uint32[256] memory canvas, bytes memory blob, uint256 o) internal pure {
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
            for (uint256 k = 0; k < cnt; k++) {
                if (color & 0xFF != 0) canvas[filled] = color; // paint only opaque pixels
                filled++;
            }
        }
    }

    // ---- SVG ----

    function _svg(uint32[256] memory grid) internal pure returns (string memory) {
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

    // ---- string helpers ----

    function _split(bytes memory blob, uint256 idx) internal pure returns (string memory) {
        return _slice(blob, idx, 0x0a);
    }

    /// @dev category `ci` (split by 0x1f), then value `vi` within it (split by '\n').
    function _splitCat(bytes memory blob, uint256 ci, uint256 vi) internal pure returns (string memory) {
        uint256 start = 0;
        uint256 field = 0;
        uint256 end = blob.length;
        for (uint256 i = 0; i <= blob.length; i++) {
            if (i == blob.length || blob[i] == 0x1f) {
                if (field == ci) { end = i; break; }
                field++;
                start = i + 1;
            }
        }
        // slice [start,end) is the category block; now split by '\n'
        bytes memory block_ = new bytes(end - start);
        for (uint256 j = start; j < end; j++) block_[j - start] = blob[j];
        return _slice(block_, vi, 0x0a);
    }

    function _slice(bytes memory blob, uint256 idx, bytes1 sep) internal pure returns (string memory) {
        uint256 start = 0;
        uint256 field = 0;
        for (uint256 i = 0; i <= blob.length; i++) {
            if (i == blob.length || blob[i] == sep) {
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
            for { let i := 0 } lt(i, len) { i := add(i, 0x20) } { mstore(add(dst, i), mload(add(src, i))) }
        }
        return n + len;
    }
}
