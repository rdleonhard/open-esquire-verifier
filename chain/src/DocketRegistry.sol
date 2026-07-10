// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IBurnableToken} from "./VerifierDocket.sol";
import {CitationDocket} from "./CitationDocket.sol";
import {VerifierLicense} from "./VerifierLicense.sol";

/// @title DocketRegistry
/// @notice The Open Esquire network: any attorney holding a VerifierLicense
///         (soulbound, issued after off-chain verification of licensure)
///         can open their own CitationDocket and appear in the public
///         registry that LLM agents read to pick a verifier node.
contract DocketRegistry {
    struct Node {
        uint256 licenseId;
        address attorney;
        address docket;
        uint64 openedAt;
    }

    VerifierLicense public immutable license;
    IBurnableToken public immutable token;
    Node[] private _nodes;
    mapping(address => address) public docketOf;   // attorney -> docket

    event NodeOpened(uint256 indexed licenseId, address indexed attorney,
                     address docket);

    modifier onlyLicensed() {
        require(license.licensed(msg.sender), "not licensed");
        _;
    }

    constructor(VerifierLicense license_, IBurnableToken token_) {
        license = license_;
        token = token_;
    }

    /// Deploy a fresh CitationDocket with the caller as its attorney.
    function openDocket(uint256 price, uint64 maxWaitS)
        external onlyLicensed returns (address docket)
    {
        require(docketOf[msg.sender] == address(0), "node exists");
        CitationDocket d = new CitationDocket(token, price, maxWaitS);
        d.setAttorney(msg.sender);
        docket = address(d);
        _register(docket);
    }

    /// Register a docket deployed elsewhere; the caller must already be
    /// its attorney (proves control) and hold a license.
    function registerDocket(address docket) external onlyLicensed {
        require(docketOf[msg.sender] == address(0), "node exists");
        require(CitationDocket(docket).attorney() == msg.sender,
                "not your docket");
        _register(docket);
    }

    function _register(address docket) private {
        uint256 lid = license.tokenOf(msg.sender);
        docketOf[msg.sender] = docket;
        _nodes.push(Node({
            licenseId: lid,
            attorney: msg.sender,
            docket: docket,
            openedAt: uint64(block.timestamp)
        }));
        emit NodeOpened(lid, msg.sender, docket);
    }

    /// A node is live only while its attorney's license stands — agents
    /// should check `active` before filing with a node.
    function active(uint256 i) external view returns (bool) {
        Node memory n = _nodes[i];
        return license.licensed(n.attorney)
            && license.tokenOf(n.attorney) == n.licenseId;
    }

    function nodes(uint256 i) external view returns (Node memory) {
        return _nodes[i];
    }

    function count() external view returns (uint256) {
        return _nodes.length;
    }
}
