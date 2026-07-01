// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {SSTORE2} from "./lib/SSTORE2.sol";

/// @notice Immutable on-chain data store for the tiny dinos renderer.
///
/// Holds three blobs produced by build/extract.py, each written via SSTORE2:
///   * sprites  — concatenated RLE trait sprites + 15 unique flattened images
///   * offsets  — (nSprites+1) uint32-BE start offsets into `sprites`
///   * tokens   — 10000 packed 5-byte token records (chunked, <=24KB each)
///
/// The owner loads the blobs once at deploy time, then renounces by calling
/// `seal()`. After sealing the data can never change, so the collection's art
/// and traits are permanently fixed on-chain.
contract DinoStorage {
    address public owner;
    bool public frozen;

    address public spritesPtr;
    address public offsetsPtr;
    address[] public tokenPtrs;
    uint256[] public tokenCumRecords; // cumulative record count per chunk

    uint256 public constant RECORD_BYTES = 5;

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

    function setSprites(bytes calldata data) external onlyOwner notFrozen {
        spritesPtr = SSTORE2.write(data);
    }

    function setOffsets(bytes calldata data) external onlyOwner notFrozen {
        offsetsPtr = SSTORE2.write(data);
    }

    /// @dev Append a chunk of token records. `data.length` must be a multiple of 5.
    function addTokenChunk(bytes calldata data) external onlyOwner notFrozen {
        require(data.length % RECORD_BYTES == 0, "ragged chunk");
        address ptr = SSTORE2.write(data);
        uint256 prev = tokenCumRecords.length == 0
            ? 0
            : tokenCumRecords[tokenCumRecords.length - 1];
        tokenPtrs.push(ptr);
        tokenCumRecords.push(prev + data.length / RECORD_BYTES);
    }

    function seal() external onlyOwner notFrozen {
        frozen = true;
        owner = address(0);
    }

    // ---- reads ----

    function sprites() external view returns (bytes memory) {
        return SSTORE2.read(spritesPtr);
    }

    function offsets() external view returns (bytes memory) {
        return SSTORE2.read(offsetsPtr);
    }

    function totalTokens() external view returns (uint256) {
        uint256 n = tokenCumRecords.length;
        return n == 0 ? 0 : tokenCumRecords[n - 1];
    }

    /// @dev Returns the 5-byte record for `tokenId` (1-indexed).
    function tokenRecord(uint256 tokenId) external view returns (bytes memory) {
        require(tokenId != 0, "bad tokenId");
        uint256 idx = tokenId - 1;
        uint256 nChunks = tokenPtrs.length;
        uint256 prev = 0;
        for (uint256 c = 0; c < nChunks; c++) {
            uint256 cum = tokenCumRecords[c];
            if (idx < cum) {
                uint256 within = idx - prev;
                return SSTORE2.read(
                    tokenPtrs[c], within * RECORD_BYTES, within * RECORD_BYTES + RECORD_BYTES
                );
            }
            prev = cum;
        }
        revert("bad tokenId");
    }
}
