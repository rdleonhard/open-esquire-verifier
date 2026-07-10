// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {CitationDocket} from "../src/CitationDocket.sol";
import {IBurnableToken} from "../src/VerifierDocket.sol";
import {DemoToken} from "../src/DemoToken.sol";

contract CitationDocketTest is Test {
    DemoToken token;
    CitationDocket docket;
    address asker = address(0xA11CE);
    uint256 constant PRICE = 1e18;          // 1 token = 1 answer

    function setUp() public {
        token = new DemoToken(1_000_000e18);
        docket = new CitationDocket(IBurnableToken(address(token)), PRICE, 1800);
        token.transfer(asker, 10e18);
        vm.prank(asker);
        token.approve(address(docket), type(uint256).max);
    }

    function _file() internal returns (uint256 id) {
        vm.prank(asker);
        id = docket.submit("410 U.S. 113");
    }

    function test_submit_escrows_one_token() public {
        uint256 before = token.balanceOf(asker);
        uint256 id = _file();
        assertEq(id, 0);
        assertEq(token.balanceOf(asker), before - PRICE);
        assertEq(docket.matters(id).citation, "410 U.S. 113");
        assertEq(docket.pendingCount(), 1);
    }

    function test_found_burns() public {
        uint256 id = _file();
        uint256 supply = token.totalSupply();
        docket.rule(id, CitationDocket.Ruling.Found, "https://x/#CL-0");
        assertEq(token.totalSupply(), supply - PRICE);
        assertEq(docket.matters(id).receipt, "https://x/#CL-0");
    }

    function test_not_found_burns_too() public {
        // NO is a completed answer — it costs the token just like YES
        uint256 id = _file();
        uint256 supply = token.totalSupply();
        docket.rule(id, CitationDocket.Ruling.NotFound, "r");
        assertEq(token.totalSupply(), supply - PRICE);
    }

    function test_denied_refunds() public {
        uint256 id = _file();
        uint256 before = token.balanceOf(asker);
        docket.rule(id, CitationDocket.Ruling.Denied, "r");
        assertEq(token.balanceOf(asker), before + PRICE);
    }

    function test_citation_length_bounds() public {
        vm.prank(asker);
        vm.expectRevert("bad citation length");
        docket.submit("1 A");
        bytes memory big = new bytes(301);
        for (uint256 i = 0; i < big.length; i++) big[i] = "a";
        vm.prank(asker);
        vm.expectRevert("bad citation length");
        docket.submit(string(big));
    }

    function test_only_attorney_rules() public {
        uint256 id = _file();
        vm.prank(asker);
        vm.expectRevert("not the attorney");
        docket.rule(id, CitationDocket.Ruling.Found, "r");
    }

    function test_no_double_ruling() public {
        uint256 id = _file();
        docket.rule(id, CitationDocket.Ruling.Found, "r");
        vm.expectRevert("already ruled");
        docket.rule(id, CitationDocket.Ruling.Denied, "r");
    }

    function test_reclaim_after_deadline() public {
        uint256 id = _file();
        vm.warp(block.timestamp + 29 minutes);
        vm.expectRevert("not yet");
        docket.reclaim(id);
        vm.warp(block.timestamp + 2 minutes);
        uint256 before = token.balanceOf(asker);
        vm.prank(address(0xBEEF));
        docket.reclaim(id);
        assertEq(token.balanceOf(asker), before + PRICE);
        vm.expectRevert("already ruled");
        docket.rule(id, CitationDocket.Ruling.Found, "r");
    }

    function test_paid_survives_price_change() public {
        uint256 id = _file();
        docket.setPrice(5e18);
        uint256 before = token.balanceOf(asker);
        docket.rule(id, CitationDocket.Ruling.Denied, "r");
        assertEq(token.balanceOf(asker), before + PRICE);
    }

    function test_admin_gates() public {
        vm.startPrank(asker);
        vm.expectRevert("not the attorney");
        docket.setPrice(2e18);
        vm.expectRevert("not the attorney");
        docket.setMaxWait(1 hours);
        vm.stopPrank();
        vm.expectRevert("bad wait");
        docket.setMaxWait(1 minutes);
    }
}
