// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {ERC721A} from "erc721a/contracts/ERC721A.sol";

/// @notice Gas-efficient (ERC721A) mimic 721 for a seasonal collection: ids start
/// at 1, name/symbol parameterized, setBaseURI + tokenURI = baseURI + id. Lets all
/// ~10k batch-mint cheaply while emitting a Transfer per token (so OpenSea indexes).
contract SeasonalNFT721A is ERC721A {
    address public owner;
    string private _base;

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor(string memory name_, string memory symbol_) ERC721A(name_, symbol_) {
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

    function mint(uint256 quantity) external onlyOwner {
        _mint(owner, quantity);
    }
}
