// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {TestTinyDinos} from "./TestTinyDinos.sol";

/// @notice CREATE2-proxy helper for managed-wallet deployers (no raw creation
/// txs): creates the TestTinyDinos mimic in its constructor (so this helper is
/// its owner) and lets the operator drive it through a generic exec forwarder
/// (mint batches, setBaseURI, later transfers — anything onlyOwner).
contract TestNFTDeployer {
    address public immutable operator;
    TestTinyDinos public immutable nft;

    constructor(address op) {
        operator = op;
        nft = new TestTinyDinos();
    }

    function exec(address to, bytes calldata data) external returns (bytes memory) {
        require(msg.sender == operator, "not operator");
        (bool ok, bytes memory ret) = to.call(data);
        require(ok, "exec failed");
        return ret;
    }
}
