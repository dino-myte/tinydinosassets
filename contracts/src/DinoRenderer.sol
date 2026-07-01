// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {DinoStorage} from "./DinoStorage.sol";
import {DinoData} from "./DinoData.sol";
import {Base64} from "./lib/Base64.sol";

/// @notice Fully on-chain renderer for the tiny dinos collection.
///
/// Reads the immutable data in `DinoStorage`, composites the token's 16x16 trait
/// sprites with the exact PIL source-over integer math, and emits the metadata
/// JSON (with an embedded base64 SVG image). Pixel- and trait-identical to the
/// original IPFS collection — verified off-chain over all 10,000 tokens.
///
/// The deployed ERC-721's `baseURI` is repointed to a web3:// pointer
/// (EIP-4804/6860) at this contract, e.g.
///   web3://<thisAddress>:<chainId>/metadataJSON/<tokenId>
/// so `tokenURI(id)` resolves to `metadataJSON(id)` fully on-chain.
contract DinoRenderer {
    DinoStorage public immutable store;

    string internal constant DESC =
        "one of 10k cc0 tiny dinos minted out across 7 different chains";

    bytes16 internal constant HEX = "0123456789abcdef";

    struct Rec {
        bool unique;
        uint256 minton;
        // composite tokens:
        uint256[9] locals; // by VIS category index
        uint256 order;
        // unique tokens:
        uint256 uimg;
        uint256 one;
    }

    /// @dev Chain-independent: the only chain shown in metadata is the static
    /// "minted on" attribute (per-token), so one renderer serves all chains.
    constructor(DinoStorage _store) {
        store = _store;
    }

    // ---------------------------------------------------------------- public

    function tokenURI(uint256 tokenId) external view returns (string memory) {
        return string.concat(
            "data:application/json;base64,",
            Base64.encode(bytes(metadataJSON(tokenId)))
        );
    }

    function metadataJSON(uint256 tokenId) public view returns (string memory) {
        Rec memory r = _decode(tokenId);
        string memory image = string.concat(
            "data:image/svg+xml;base64,", Base64.encode(bytes(imageSVG(tokenId)))
        );
        return string.concat(
            '{"name":"tiny dinos #', _utoa(tokenId),
            '","description":"', DESC,
            '","tokenId":', _utoa(tokenId),
            ',"attributes":[', _attributes(r),
            '],"image":"', image, '"}'
        );
    }

    /// @notice Raw 16x16 RGBA pixels (1024 bytes, row-major) of a single stored
    /// sprite. globalSpriteId in [0, N_COMPOSITE) are trait sprites (category
    /// order from DinoData.catBase); [N_COMPOSITE, N_COMPOSITE+N_UNIQUE) are the
    /// unique images. Lets traits be verified directly against the source PNGs.
    function traitRGBA(uint256 globalSpriteId) external view returns (bytes memory out) {
        bytes memory sprites = store.sprites();
        bytes memory offs = store.offsets();
        uint32[256] memory px = _sprite(sprites, _spriteOffset(offs, globalSpriteId));
        out = new bytes(1024);
        for (uint256 i = 0; i < 256; i++) {
            uint32 c = px[i];
            out[i * 4] = bytes1(uint8(c >> 24));
            out[i * 4 + 1] = bytes1(uint8(c >> 16));
            out[i * 4 + 2] = bytes1(uint8(c >> 8));
            out[i * 4 + 3] = bytes1(uint8(c));
        }
    }

    function imageSVG(uint256 tokenId) public view returns (string memory) {
        uint32[256] memory grid = _composite(tokenId);
        bytes memory buf = new bytes(24000);
        uint256 n = _append(
            buf, 0,
            bytes(
                "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' shape-rendering='crispEdges'>"
            )
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
        assembly {
            mstore(buf, n)
        }
        return string(buf);
    }

    // ------------------------------------------------------------- internals

    function _decode(uint256 tokenId) internal view returns (Rec memory r) {
        bytes memory rec = store.tokenRecord(tokenId);
        uint256 word;
        for (uint256 i = 0; i < 5; i++) {
            word |= uint256(uint8(rec[i])) << (8 * i);
        }
        r.unique = ((word >> 39) & 1) == 1;
        r.minton = (word >> 36) & 0x7;
        if (r.unique) {
            r.uimg = word & 0x1F;
            r.one = (word >> 5) & 0x1F;
        } else {
            uint8[9] memory w = DinoData.widths();
            uint256 shift = 0;
            for (uint256 i = 0; i < 9; i++) {
                r.locals[i] = (word >> shift) & ((uint256(1) << w[i]) - 1);
                shift += w[i];
            }
            r.order = (word >> 33) & 0x7;
        }
    }

    function _composite(uint256 tokenId) internal view returns (uint32[256] memory canvas) {
        Rec memory r = _decode(tokenId);
        bytes memory sprites = store.sprites();
        bytes memory offs = store.offsets();

        uint16[9] memory base = DinoData.catBase();
        uint256[9] memory gids;
        uint256 nLayers;

        if (r.unique) {
            gids[0] = DinoData.N_COMPOSITE + r.uimg;
            nLayers = 1;
        } else {
            uint8[9] memory ord = DinoData.order(r.order);
            for (uint256 k = 0; k < 9; k++) {
                uint256 cat = ord[k];
                gids[k] = uint256(base[cat]) + r.locals[cat];
            }
            nLayers = 9;
        }

        for (uint256 k = 0; k < nLayers; k++) {
            uint32[256] memory px = _sprite(sprites, _spriteOffset(offs, gids[k]));
            for (uint256 i = 0; i < 256; i++) {
                uint32 s = px[i];
                if ((s & 0xFF) != 0) {
                    canvas[i] = _blend(canvas[i], s);
                }
            }
        }
    }

    function _spriteOffset(bytes memory offs, uint256 idx) internal pure returns (uint256) {
        uint256 p = idx * 4;
        return (uint256(uint8(offs[p])) << 24) | (uint256(uint8(offs[p + 1])) << 16)
            | (uint256(uint8(offs[p + 2])) << 8) | uint256(uint8(offs[p + 3]));
    }

    /// @dev Decode one RLE sprite at `o` in the sprites blob into 256 packed pixels.
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
            for (uint256 k = 0; k < count; k++) {
                px[filled++] = color;
            }
        }
    }

    /// @dev Source-over compositing matching Pillow's AlphaComposite (PRECISION_BITS=7),
    /// bit-for-bit. Verified against PIL over 500k random pairs.
    function _blend(uint32 dst, uint32 src) internal pure returns (uint32) {
        uint256 sa = src & 0xFF;
        if (sa == 0) return dst;
        if (sa == 255) return src;
        uint256 da = dst & 0xFF;

        uint256 blend_ = da * (255 - sa);
        uint256 outa255 = sa * 255 + blend_;
        uint256 coef1 = (sa * 255 * 255 * 128) / outa255;
        uint256 coef2 = 255 * 128 - coef1;

        uint256 r = _ch((src >> 24) & 0xFF, (dst >> 24) & 0xFF, coef1, coef2);
        uint256 g = _ch((src >> 16) & 0xFF, (dst >> 16) & 0xFF, coef1, coef2);
        uint256 b = _ch((src >> 8) & 0xFF, (dst >> 8) & 0xFF, coef1, coef2);
        uint256 oa = _div255(outa255 + 128);

        return uint32((r << 24) | (g << 16) | (b << 8) | oa);
    }

    function _ch(uint256 sc, uint256 dc, uint256 coef1, uint256 coef2)
        private
        pure
        returns (uint256)
    {
        uint256 tmp = sc * coef1 + dc * coef2;
        return _div255(tmp + 16384) >> 7; // 16384 = 0x80 << 7
    }

    function _div255(uint256 a) private pure returns (uint256) {
        return (((a >> 8) + a) >> 8);
    }

    // ---- metadata attributes ----

    function _attributes(Rec memory r) internal pure returns (string memory) {
        if (r.unique) {
            return string.concat(
                '{"trait_type":"1/1","value":"', DinoData.oneOfOne(r.one),
                '"},{"trait_type":"minted on","value":"', DinoData.mintedOn(r.minton), '"}'
            );
        }
        uint8[9] memory a = DinoData.attrOrderIdx();
        string memory out = "";
        for (uint256 k = 0; k < 9; k++) {
            uint256 cat = a[k];
            out = string.concat(
                out,
                '{"trait_type":"', DinoData.traitType(cat),
                '","value":"', DinoData.catValue(cat, r.locals[cat]), '"},'
            );
        }
        return string.concat(
            out, '{"trait_type":"minted on","value":"', DinoData.mintedOn(r.minton), '"}'
        );
    }

    // ---- string / buffer helpers ----

    function _rect(uint256 x, uint256 y, uint256 w, uint32 c) internal pure returns (bytes memory) {
        uint256 a = c & 0xFF;
        bytes memory fill = a == 255
            ? abi.encodePacked("#", _hex2((c >> 24) & 0xFF), _hex2((c >> 16) & 0xFF), _hex2((c >> 8) & 0xFF))
            : abi.encodePacked("#", _hex2((c >> 24) & 0xFF), _hex2((c >> 16) & 0xFF), _hex2((c >> 8) & 0xFF), _hex2(a));
        return abi.encodePacked(
            "<rect x='", _utoa(x), "' y='", _utoa(y), "' width='", _utoa(w),
            "' height='1' fill='", fill, "'/>"
        );
    }

    function _hex2(uint256 b) internal pure returns (bytes memory) {
        return abi.encodePacked(HEX[(b >> 4) & 0xF], HEX[b & 0xF]);
    }

    function _utoa(uint256 v) internal pure returns (string memory) {
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

    /// @dev Copy `data` into `buf` at position `n` (word-wise). `buf` must have
    /// capacity >= n + data.length + 31. Returns new length.
    function _append(bytes memory buf, uint256 n, bytes memory data)
        private
        pure
        returns (uint256)
    {
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
