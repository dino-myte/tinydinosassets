// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {DinoStorage} from "./DinoStorage.sol";

/// @notice One-shot deploy helper for managed-wallet deployers (e.g. the Bankr
/// wallet API) that can only send `to`-addressed calls — no raw contract-creation
/// transactions. Deployed via the canonical CREATE2 proxy
/// (0x4e59b44847b379578588920cA78FbF26c0B4956C); it creates the DinoStorage in
/// its constructor (so the helper is the storage owner) and forwards the
/// owner-only loading calls from the operator. After seal() the storage is
/// permanently ownerless as usual and this helper keeps no power over anything.
///
/// The DinoRenderer is deployed separately via the same CREATE2 proxy — its
/// constructor takes only the storage address and has no msg.sender logic.
contract DinoDeployer {
    address public immutable operator;
    DinoStorage public immutable store;

    modifier onlyOperator() {
        require(msg.sender == operator, "not operator");
        _;
    }

    constructor(address op) {
        operator = op;
        store = new DinoStorage();
    }

    function setSprites(bytes calldata d) external onlyOperator {
        store.setSprites(d);
    }

    function setOffsets(bytes calldata d) external onlyOperator {
        store.setOffsets(d);
    }

    function addTokenChunk(bytes calldata d) external onlyOperator {
        store.addTokenChunk(d);
    }

    function seal() external onlyOperator {
        store.seal();
    }
}
