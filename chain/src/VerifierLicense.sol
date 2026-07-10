// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title VerifierLicense
/// @notice Soulbound ERC-721: "the holder is a licensed attorney, verified
///         by Open Esquire, authorized to operate a verifier node on the
///         Open Esquire network."
///
///         * SOULBOUND — transfers always revert. The attestation is about
///           a person; it cannot be sold or delegated.
///         * REVOCABLE — the issuer can burn a license (bar status changes,
///           terms violated). Verification of licensure happens OFF-chain,
///           attorney-to-attorney, before minting.
///         * One license per address. Token ids start at 1.
contract VerifierLicense {
    string public constant name = "Open Esquire Verifier License";
    string public constant symbol = "ESQ";

    address public issuer;
    uint256 public nextId = 1;

    mapping(uint256 => address) private _holder;      // id -> holder
    mapping(address => uint256) public tokenOf;       // holder -> id (0=none)
    mapping(uint256 => string) public descriptorOf;   // id -> e.g. bar line
    uint256 public activeCount;

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Licensed(uint256 indexed tokenId, address indexed attorney, string descriptor);
    event Revoked(uint256 indexed tokenId, address indexed attorney);
    event IssuerSet(address issuer);

    modifier onlyIssuer() {
        require(msg.sender == issuer, "not the issuer");
        _;
    }

    constructor() {
        issuer = msg.sender;
    }

    /// Mint a license to a vetted licensed attorney. `descriptor` is a
    /// short public line (e.g. jurisdiction / role); never a secret.
    function mint(address to, string calldata descriptor)
        external onlyIssuer returns (uint256 id)
    {
        require(to != address(0), "zero address");
        require(tokenOf[to] == 0, "already licensed");
        id = nextId++;
        _holder[id] = to;
        tokenOf[to] = id;
        descriptorOf[id] = descriptor;
        activeCount++;
        emit Transfer(address(0), to, id);
        emit Licensed(id, to, descriptor);
    }

    /// Revoke a license (burn). The id is never reused.
    function revoke(uint256 id) external onlyIssuer {
        address h = _holder[id];
        require(h != address(0), "no such license");
        delete _holder[id];
        delete tokenOf[h];
        activeCount--;
        emit Transfer(h, address(0), id);
        emit Revoked(id, h);
    }

    function licensed(address who) external view returns (bool) {
        return tokenOf[who] != 0;
    }

    // ---- minimal ERC-721 views ----

    function balanceOf(address who) external view returns (uint256) {
        require(who != address(0), "zero address");
        return tokenOf[who] == 0 ? 0 : 1;
    }

    function ownerOf(uint256 id) public view returns (address) {
        address h = _holder[id];
        require(h != address(0), "no such license");
        return h;
    }

    function totalSupply() external view returns (uint256) {
        return activeCount;
    }

    function supportsInterface(bytes4 iid) external pure returns (bool) {
        return iid == 0x01ffc9a7      // ERC-165
            || iid == 0x80ac58cd      // ERC-721
            || iid == 0x5b5e139f;     // ERC-721 Metadata
    }

    // ---- soulbound: every transfer path reverts ----

    function transferFrom(address, address, uint256) external pure {
        revert("soulbound");
    }

    function safeTransferFrom(address, address, uint256) external pure {
        revert("soulbound");
    }

    function safeTransferFrom(address, address, uint256, bytes calldata)
        external pure
    {
        revert("soulbound");
    }

    function approve(address, uint256) external pure {
        revert("soulbound");
    }

    function setApprovalForAll(address, bool) external pure {
        revert("soulbound");
    }

    function getApproved(uint256) external pure returns (address) {
        return address(0);
    }

    function isApprovedForAll(address, address) external pure returns (bool) {
        return false;
    }

    // ---- on-chain metadata: the engraved seal ----

    function tokenURI(uint256 id) external view returns (string memory) {
        ownerOf(id);                          // reverts if revoked/unknown
        string memory n = _toString(id);
        string memory svg = string.concat(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 350 350">',
            '<rect width="350" height="350" fill="#050608"/>',
            '<rect x="12" y="12" width="326" height="326" fill="none" ',
            'stroke="#9a7f3a" stroke-width="2"/>',
            '<rect x="20" y="20" width="310" height="310" fill="none" ',
            'stroke="#2a2620"/>',
            '<polygon points="175,96 217,150 175,204 133,150" fill="none" ',
            'stroke="#e7be55" stroke-width="4"/>',
            '<polygon points="175,120 199,150 175,180 151,150" fill="#e7be55"/>',
            '<text x="175" y="240" text-anchor="middle" fill="#e7be55" ',
            'font-family="Georgia,serif" font-size="22" letter-spacing="6">',
            'OPEN ESQUIRE</text>',
            '<text x="175" y="266" text-anchor="middle" fill="#acb4c0" ',
            'font-family="Georgia,serif" font-size="11" letter-spacing="4">',
            'VERIFIER LICENSE No. ', n, '</text>',
            '<text x="175" y="292" text-anchor="middle" fill="#6a6658" ',
            'font-family="Georgia,serif" font-size="9" letter-spacing="2">',
            'LICENSED ATTORNEY - SOULBOUND - REVOCABLE</text></svg>');
        string memory json = string.concat(
            '{"name":"Open Esquire Verifier License #', n,
            '","description":"The holder is a licensed attorney, verified ',
            'by Open Esquire, and authorized to operate a verifier node on ',
            'the Open Esquire network. Soulbound (non-transferable); ',
            'revocable by the issuer if licensure lapses. ',
            unicode'Descriptor: ', descriptorOf[id], '",',
            '"image":"data:image/svg+xml;base64,', _b64(bytes(svg)), '"}');
        return string.concat("data:application/json;base64,", _b64(bytes(json)));
    }

    function setIssuer(address issuer_) external onlyIssuer {
        require(issuer_ != address(0), "zero address");
        issuer = issuer_;
        emit IssuerSet(issuer_);
    }

    // ---- tiny libs (kept local; repo vendors no OZ) ----

    function _toString(uint256 v) private pure returns (string memory) {
        if (v == 0) return "0";
        uint256 t = v; uint256 d;
        while (t != 0) { d++; t /= 10; }
        bytes memory b = new bytes(d);
        while (v != 0) { d--; b[d] = bytes1(uint8(48 + v % 10)); v /= 10; }
        return string(b);
    }

    string private constant _TABLE =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

    function _b64(bytes memory data) private pure returns (string memory) {
        if (data.length == 0) return "";
        string memory table = _TABLE;
        string memory result = new string(4 * ((data.length + 2) / 3));
        assembly {
            let tablePtr := add(table, 1)
            let resultPtr := add(result, 32)
            for {
                let dataPtr := data
                let endPtr := add(data, mload(data))
            } lt(dataPtr, endPtr) {} {
                dataPtr := add(dataPtr, 3)
                let input := mload(dataPtr)
                mstore8(resultPtr, mload(add(tablePtr, and(shr(18, input), 0x3F))))
                resultPtr := add(resultPtr, 1)
                mstore8(resultPtr, mload(add(tablePtr, and(shr(12, input), 0x3F))))
                resultPtr := add(resultPtr, 1)
                mstore8(resultPtr, mload(add(tablePtr, and(shr(6, input), 0x3F))))
                resultPtr := add(resultPtr, 1)
                mstore8(resultPtr, mload(add(tablePtr, and(input, 0x3F))))
                resultPtr := add(resultPtr, 1)
            }
            switch mod(mload(data), 3)
            case 1 {
                mstore8(sub(resultPtr, 1), 0x3d)
                mstore8(sub(resultPtr, 2), 0x3d)
            }
            case 2 {
                mstore8(sub(resultPtr, 1), 0x3d)
            }
        }
        return result;
    }
}
