// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {VerifierDocket, IBurnableToken} from "../src/VerifierDocket.sol";
import {DemoToken} from "../src/DemoToken.sol";

contract VerifierDocketTest is Test {
    DemoToken token;
    VerifierDocket docket;
    address attorney = address(this);
    address asker = address(0xA11CE);
    uint256 constant PRICE = 10e18;

    function setUp() public {
        token = new DemoToken(1_000_000e18);
        docket = new VerifierDocket(IBurnableToken(address(token)), PRICE);
        token.transfer(asker, 100e18);
        vm.prank(asker);
        token.approve(address(docket), type(uint256).max);
    }

    function _file() internal returns (uint256 id) {
        vm.prank(asker);
        id = docket.submit(1, "Marbury v. Madison, 5 U.S. 137 (1803)");
    }

    function test_submit_escrows() public {
        uint256 before = token.balanceOf(asker);
        uint256 id = _file();
        assertEq(id, 0);
        assertEq(token.balanceOf(asker), before - PRICE);
        assertEq(token.balanceOf(address(docket)), PRICE);
        assertEq(uint8(docket.matters(id).ruling), uint8(VerifierDocket.Ruling.Pending));
        assertEq(docket.pendingCount(), 1);
    }

    function test_verified_burns_escrow() public {
        uint256 id = _file();
        uint256 supply = token.totalSupply();
        docket.rule(id, VerifierDocket.Ruling.Verified, "https://x/#B-0");
        assertEq(token.totalSupply(), supply - PRICE);       // burned
        assertEq(token.balanceOf(address(docket)), 0);
        assertEq(docket.matters(id).receipt, "https://x/#B-0");
        assertEq(docket.pendingCount(), 0);
    }

    function test_wrong_burns_escrow() public {
        uint256 id = _file();
        uint256 supply = token.totalSupply();
        docket.rule(id, VerifierDocket.Ruling.Wrong, "r");
        assertEq(token.totalSupply(), supply - PRICE);
    }

    function test_denied_refunds_asker() public {
        uint256 id = _file();
        uint256 before = token.balanceOf(asker);
        uint256 supply = token.totalSupply();
        docket.rule(id, VerifierDocket.Ruling.Denied, "r");
        assertEq(token.balanceOf(asker), before + PRICE);    // refunded
        assertEq(token.totalSupply(), supply);               // nothing burned
    }

    function test_refund_uses_paid_amount_not_current_price() public {
        uint256 id = _file();                                // escrowed 10
        docket.setPrice(999e18);                             // price changes later
        uint256 before = token.balanceOf(asker);
        docket.rule(id, VerifierDocket.Ruling.Denied, "r");
        assertEq(token.balanceOf(asker), before + PRICE);    // old amount back
    }

    function test_only_attorney_rules() public {
        uint256 id = _file();
        vm.prank(asker);
        vm.expectRevert("not the attorney");
        docket.rule(id, VerifierDocket.Ruling.Verified, "r");
    }

    function test_cannot_rule_twice() public {
        uint256 id = _file();
        docket.rule(id, VerifierDocket.Ruling.Verified, "r");
        vm.expectRevert("already ruled");
        docket.rule(id, VerifierDocket.Ruling.Wrong, "r2");
    }

    function test_cannot_rule_pending() public {
        uint256 id = _file();
        vm.expectRevert("bad ruling");
        docket.rule(id, VerifierDocket.Ruling.Pending, "r");
    }

    function test_submit_requires_allowance() public {
        address stranger = address(0xBEEF);
        token.transfer(stranger, 50e18);
        vm.prank(stranger);
        vm.expectRevert("insufficient allowance");
        docket.submit(0, "no approval given");
    }

    function test_rejects_bad_input() public {
        vm.startPrank(asker);
        vm.expectRevert("bad kind");
        docket.submit(3, "x");
        vm.expectRevert("bad text length");
        docket.submit(0, "");
        vm.stopPrank();
    }

    function test_attorney_handoff() public {
        docket.setAttorney(asker);
        uint256 id = _file();
        vm.expectRevert("not the attorney");
        docket.rule(id, VerifierDocket.Ruling.Verified, "r");
        vm.prank(asker);
        docket.rule(id, VerifierDocket.Ruling.Verified, "r");
    }

    function test_events() public {
        vm.expectEmit(true, true, false, true);
        emit VerifierDocket.MatterFiled(0, asker, 1, "Marbury v. Madison, 5 U.S. 137 (1803)");
        uint256 id = _file();
        vm.expectEmit(true, false, false, true);
        emit VerifierDocket.MatterRuled(id, VerifierDocket.Ruling.Verified, "rcpt");
        docket.rule(id, VerifierDocket.Ruling.Verified, "rcpt");
    }
}
