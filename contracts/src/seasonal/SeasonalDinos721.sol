// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

/// @notice Minimal indexable ERC-721 for previewing a seasonal collection, able
/// to mint arbitrary (non-contiguous) token ids — the seasonal tokens reuse the
/// original dino ids. setBaseURI + tokenURI=baseURI+id, like the live contracts.
contract SeasonalDinos721 {
    string public name;
    string public symbol;
    address public owner;
    string private _base;

    mapping(uint256 => address) private _owners;
    mapping(address => uint256) private _balances;
    mapping(uint256 => address) private _tokenApprovals;
    mapping(address => mapping(address => bool)) private _operatorApprovals;

    event Transfer(address indexed from, address indexed to, uint256 indexed id);
    event Approval(address indexed owner, address indexed approved, uint256 indexed id);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor(string memory _name, string memory _symbol) {
        name = _name;
        symbol = _symbol;
        owner = msg.sender;
    }

    function setBaseURI(string calldata uri) external onlyOwner {
        _base = uri;
    }

    function mintBatch(uint256[] calldata ids) external onlyOwner {
        for (uint256 i = 0; i < ids.length; i++) {
            uint256 id = ids[i];
            require(_owners[id] == address(0), "exists");
            _owners[id] = owner;
            emit Transfer(address(0), owner, id);
        }
        _balances[owner] += ids.length;
    }

    /// @dev Mint a contiguous run [from, from+qty) to the owner.
    function mintRange(uint256 from, uint256 qty) external onlyOwner {
        for (uint256 id = from; id < from + qty; id++) {
            require(_owners[id] == address(0), "exists");
            _owners[id] = owner;
            emit Transfer(address(0), owner, id);
        }
        _balances[owner] += qty;
    }

    function tokenURI(uint256 id) external view returns (string memory) {
        require(_owners[id] != address(0), "nonexistent");
        return bytes(_base).length == 0 ? "" : string.concat(_base, _toString(id));
    }

    function ownerOf(uint256 id) public view returns (address) {
        address o = _owners[id];
        require(o != address(0), "nonexistent");
        return o;
    }

    function balanceOf(address a) external view returns (uint256) {
        require(a != address(0), "zero");
        return _balances[a];
    }

    function approve(address to, uint256 id) external {
        address o = ownerOf(id);
        require(msg.sender == o || _operatorApprovals[o][msg.sender], "not authorized");
        _tokenApprovals[id] = to;
        emit Approval(o, to, id);
    }

    function getApproved(uint256 id) external view returns (address) {
        require(_owners[id] != address(0), "nonexistent");
        return _tokenApprovals[id];
    }

    function setApprovalForAll(address operator, bool approved) external {
        _operatorApprovals[msg.sender][operator] = approved;
        emit ApprovalForAll(msg.sender, operator, approved);
    }

    function isApprovedForAll(address o, address operator) public view returns (bool) {
        return _operatorApprovals[o][operator];
    }

    function transferFrom(address from, address to, uint256 id) public {
        require(ownerOf(id) == from, "wrong from");
        require(
            msg.sender == from || _tokenApprovals[id] == msg.sender || _operatorApprovals[from][msg.sender],
            "not authorized"
        );
        require(to != address(0), "zero to");
        delete _tokenApprovals[id];
        _balances[from] -= 1;
        _balances[to] += 1;
        _owners[id] = to;
        emit Transfer(from, to, id);
    }

    function safeTransferFrom(address from, address to, uint256 id) external {
        transferFrom(from, to, id);
    }

    function safeTransferFrom(address from, address to, uint256 id, bytes calldata) external {
        transferFrom(from, to, id);
    }

    function supportsInterface(bytes4 iid) external pure returns (bool) {
        return iid == 0x01ffc9a7 // ERC165
            || iid == 0x80ac58cd // ERC721
            || iid == 0x5b5e139f; // ERC721Metadata
    }

    function _toString(uint256 v) internal pure returns (string memory) {
        if (v == 0) return "0";
        uint256 d;
        uint256 t = v;
        while (t != 0) { d++; t /= 10; }
        bytes memory s = new bytes(d);
        while (v != 0) { s[--d] = bytes1(uint8(48 + (v % 10))); v /= 10; }
        return string(s);
    }
}
