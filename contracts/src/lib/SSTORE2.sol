// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Minimal SSTORE2: store an immutable byte blob as contract code and
/// read slices of it back. Each blob is limited to ~24KB (contract code size).
/// Standard, well-known implementation (Solmate/Solady lineage).
library SSTORE2 {
    /// @dev Writes `data` as the runtime code of a new contract, prefixed with a
    /// STOP byte (0x00) so the code can never be executed. Returns its address.
    function write(bytes memory data) internal returns (address pointer) {
        require(data.length <= 24575, "SSTORE2: too large"); // EIP-170 minus STOP prefix
        bytes memory runtime = abi.encodePacked(hex"00", data);
        // creation code: returns `runtime` as the deployed code.
        //   0x60 size 0x80 0x60 0x0a 0x39 0x60 size 0x90 0x57 ... -> use a simple wrapper
        bytes memory creation = abi.encodePacked(
            hex"61",            // PUSH2 size
            uint16(runtime.length),
            hex"80",            // DUP1
            hex"600a",          // PUSH1 0x0a (offset of runtime in this creation code)
            hex"3d",            // RETURNDATASIZE (0)
            hex"39",            // CODECOPY
            hex"3d",            // RETURNDATASIZE (0)
            hex"f3",            // RETURN
            runtime
        );
        assembly {
            pointer := create(0, add(creation, 0x20), mload(creation))
        }
        require(pointer != address(0), "SSTORE2: deploy failed");
    }

    /// @dev Reads the full blob (minus the leading STOP byte).
    function read(address pointer) internal view returns (bytes memory) {
        uint256 size = pointer.code.length;
        require(size > 0, "SSTORE2: empty");
        return _readBytes(pointer, 1, size);
    }

    /// @dev Reads `data[start:end]` (offsets into the original blob, i.e. excluding STOP byte).
    function read(address pointer, uint256 start, uint256 end)
        internal
        view
        returns (bytes memory)
    {
        return _readBytes(pointer, start + 1, end + 1);
    }

    function _readBytes(address pointer, uint256 from, uint256 to)
        private
        view
        returns (bytes memory out)
    {
        uint256 len = to - from;
        out = new bytes(len);
        assembly {
            extcodecopy(pointer, add(out, 0x20), from, len)
        }
    }
}
