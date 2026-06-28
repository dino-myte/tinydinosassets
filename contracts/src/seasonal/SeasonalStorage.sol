// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {SSTORE2} from "../lib/SSTORE2.sol";

/// @notice Immutable on-chain data for one seasonal tiny dinos collection (ids
/// 1..count), rendered genesis-style: composite shared trait sprites + a small
/// per-token correction overlay (for the art's alpha-blended trait edges).
///
/// Blobs (build/seasons/encode_b.py):
///   spriteChunks  RLE trait sprites, chunked (<=24KB)
///   spriteLoc     per global sprite id: (chunkIdx u16-BE, localOff u16-BE)
///   dataChunks    per-token records, chunked: [flag u8]
///                 flag0: [localValIdx u8]*9 ; flag1: [oneIdx u8]
///                 then [numCorr u16-BE] (pixel u8, colorId u16-BE)*numCorr
///   locChunks     per-token (dataChunkIdx u16-BE, localOff u16-BE), locPerChunk/chunk
///   corrPalette   correction colours, RGBA (4B each)
///   cats          9 visual category names ('\n')
///   vals          per-category value lists ('\n' within, 0x1f between categories)
///   one           1/1 values ('\n')
contract SeasonalStorage {
    address public owner;
    bool public frozen;

    address[] public spriteChunks;
    address public spriteLocPtr;
    address[] public dataChunks;
    address[] public locChunks;
    address public corrPalettePtr;
    address public catsPtr;
    address public valsPtr;
    address public onePtr;

    uint256 public count;
    uint256 public locPerChunk;
    uint16[9] public catBase;  // global sprite id base per category (ORDER)
    uint8[9] public alphaIdx;  // category indices in alphabetical (metadata) order

    modifier onlyOwner() { require(msg.sender == owner, "not owner"); _; }
    modifier notFrozen() { require(!frozen, "frozen"); _; }

    constructor() { owner = msg.sender; }

    function addSpriteChunk(bytes calldata d) external onlyOwner notFrozen {
        spriteChunks.push(SSTORE2.write(d));
    }
    function addDataChunk(bytes calldata d) external onlyOwner notFrozen {
        dataChunks.push(SSTORE2.write(d));
    }
    function addLocChunk(bytes calldata d) external onlyOwner notFrozen {
        locChunks.push(SSTORE2.write(d));
    }

    function setBlobs(
        bytes calldata spriteLoc_,
        bytes calldata corrPalette_,
        bytes calldata cats_,
        bytes calldata vals_,
        bytes calldata one_
    ) external onlyOwner notFrozen {
        spriteLocPtr = SSTORE2.write(spriteLoc_);
        corrPalettePtr = SSTORE2.write(corrPalette_);
        catsPtr = SSTORE2.write(cats_);
        valsPtr = SSTORE2.write(vals_);
        onePtr = SSTORE2.write(one_);
    }

    function setMeta(uint256 count_, uint256 locPerChunk_, uint16[9] calldata catBase_, uint8[9] calldata alphaIdx_)
        external onlyOwner notFrozen
    {
        count = count_;
        locPerChunk = locPerChunk_;
        catBase = catBase_;
        alphaIdx = alphaIdx_;
    }

    function seal() external onlyOwner notFrozen {
        frozen = true;
        owner = address(0);
    }

    // ---- reads ----
    function spriteChunk(uint256 i) external view returns (bytes memory) { return SSTORE2.read(spriteChunks[i]); }
    function spriteLoc() external view returns (bytes memory) { return SSTORE2.read(spriteLocPtr); }
    function dataChunk(uint256 i) external view returns (bytes memory) { return SSTORE2.read(dataChunks[i]); }
    function locChunk(uint256 i) external view returns (bytes memory) { return SSTORE2.read(locChunks[i]); }
    function corrPalette() external view returns (bytes memory) { return SSTORE2.read(corrPalettePtr); }
    function cats() external view returns (bytes memory) { return SSTORE2.read(catsPtr); }
    function vals() external view returns (bytes memory) { return SSTORE2.read(valsPtr); }
    function one() external view returns (bytes memory) { return SSTORE2.read(onePtr); }
    function catBaseArr() external view returns (uint16[9] memory) { return catBase; }
    function alphaIdxArr() external view returns (uint8[9] memory) { return alphaIdx; }
    function totalTokens() external view returns (uint256) { return count; }
}
