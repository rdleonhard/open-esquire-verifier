// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {VerifierLicense} from "../src/VerifierLicense.sol";
import {DocketRegistry} from "../src/DocketRegistry.sol";
import {CitationDocket} from "../src/CitationDocket.sol";
import {IBurnableToken} from "../src/VerifierDocket.sol";
import {DemoToken} from "../src/DemoToken.sol";

contract NetworkTest is Test {
    VerifierLicense license;
    DocketRegistry registry;
    DemoToken token;
    address lawyerA = address(0xAAAA);
    address lawyerB = address(0xBBBB);
    address rando = address(0xCCCC);

    function setUp() public {
        token = new DemoToken(1_000_000e18);
        license = new VerifierLicense();
        registry = new DocketRegistry(license, IBurnableToken(address(token)));
    }

    function test_mint_and_licensed() public {
        uint256 id = license.mint(lawyerA, "Founding verifier");
        assertEq(id, 1);
        assertTrue(license.licensed(lawyerA));
        assertEq(license.ownerOf(1), lawyerA);
        assertEq(license.balanceOf(lawyerA), 1);
        assertEq(license.totalSupply(), 1);
        assertEq(license.descriptorOf(1), "Founding verifier");
    }

    function test_one_license_per_address() public {
        license.mint(lawyerA, "x");
        vm.expectRevert("already licensed");
        license.mint(lawyerA, "y");
    }

    function test_only_issuer_mints_and_revokes() public {
        vm.prank(lawyerA);
        vm.expectRevert("not the issuer");
        license.mint(lawyerA, "self-serve");
        uint256 id = license.mint(lawyerA, "x");
        vm.prank(lawyerA);
        vm.expectRevert("not the issuer");
        license.revoke(id);
    }

    function test_soulbound() public {
        uint256 id = license.mint(lawyerA, "x");
        vm.startPrank(lawyerA);
        vm.expectRevert("soulbound");
        license.transferFrom(lawyerA, lawyerB, id);
        vm.expectRevert("soulbound");
        license.safeTransferFrom(lawyerA, lawyerB, id);
        vm.expectRevert("soulbound");
        license.approve(lawyerB, id);
        vm.stopPrank();
    }

    function test_revoke_kills_license() public {
        uint256 id = license.mint(lawyerA, "x");
        license.revoke(id);
        assertFalse(license.licensed(lawyerA));
        assertEq(license.totalSupply(), 0);
        vm.expectRevert("no such license");
        license.ownerOf(id);
        // id never reused
        assertEq(license.mint(lawyerB, "y"), 2);
    }

    function test_token_uri_is_onchain_json() public {
        uint256 id = license.mint(lawyerA, "Founding verifier");
        string memory uri = license.tokenURI(id);
        assertTrue(bytes(uri).length > 100);
        // starts with the data-json prefix
        bytes memory prefix = bytes("data:application/json;base64,");
        for (uint256 i = 0; i < prefix.length; i++) {
            assertEq(bytes(uri)[i], prefix[i]);
        }
    }

    function test_open_docket_requires_license() public {
        vm.prank(rando);
        vm.expectRevert("not licensed");
        registry.openDocket(1e18, 1800);
    }

    function test_open_docket_makes_caller_attorney() public {
        license.mint(lawyerA, "x");
        vm.prank(lawyerA);
        address d = registry.openDocket(1e18, 1800);
        assertEq(CitationDocket(d).attorney(), lawyerA);
        assertEq(CitationDocket(d).price(), 1e18);
        assertEq(registry.docketOf(lawyerA), d);
        assertEq(registry.count(), 1);
        assertTrue(registry.active(0));
        assertEq(registry.nodes(0).licenseId, 1);
    }

    function test_register_existing_docket() public {
        license.mint(lawyerA, "x");
        vm.prank(lawyerA);
        CitationDocket d = new CitationDocket(
            IBurnableToken(address(token)), 1e18, 1800);
        vm.prank(lawyerA);
        registry.registerDocket(address(d));
        assertEq(registry.docketOf(lawyerA), address(d));
        // can't register someone else's docket
        license.mint(lawyerB, "y");
        vm.prank(lawyerB);
        vm.expectRevert("not your docket");
        registry.registerDocket(address(d));
    }

    function test_revocation_deactivates_node() public {
        uint256 id = license.mint(lawyerA, "x");
        vm.prank(lawyerA);
        registry.openDocket(1e18, 1800);
        assertTrue(registry.active(0));
        license.revoke(id);
        assertFalse(registry.active(0));
    }

    function test_relicense_does_not_revive_old_node() public {
        uint256 id = license.mint(lawyerA, "x");
        vm.prank(lawyerA);
        registry.openDocket(1e18, 1800);
        license.revoke(id);
        license.mint(lawyerA, "re-vetted");   // new license id
        assertFalse(registry.active(0));       // old node stays dead
    }
}
