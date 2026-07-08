// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IBurnableToken} from "./VerifierDocket.sol";

/// @title VerifierDocketV2
/// @notice Second-generation docket for the Open Esquire verifier:
///           * per-kind pricing — a CHARACTERIZATION review (kind 2) costs
///             more than a CITATION check (kind 1), because the attorney may
///             have to rewrite the characterization, not just stamp it;
///           * the ruling can carry that corrected characterization back to
///             the asker on-chain (`response`), and a characterization matter
///             ruled WRONG must carry one — that is what the higher fee buys.
///         Escrow semantics are unchanged from V1:
///           VERIFIED / WRONG -> escrow burned;  DENIED -> asker refunded.
///         Rulings are personal scholarly attestations; the deployment
///         receipt and every docket receipt embed the capacity terms (no
///         legal advice, no attorney-client relationship).
contract VerifierDocketV2 {
    enum Ruling { Pending, Verified, Denied, Wrong }

    struct Matter {
        address asker;
        uint96 paid;        // escrowed amount at filing time
        uint64 filedAt;
        uint64 ruledAt;
        Ruling ruling;
        uint8 kind;         // 0 = review, 1 = citation, 2 = characterization
        string text;
        string receipt;     // public docket permalink, set with the ruling
        string response;    // attorney's corrected characterization (if any)
    }

    address public attorney;
    IBurnableToken public immutable token;
    mapping(uint8 => uint256) public priceOf;   // per-kind price
    uint64 public maxWaitS = 1800;              // 30 min: refund deadline

    Matter[] private _matters;

    event MatterFiled(uint256 indexed id, address indexed asker, uint8 kind, string text);
    event MatterRuled(uint256 indexed id, Ruling ruling, string receipt, string response);
    event MatterLapsed(uint256 indexed id, address indexed asker, uint256 refunded);
    event PriceSet(uint8 kind, uint256 price);
    event MaxWaitSet(uint64 maxWaitS);
    event AttorneySet(address attorney);

    modifier onlyAttorney() {
        require(msg.sender == attorney, "not the attorney");
        _;
    }

    constructor(IBurnableToken token_, uint256 citePrice, uint256 charPrice) {
        require(charPrice >= citePrice, "char must cost >= cite");
        attorney = msg.sender;
        token = token_;
        priceOf[0] = citePrice;      // plain review priced like a cite check
        priceOf[1] = citePrice;
        priceOf[2] = charPrice;
    }

    /// V1-compatible view: the base (citation) price.
    function price() external view returns (uint256) {
        return priceOf[1];
    }

    /// File a matter. Requires prior ERC-20 approval of `priceOf[kind]`.
    function submit(uint8 kind, string calldata text) external returns (uint256 id) {
        require(kind <= 2, "bad kind");
        uint256 len = bytes(text).length;
        require(len > 0 && len <= 2000, "bad text length");
        uint256 p = priceOf[kind];
        require(p > 0 && p <= type(uint96).max, "bad price");
        require(token.transferFrom(msg.sender, address(this), p), "escrow failed");
        id = _matters.length;
        _matters.push(Matter({
            asker: msg.sender,
            paid: uint96(p),
            filedAt: uint64(block.timestamp),
            ruledAt: 0,
            ruling: Ruling.Pending,
            kind: kind,
            text: text,
            receipt: "",
            response: ""
        }));
        emit MatterFiled(id, msg.sender, kind, text);
    }

    /// The attorney's ruling. A characterization matter ruled WRONG must
    /// carry the corrected characterization in `response_`.
    function rule(uint256 id, Ruling ruling_, string calldata receipt_,
                  string calldata response_) external onlyAttorney {
        Matter storage m = _matters[id];
        require(m.ruling == Ruling.Pending, "already ruled");
        require(ruling_ != Ruling.Pending, "bad ruling");
        if (m.kind == 2 && ruling_ == Ruling.Wrong) {
            require(bytes(response_).length > 0, "rewrite required");
        }
        require(bytes(response_).length <= 4000, "response too long");
        m.ruling = ruling_;
        m.ruledAt = uint64(block.timestamp);
        m.receipt = receipt_;
        m.response = response_;
        if (ruling_ == Ruling.Denied) {
            require(token.transfer(m.asker, m.paid), "refund failed");
        } else {
            token.burn(m.paid);
        }
        emit MatterRuled(id, ruling_, receipt_, response_);
    }

    /// Trustless refund: once a matter has sat pending past `maxWaitS`,
    /// ANYONE (typically the asker) can reclaim the escrow. The customer is
    /// never left waiting on the attorney's machines being on. An
    /// attorney's ruling posted before reclaim still wins.
    function reclaim(uint256 id) external {
        Matter storage m = _matters[id];
        require(m.ruling == Ruling.Pending, "already ruled");
        require(block.timestamp >= uint256(m.filedAt) + maxWaitS, "not yet");
        m.ruling = Ruling.Denied;
        m.ruledAt = uint64(block.timestamp);
        m.receipt = "lapsed: refunded, no ruling within the posted deadline";
        require(token.transfer(m.asker, m.paid), "refund failed");
        emit MatterLapsed(id, m.asker, m.paid);
        emit MatterRuled(id, Ruling.Denied, m.receipt, "");
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

    function setPriceOf(uint8 kind, uint256 price_) external onlyAttorney {
        require(kind <= 2, "bad kind");
        require(price_ > 0 && price_ <= type(uint96).max, "bad price");
        priceOf[kind] = price_;
        emit PriceSet(kind, price_);
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
