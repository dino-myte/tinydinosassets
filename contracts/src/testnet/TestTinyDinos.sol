// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {ERC721A} from "erc721a/contracts/ERC721A.sol";

/// @notice Deployable stand-in for the live `tiny dinos` ERC-721, for previewing
/// the on-chain renderer on a testnet / cheap chain on OpenSea.
///
/// Mimics the live contract where it matters for indexing + rendering:
///   - name "tiny dinos", symbol "dino"
///   - token ids start at 1 (ids 1..10000)
///   - setBaseURI(string) onlyOwner
///   - tokenURI(id) = string.concat(baseURI, id)   (ERC721A's default)
///
/// Uses ERC721A so all 10,000 can be batch-minted cheaply while still emitting a
/// Transfer event per token (so OpenSea indexes every token). The mint mechanism
/// differs from the live LayerZero ONFT, but tokenURI/metadata behaviour — the
/// only thing that affects how it renders on OpenSea — is identical.
contract TestTinyDinos is ERC721A {
    address public owner;
    string private _base;

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor() ERC721A("tiny dinos", "dino") {
        owner = msg.sender;
    }

    function _startTokenId() internal pure override returns (uint256) {
        return 1;
    }

    function _baseURI() internal view override returns (string memory) {
        return _base;
    }

    function setBaseURI(string calldata uri) external onlyOwner {
        _base = uri;
    }

    /// @dev Batch-mint `quantity` tokens to the owner (call in chunks to stay
    /// under the block gas limit, e.g. 2000 at a time for 10k total).
    function mint(uint256 quantity) external onlyOwner {
        _mint(owner, quantity);
    }
}
