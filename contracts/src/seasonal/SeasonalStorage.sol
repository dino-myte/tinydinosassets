// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {SSTORE2} from "../lib/SSTORE2.sol";

/// @notice Immutable on-chain data for one seasonal tiny dinos collection with a
/// contiguous id range 1..count.
///
/// Layout (produced by build/seasons/encode.py):
///   dataChunks  combined per-token records, chunked at token boundaries (<=24KB):
///               [numAttrs u8][catIdx u8, valIdx u16-BE]*n [sprite RLE]
///   locChunks   location index, locPerChunk tokens/chunk, 4 bytes each:
///               (dataChunkIdx u16-BE, localOffset u16-BE)
///   cats / vals '\n'-joined trait_type names / values
/// Token idx = id - 1. Everything is chunked so no blob exceeds the SSTORE2 limit.
contract SeasonalStorage {
    address public owner;
    bool public frozen;

    address[] public dataChunks;
    address[] public locChunks;
    address public catsPtr;
    address public valsPtr;
    uint256 public count;
    uint256 public locPerChunk;

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    modifier notFrozen() {
        require(!frozen, "frozen");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function addDataChunk(bytes calldata d) external onlyOwner notFrozen {
        dataChunks.push(SSTORE2.write(d));
    }

    function addLocChunk(bytes calldata d) external onlyOwner notFrozen {
        locChunks.push(SSTORE2.write(d));
    }

    function setStrings(bytes calldata cats_, bytes calldata vals_) external onlyOwner notFrozen {
        catsPtr = SSTORE2.write(cats_);
        valsPtr = SSTORE2.write(vals_);
    }

    function setMeta(uint256 count_, uint256 locPerChunk_) external onlyOwner notFrozen {
        count = count_;
        locPerChunk = locPerChunk_;
    }

    function seal() external onlyOwner notFrozen {
        frozen = true;
        owner = address(0);
    }

    // ---- reads ----

    function dataChunk(uint256 i) external view returns (bytes memory) {
        return SSTORE2.read(dataChunks[i]);
    }

    function locChunk(uint256 i) external view returns (bytes memory) {
        return SSTORE2.read(locChunks[i]);
    }

    function cats() external view returns (bytes memory) {
        return SSTORE2.read(catsPtr);
    }

    function vals() external view returns (bytes memory) {
        return SSTORE2.read(valsPtr);
    }

    function totalTokens() external view returns (uint256) {
        return count;
    }
}
