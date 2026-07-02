// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// Minimal interface the payment token must satisfy: standard ERC-20
/// transfers plus the ability to burn tokens the docket holds in escrow.
interface IBurnableToken {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function burn(uint256 amount) external;
}

/// @title VerifierDocket
/// @notice AI models (or anyone) pay a token price to place a case-law claim
///         on a licensed attorney's docket. Tokens are held in ESCROW until
///         the attorney rules from the hardware verifier:
///           VERIFIED / WRONG  -> the escrowed tokens are burned
///           DENIED            -> the asker is refunded (attorney declined)
///         Every ruling carries a receipt URL pointing at the public docket.
contract VerifierDocket {
    enum Ruling { Pending, Verified, Denied, Wrong }

    struct Matter {
        address asker;
        uint96 paid;        // escrowed amount (price may change later)
        uint64 filedAt;
        uint64 ruledAt;
        Ruling ruling;
        uint8 kind;         // 0 = review, 1 = citation, 2 = characterization
        string text;
        string receipt;     // public docket permalink, set with the ruling
    }

    address public attorney;
    IBurnableToken public immutable token;
    uint256 public price;

    Matter[] private _matters;

    event MatterFiled(uint256 indexed id, address indexed asker, uint8 kind, string text);
    event MatterRuled(uint256 indexed id, Ruling ruling, string receipt);
    event PriceSet(uint256 price);
    event AttorneySet(address attorney);

    modifier onlyAttorney() {
        require(msg.sender == attorney, "not the attorney");
        _;
    }

    constructor(IBurnableToken token_, uint256 price_) {
        attorney = msg.sender;
        token = token_;
        price = price_;
    }

    /// File a matter for review. Requires prior ERC-20 approval of `price`.
    function submit(uint8 kind, string calldata text) external returns (uint256 id) {
        require(kind <= 2, "bad kind");
        uint256 len = bytes(text).length;
        require(len > 0 && len <= 2000, "bad text length");
        uint256 p = price;
        require(p <= type(uint96).max, "price too large");
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
            receipt: ""
        }));
        emit MatterFiled(id, msg.sender, kind, text);
    }

    /// The attorney's ruling, posted by the oracle bridge after the physical
    /// tap on the verifier. Escrow is burned, except DENIED which refunds.
    function rule(uint256 id, Ruling ruling_, string calldata receipt_) external onlyAttorney {
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
        require(price_ <= type(uint96).max, "price too large");
        price = price_;
        emit PriceSet(price_);
    }

    function setAttorney(address attorney_) external onlyAttorney {
        require(attorney_ != address(0), "zero address");
        attorney = attorney_;
        emit AttorneySet(attorney_);
    }
}
