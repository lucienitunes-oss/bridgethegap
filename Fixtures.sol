// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

// Constructed regression fixtures, not deployed protocol implementations.
contract Effects {
    uint256 public value;
    mapping(uint256 => uint256) public dynamicSlots;
    bool public blocked;
    function set(uint256 v) external { require(!blocked, "blocked"); value = v; }
    function blockCalls(bool flag) external { blocked = flag; }
    function setDynamic(uint256 key, uint256 v) external { dynamicSlots[key] = v; }
    function setThenRevert(uint256 v) external { value = v; revert("rollback"); }
    function delegate(address implementation, bytes calldata data) external {
        (bool ok,) = implementation.delegatecall(data); require(ok);
    }
    function transientRoundTrip(uint256 v) external returns (uint256 result) {
        assembly { tstore(0, v) result := tload(0) }
    }
    function transientRead() external view returns (uint256 result) {
        assembly { result := tload(0) }
    }
}

contract Relay {
    address public immutable governor;
    mapping(bytes32 => bool) public executed;
    constructor() { governor = msg.sender; }
    function deliver(bytes32 id, address target, bytes calldata data, uint256 deadline) external {
        require(msg.sender == governor, "authentication");
        require(block.timestamp <= deadline, "expired");
        require(!executed[id], "duplicate");
        executed[id] = true;
        (bool ok,) = target.call(data);
        require(ok, "destination revert");
    }
}

contract CallbackVault {
    mapping(address => uint256) public credit;
    uint256 public totalPaid;
    bool public immutable fixedOrder;
    constructor(bool fixed_) { fixedOrder = fixed_; }
    function seed(address who) external { credit[who] = 1; }
    function withdraw() external {
        uint256 n = credit[msg.sender]; require(n > 0);
        if (fixedOrder) credit[msg.sender] = 0;
        (bool ok,) = msg.sender.call(abi.encodeWithSignature("onPay()"));
        require(ok); totalPaid += n;
        if (!fixedOrder) credit[msg.sender] = 0;
    }
}

contract CallbackClient {
    CallbackVault public vault;
    bool private entered;
    constructor(address v) { vault = CallbackVault(v); }
    function start() external { vault.withdraw(); }
    function onPay() external {
        require(msg.sender == address(vault));
        if (!entered) {
            entered = true;
            // A failed second withdrawal is intentionally caught by this fixture.
            address(vault).call(abi.encodeWithSignature("withdraw()"));
        }
    }
}
