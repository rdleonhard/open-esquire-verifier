// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IBurnableToken} from "./VerifierDocket.sol";

/// @title CitationDocket (Open Esquire V3)
/// @notice One narrow, durable question per token: DOES THIS CITATION MATCH
///         A CASE ON COURTLISTENER (Free Law Project)?
///
///           FOUND     -> yes, a matching citation is on CourtListener; burn
///           NOT_FOUND -> no matching citation there (says nothing about
///                        unpublished/sealed/unindexed decisions); burn
///           DENIED    -> the verifier declines to answer; refund
///
///         The attestation is deliberately narrow: it is NOT a statement
///         that any case is good law, remains valid, or supports any
///         proposition — only whether the citation string resolves in the
///         public CourtListener database at ruling time. 1 token = 1 answer.
///
///         Refund guarantee: a matter pending past `maxWaitS` can be
///         reclaimed by anyone, returning the escrow to the asker.
contract CitationDocket {
    enum Ruling { Pending, Found, Denied, NotFound }

    struct Matter {
        address asker;
        uint96 paid;        // escrowed amount at filing time
        uint64 filedAt;
        uint64 ruledAt;
        Ruling ruling;
        string citation;    // one citation, Bluebook or similar
        string receipt;     // public docket permalink, set with the ruling
    }

    address public attorney;
    IBurnableToken public immutable token;
    uint256 public price;               // 1 token = 1 yes/no answer
    uint64 public maxWaitS;

    Matter[] private _matters;

    event MatterFiled(uint256 indexed id, address indexed asker, string citation);
    event MatterRuled(uint256 indexed id, Ruling ruling, string receipt);
    event MatterLapsed(uint256 indexed id, address indexed asker, uint256 refunded);
    event PriceSet(uint256 price);
    event MaxWaitSet(uint64 maxWaitS);
    event AttorneySet(address attorney);

    modifier onlyAttorney() {
        require(msg.sender == attorney, "not the attorney");
        _;
    }

    constructor(IBurnableToken token_, uint256 price_, uint64 maxWaitS_) {
        require(price_ > 0 && price_ <= type(uint96).max, "bad price");
        require(maxWaitS_ >= 5 minutes && maxWaitS_ <= 7 days, "bad wait");
        attorney = msg.sender;
        token = token_;
        price = price_;
        maxWaitS = maxWaitS_;
    }

    /// File one citation for a yes/no answer. Requires prior ERC-20
    /// approval of `price`. Citations are short strings by design.
    function submit(string calldata citation) external returns (uint256 id) {
        uint256 len = bytes(citation).length;
        require(len >= 4 && len <= 300, "bad citation length");
        uint256 p = price;
        require(token.transferFrom(msg.sender, address(this), p), "escrow failed");
        id = _matters.length;
        _matters.push(Matter({
            asker: msg.sender,
            paid: uint96(p),
            filedAt: uint64(block.timestamp),
            ruledAt: 0,
            ruling: Ruling.Pending,
            citation: citation,
            receipt: ""
        }));
        emit MatterFiled(id, msg.sender, citation);
    }

    /// The verifier's answer. FOUND / NOT_FOUND burn the escrow (the
    /// question was answered); DENIED refunds the asker.
    function rule(uint256 id, Ruling ruling_, string calldata receipt_)
        external onlyAttorney
    {
        Matter storage m = _matters[id];
        require(m.ruling == Ruling.Pending, "already ruled");
        require(ruling_ != Ruling.Pending, "bad ruling");
        m.ruling = ruling_;
        m.ruledAt = uint64(block.timestamp);
        m.receipt = receipt_;
        if (ruling_ == Ruling.Denied) {
            require(token.transfer(m.asker, m.paid), "refund failed");
        } else {
            token.burn(m.paid);
        }
        emit MatterRuled(id, ruling_, receipt_);
    }

    /// Trustless refund once a matter has sat pending past `maxWaitS`:
    /// anyone (typically the asker) may reclaim the escrow. A ruling
    /// posted before reclaim still wins.
    function reclaim(uint256 id) external {
        Matter storage m = _matters[id];
        require(m.ruling == Ruling.Pending, "already ruled");
        require(block.timestamp >= uint256(m.filedAt) + maxWaitS, "not yet");
        m.ruling = Ruling.Denied;
        m.ruledAt = uint64(block.timestamp);
        m.receipt = "lapsed: refunded, no answer within the posted deadline";
        require(token.transfer(m.asker, m.paid), "refund failed");
        emit MatterLapsed(id, m.asker, m.paid);
        emit MatterRuled(id, Ruling.Denied, m.receipt);
    }

    function matters(uint256 id) external view returns (Matter memory) {
        return _matters[id];
    }

    function count() external view returns (uint256) {
        return _matters.length;
    }

    function pendingCount() external view returns (uint256 n) {
        for (uint256 i = 0; i < _matters.length; i++) {
            if (_matters[i].ruling == Ruling.Pending) n++;
        }
    }

    function setPrice(uint256 price_) external onlyAttorney {
        require(price_ > 0 && price_ <= type(uint96).max, "bad price");
        price = price_;
        emit PriceSet(price_);
    }

    function setMaxWait(uint64 maxWaitS_) external onlyAttorney {
        require(maxWaitS_ >= 5 minutes && maxWaitS_ <= 7 days, "bad wait");
        maxWaitS = maxWaitS_;
        emit MaxWaitSet(maxWaitS_);
    }

    function setAttorney(address attorney_) external onlyAttorney {
        require(attorney_ != address(0), "zero address");
        attorney = attorney_;
        emit AttorneySet(attorney_);
    }
}
