// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {SeasonalStorage} from "../src/seasonal/SeasonalStorage.sol";
import {SeasonalRenderer} from "../src/seasonal/SeasonalRenderer.sol";
import {SeasonalDinos721} from "../src/seasonal/SeasonalDinos721.sol";
import {Web3Url} from "../src/lib/Web3Url.sol";

/// @notice Deploy one seasonal collection (storage + renderer + mimic 721), mint
/// the real token ids, and point baseURI at the renderer via web3://.
///
///   SEASON=summer forge script script/DeploySeasonal.s.sol \
///     --rpc-url <RPC> --broadcast --private-key <KEY>
contract DeploySeasonal is Script {
    uint256 internal constant CHUNK = 24000;

    function run() external {
        string memory season = vm.envString("SEASON");
        string memory disp = _displayName(season);
        string memory desc = _description(season);
        string memory base = string.concat("../build/seasons/out/", season, "/");

        bytes memory sprites = vm.readFileBinary(string.concat(base, "sprites.bin"));
        bytes memory offsets = vm.readFileBinary(string.concat(base, "spriteOffsets.bin"));
        bytes memory idsBlob = vm.readFileBinary(string.concat(base, "ids.bin"));
        bytes memory records = vm.readFileBinary(string.concat(base, "records.bin"));
        bytes memory recOff = vm.readFileBinary(string.concat(base, "recordOffsets.bin"));
        bytes memory cats = bytes(vm.readFile(string.concat(base, "cats.txt")));
        bytes memory vals = bytes(vm.readFile(string.concat(base, "vals.txt")));

        vm.startBroadcast();

        SeasonalStorage store = new SeasonalStorage();
        for (uint256 off = 0; off < sprites.length; off += CHUNK) {
            uint256 end = off + CHUNK > sprites.length ? sprites.length : off + CHUNK;
            store.addSpriteChunk(_slice(sprites, off, end));
        }
        store.setBlobs(offsets, idsBlob, records, recOff, cats, vals);
        store.seal();

        SeasonalRenderer renderer = new SeasonalRenderer(store, disp, desc);

        SeasonalDinos721 nft = new SeasonalDinos721(disp, "dino");
        uint256[] memory ids = _parseIds(idsBlob);
        nft.mintBatch(ids);
        string memory baseURI = Web3Url.metadataBaseURI(address(renderer), block.chainid);
        nft.setBaseURI(baseURI);

        vm.stopBroadcast();

        console2.log("season        :", season);
        console2.log("SeasonalStorage :", address(store));
        console2.log("SeasonalRenderer:", address(renderer));
        console2.log("SeasonalDinos721:", address(nft));
        console2.log("tokens minted :", ids.length);
        console2.log("baseURI       :", baseURI);
        console2.log("sample tokenURI:", nft.tokenURI(ids[0]));
    }

    function _displayName(string memory s) internal pure returns (string memory) {
        bytes32 h = keccak256(bytes(s));
        if (h == keccak256("summer")) return "tiny dinos: summer 2022";
        if (h == keccak256("winter")) return "tiny dinos: winter 2022";
        if (h == keccak256("halloween")) return "tiny dinos: halloween 2022";
        revert("unknown season");
    }

    function _description(string memory s) internal pure returns (string memory) {
        bytes32 h = keccak256(bytes(s));
        if (h == keccak256("summer")) return "one of 10k tiny dinos ready for summer vibes";
        if (h == keccak256("winter")) return "one of 10k tiny dinos ready for winter vibes";
        if (h == keccak256("halloween")) return "one of 10k tiny dinos ready for halloween vibes";
        revert("unknown season");
    }

    function _parseIds(bytes memory b) internal pure returns (uint256[] memory ids) {
        uint256 n = b.length / 2;
        ids = new uint256[](n);
        for (uint256 i = 0; i < n; i++) {
            ids[i] = (uint256(uint8(b[i * 2])) << 8) | uint8(b[i * 2 + 1]);
        }
    }

    function _slice(bytes memory d, uint256 s, uint256 e) internal pure returns (bytes memory o) {
        o = new bytes(e - s);
        for (uint256 i = 0; i < o.length; i++) o[i] = d[s + i];
    }
}
