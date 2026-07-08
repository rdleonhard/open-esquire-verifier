// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {VerifierDocketV2} from "../src/VerifierDocketV2.sol";
import {IBurnableToken} from "../src/VerifierDocket.sol";
import {DemoToken} from "../src/DemoToken.sol";

contract VerifierDocketV2Test is Test {
    DemoToken token;
    VerifierDocketV2 docket;
    address attorney = address(this);
    address asker = address(0xA11CE);
    uint256 constant CITE = 10e18;
    uint256 constant CHAR = 50e18;

    function setUp() public {
        token = new DemoToken(1_000_000e18);
        docket = new VerifierDocketV2(IBurnableToken(address(token)), CITE, CHAR);
        token.transfer(asker, 500e18);
        vm.prank(asker);
        token.approve(address(docket), type(uint256).max);
    }

    function _file(uint8 kind) internal returns (uint256 id) {
        vm.prank(asker);
        id = docket.submit(kind, "Marbury v. Madison, 5 U.S. 137 (1803)");
    }

    function test_per_kind_pricing() public {
        assertEq(docket.priceOf(1), CITE);
        assertEq(docket.priceOf(2), CHAR);
        assertEq(docket.price(), CITE);            // V1-compat view
        uint256 before = token.balanceOf(asker);
        _file(1);
        assertEq(token.balanceOf(asker), before - CITE);
        _file(2);
        assertEq(token.balanceOf(asker), before - CITE - CHAR);
        assertEq(docket.matters(1).paid, uint96(CHAR));
    }

    function test_char_costs_more_enforced_at_deploy() public {
        vm.expectRevert("char must cost >= cite");
        new VerifierDocketV2(IBurnableToken(address(token)), CHAR, CITE);
    }

    function test_verified_burns_escrow() public {
        uint256 id = _file(1);
        uint256 supply = token.totalSupply();
        docket.rule(id, VerifierDocketV2.Ruling.Verified, "https://x/#B-0", "");
        assertEq(token.totalSupply(), supply - CITE);
        assertEq(token.balanceOf(address(docket)), 0);
    }

    function test_denied_refunds_asker() public {
        uint256 id = _file(2);
        uint256 before = token.balanceOf(asker);
        docket.rule(id, VerifierDocketV2.Ruling.Denied, "r", "");
        assertEq(token.balanceOf(asker), before + CHAR);
    }

    function test_char_wrong_requires_rewrite() public {
        uint256 id = _file(2);
        vm.expectRevert("rewrite required");
        docket.rule(id, VerifierDocketV2.Ruling.Wrong, "r", "");
    }

    function test_char_wrong_stores_response_and_burns() public {
        uint256 id = _file(2);
        uint256 supply = token.totalSupply();
        string memory fix = "The case held X, not Y as characterized.";
        docket.rule(id, VerifierDocketV2.Ruling.Wrong, "https://x/#B-1", fix);
        assertEq(token.totalSupply(), supply - CHAR);        // burned
        assertEq(docket.matters(id).response, fix);
        assertEq(docket.matters(id).receipt, "https://x/#B-1");
    }

    function test_cite_wrong_needs_no_rewrite() public {
        uint256 id = _file(1);
        docket.rule(id, VerifierDocketV2.Ruling.Wrong, "r", "");
        assertEq(uint8(docket.matters(id).ruling),
                 uint8(VerifierDocketV2.Ruling.Wrong));
    }

    function test_only_attorney_rules() public {
        uint256 id = _file(1);
        vm.prank(asker);
        vm.expectRevert("not the attorney");
        docket.rule(id, VerifierDocketV2.Ruling.Verified, "r", "");
    }

    function test_no_double_ruling() public {
        uint256 id = _file(1);
        docket.rule(id, VerifierDocketV2.Ruling.Verified, "r", "");
        vm.expectRevert("already ruled");
        docket.rule(id, VerifierDocketV2.Ruling.Denied, "r", "");
    }

    function test_set_price_of() public {
        docket.setPriceOf(2, 75e18);
        assertEq(docket.priceOf(2), 75e18);
        vm.prank(asker);
        vm.expectRevert("not the attorney");
        docket.setPriceOf(2, 1);
    }

    function test_paid_survives_price_change() public {
        uint256 id = _file(2);
        docket.setPriceOf(2, 500e18);
        uint256 before = token.balanceOf(asker);
        docket.rule(id, VerifierDocketV2.Ruling.Denied, "r", "");
        assertEq(token.balanceOf(asker), before + CHAR);     // old escrow back
    }

    function test_reclaim_before_deadline_reverts() public {
        uint256 id = _file(1);
        vm.warp(block.timestamp + 29 minutes);
        vm.expectRevert("not yet");
        docket.reclaim(id);
    }

    function test_reclaim_refunds_after_deadline_anyone() public {
        uint256 id = _file(2);
        uint256 before = token.balanceOf(asker);
        vm.warp(block.timestamp + 31 minutes);
        vm.prank(address(0xBEEF));               // any third party
        docket.reclaim(id);
        assertEq(token.balanceOf(asker), before + CHAR);
        assertEq(uint8(docket.matters(id).ruling),
                 uint8(VerifierDocketV2.Ruling.Denied));
        assertEq(docket.pendingCount(), 0);
    }

    function test_reclaim_cannot_double_dip() public {
        uint256 id = _file(1);
        vm.warp(block.timestamp + 31 minutes);
        docket.reclaim(id);
        vm.expectRevert("already ruled");
        docket.reclaim(id);
        vm.expectRevert("already ruled");        // nor can a ruling follow
        docket.rule(id, VerifierDocketV2.Ruling.Verified, "r", "");
    }

    function test_ruling_beats_reclaim() public {
        uint256 id = _file(1);
        vm.warp(block.timestamp + 31 minutes);   // past deadline, unclaimed
        docket.rule(id, VerifierDocketV2.Ruling.Verified, "r", "");
        vm.expectRevert("already ruled");
        docket.reclaim(id);
    }

    function test_set_max_wait() public {
        docket.setMaxWait(2 hours);
        assertEq(docket.maxWaitS(), 2 hours);
        vm.expectRevert("bad wait");
        docket.setMaxWait(1 minutes);
        vm.prank(asker);
        vm.expectRevert("not the attorney");
        docket.setMaxWait(1 hours);
    }

    function test_response_length_capped() public {
        uint256 id = _file(2);
        bytes memory big = new bytes(4001);
        for (uint256 i = 0; i < big.length; i++) big[i] = "a";
        vm.expectRevert("response too long");
        docket.rule(id, VerifierDocketV2.Ruling.Wrong, "r", string(big));
    }
}
