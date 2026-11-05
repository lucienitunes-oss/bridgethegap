// SPDX-License-Identifier: AGPL-3.0
pragma solidity ^0.8.26;

interface Vm {
    function prank(address sender) external;
    function store(address target, bytes32 slot, bytes32 value) external;
}

interface IFactory {
    function owner() external view returns (address);
}

contract Proposal29EchidnaReplay {
    Vm private constant vm =
        Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    address private constant FACTORY =
        0x1F98431c8aD98523631AE4a59f267346ea31F984;
    address private constant CALLER =
        0x2BAD8182C09F50c8318d769245beA52C32Be46CD;
    address private constant ALIASED_OWNER =
        0x2BAD8182C09F50c8318d769245beA52C32Be46CD;
    bytes private constant SET_OWNER =
        hex"13af4035000000000000000000000000ff7ad5da31fecdc678796c88b05926db896b0699";
    bytes32 private constant OWNER_SLOT = bytes32(uint256(3));
    bytes32 private constant PRE_REPAIR_OWNER =
        hex"0000000000000000000000001a9c8182c09f50c8318d769245bea52c32be35bc";
    bytes32 private constant POST_REPAIR_OWNER =
        hex"0000000000000000000000002bad8182c09f50c8318d769245bea52c32be46cd";

    function _prefix(bytes32 ownerValue, bool expectedCallSuccess)
        internal
        returns (bool)
    {
        vm.store(FACTORY, OWNER_SLOT, ownerValue);
        bool ownerMatches = IFactory(FACTORY).owner() == ALIASED_OWNER;
        vm.prank(CALLER);
        (bool callSucceeded,) = FACTORY.call(SET_OWNER);
        return ownerMatches && (callSucceeded == expectedCallSuccess);
    }

    function echidna_proposal29_pre_repair_prefix_satisfies_property()
        public
        returns (bool)
    {
        return _prefix(PRE_REPAIR_OWNER, false);
    }

    function echidna_proposal29_post_repair_prefix_satisfies_property()
        public
        returns (bool)
    {
        return _prefix(POST_REPAIR_OWNER, true);
    }
}
