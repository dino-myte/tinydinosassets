// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {SSTORE2} from "../lib/SSTORE2.sol";

/// @notice Immutable on-chain data for one seasonal tiny dinos collection.
///
/// Blobs (produced by build/seasons/encode.py):
///   sprites      concatenated RLE sprites, one per token (chunked, <=24KB each)
///   offsets      uint32-BE (N+1) offsets into the concatenated sprites
///   ids          uint16-BE (N) real token ids, ascending (for lookup)
///   records      per token: numAttrs(u8) then (catIdx u8, valIdx u16-BE) pairs
///   recOffsets   uint32-BE (N+1) offsets into records
///   cats / vals  '\n'-joined trait_type names / values
contract SeasonalStorage {
    address public owner;
    bool public frozen;

    address[] public spriteChunks;
    address public offsetsPtr;
    address public idsPtr;
    address public recordsPtr;
    address public recOffsetsPtr;
    address public catsPtr;
    address public valsPtr;

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

    function addSpriteChunk(bytes calldata data) external onlyOwner notFrozen {
        spriteChunks.push(SSTORE2.write(data));
    }

    function setBlobs(
        bytes calldata offsets_,
        bytes calldata ids_,
        bytes calldata records_,
        bytes calldata recOffsets_,
        bytes calldata cats_,
        bytes calldata vals_
    ) external onlyOwner notFrozen {
        offsetsPtr = SSTORE2.write(offsets_);
        idsPtr = SSTORE2.write(ids_);
        recordsPtr = SSTORE2.write(records_);
        recOffsetsPtr = SSTORE2.write(recOffsets_);
        catsPtr = SSTORE2.write(cats_);
        valsPtr = SSTORE2.write(vals_);
    }

    function seal() external onlyOwner notFrozen {
        frozen = true;
        owner = address(0);
    }

    // ---- reads ----

    function sprites() external view returns (bytes memory out) {
        uint256 n = spriteChunks.length;
        for (uint256 i = 0; i < n; i++) {
            out = bytes.concat(out, SSTORE2.read(spriteChunks[i]));
        }
    }

    function offsets() external view returns (bytes memory) {
        return SSTORE2.read(offsetsPtr);
    }

    function ids() external view returns (bytes memory) {
        return SSTORE2.read(idsPtr);
    }

    function records() external view returns (bytes memory) {
        return SSTORE2.read(recordsPtr);
    }

    function recOffsets() external view returns (bytes memory) {
        return SSTORE2.read(recOffsetsPtr);
    }

    function cats() external view returns (bytes memory) {
        return SSTORE2.read(catsPtr);
    }

    function vals() external view returns (bytes memory) {
        return SSTORE2.read(valsPtr);
    }

    function totalTokens() external view returns (uint256) {
        return SSTORE2.read(idsPtr).length / 2;
    }
}
