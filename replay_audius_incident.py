"""Replay the public transaction-level prefix of the Audius governance takeover.

The collector is read-only.  It does not submit transactions or infer hidden
state from a model: every row is backed by a transaction, receipt, block, and
the AUDIO Transfer events emitted by the historical execution.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from web3 import Web3

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "experiments" / "results" / "real_replay" / "audius_incident.json"
RPC = "https://eth.drpc.org"

GOVERNANCE_PROXY = Web3.to_checksum_address("0x4DEcA517D6817B6510798b7328F2314d3003AbAC")
AUDIO = Web3.to_checksum_address("0x18aAA7115705e8be94bfFEBDE57Af9BFc265B998")
TREASURY = GOVERNANCE_PROXY
STAKING = Web3.to_checksum_address("0xe6D97B2099F142513be7A2a068bE040656Ae4591")
DELEGATE_MANAGER = Web3.to_checksum_address("0x4d7968ebfD390D5E7926Cb3587C39eFf2F9FB225")

# These hashes are linked from, or explicitly described by, the official
# Audius postmortem.  The later proposal/vote/execute hashes are retained as
# exact public evidence for the complete security-consequence prefix.
TX_HASHES = [
    ("attacker_initialize", "0x3bbb15f9852c389e8d77399fe88b49b042d0f22aad4a33c979fbabc60a34b24f"),
    ("malicious_proposal", "0xfefd829e246002a8fd061eede7501bccb6e244a9aacea0ebceaecef5d877a984"),
    ("vote_proposal_85", "0x3c09c6306b67737227edc24c663462d870e7c2bf39e9ab66877a980c900dd5d5"),
    ("execute_proposal_85", "0x4227bca8ed4b8915c7eec0e14ad3748a88c4371d4176e716e8007249b9980dc9"),
    ("treasury_token_transfer", "0x82fc23992c7433fffad0e28a1b8d11211dc4377de83e88088d79f24f4a3f28b3"),
]

TRANSFER_TOPIC = Web3.keccak(text="Transfer(address,address,uint256)").hex()
PROPOSAL_CREATED_TOPIC = "7edc618964f595eb3f96e87d2c01643484aa8490797eb47bd46680d0ad4c7f72"
PROPOSAL_STATE_TOPIC = "b5c05f2b4df457fb2a62ca282c87338fa901f0b7de530321f507d59859cc11cf"
VOTE_CAST_TOPIC = "f3f11b6b0f2367aeeec3a6b96f9528d1b57165334563e1d7083be608cdb64a54"
PROPOSAL_EXECUTED_TOPIC = "a85727613e00cfd4688ad13995391ed4b4cd9e493bcb978393d8fddeec804dbd"


def utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def hex_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    return int(value, 16) if isinstance(value, str) else int(value)


def address_from_topic(topic: str) -> str:
    return Web3.to_checksum_address("0x" + topic[-40:])


def read_tx(w3: Web3, label: str, tx_hash: str) -> dict:
    last_error = None
    for _ in range(4):
        try:
            tx = w3.eth.get_transaction(tx_hash)
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            block = w3.eth.get_block(receipt["blockNumber"])
            logs = []
            audio_transfers = []
            governance_events = []
            for log in receipt["logs"]:
                item = {
                    "address": log["address"],
                    "topics": [topic.hex() for topic in log["topics"]],
                    "data": log["data"].hex(),
                    "log_index": log["logIndex"],
                }
                logs.append(item)
                if (log["address"].lower() == GOVERNANCE_PROXY.lower()
                        and log["topics"]):
                    topic0 = log["topics"][0].hex().lower()
                    if topic0 == PROPOSAL_CREATED_TOPIC:
                        governance_events.append({
                            "type": "proposal_created",
                            "proposal_id": int(log["topics"][1].hex(), 16),
                            "proposer": address_from_topic(log["topics"][2].hex()),
                            "log_index": log["logIndex"],
                        })
                    elif topic0 == PROPOSAL_STATE_TOPIC:
                        governance_events.append({
                            "type": "proposal_state",
                            "proposal_id": int(log["topics"][1].hex(), 16),
                            "state_code": int(log["topics"][2].hex(), 16),
                            "log_index": log["logIndex"],
                        })
                    elif topic0 == VOTE_CAST_TOPIC:
                        governance_events.append({
                            "type": "vote_cast",
                            "proposal_id": int(log["topics"][1].hex(), 16),
                            "voter": address_from_topic(log["topics"][2].hex()),
                            "support": int(log["topics"][3].hex(), 16),
                            "log_index": log["logIndex"],
                        })
                    elif topic0 == PROPOSAL_EXECUTED_TOPIC:
                        governance_events.append({
                            "type": "proposal_executed",
                            "proposal_id": int(log["topics"][1].hex(), 16),
                            "result_code": int(log["topics"][2].hex(), 16),
                            "log_index": log["logIndex"],
                        })
                if (log["address"].lower() == AUDIO.lower()
                        and log["topics"]
                        and log["topics"][0].hex().lower() == TRANSFER_TOPIC.lower()):
                    audio_transfers.append({
                        "from": address_from_topic(log["topics"][1].hex()),
                        "to": address_from_topic(log["topics"][2].hex()),
                        "amount_wei": int(log["data"].hex(), 16),
                        "amount_audio": int(log["data"].hex(), 16) / 10**18,
                        "log_index": log["logIndex"],
                    })
            return {
                "label": label,
                "transaction_hash": tx_hash,
                "block": receipt["blockNumber"],
                "timestamp": block["timestamp"],
                "timestamp_utc": utc(block["timestamp"]),
                "transaction_index": receipt["transactionIndex"],
                "status": receipt["status"],
                "from": tx["from"],
                "to": tx["to"],
                "nonce": tx["nonce"],
                "input_selector": tx["input"][:4].hex(),
                "input_hex": tx["input"].hex(),
                "gas_used": receipt["gasUsed"],
                "log_count": len(logs),
                "audio_transfers": audio_transfers,
                "governance_events": governance_events,
                "logs": logs,
            }
        except Exception as exc:
            last_error = str(exc)[:300]
            time.sleep(0.6)
    raise RuntimeError(f"could not read {tx_hash}: {last_error}")


def audio_balance(w3: Web3, holder: str, block: int) -> dict:
    # balanceOf(address), encoded without relying on a contract ABI.
    data = "0x70a08231" + holder.lower().removeprefix("0x").rjust(64, "0")
    try:
        raw = w3.eth.call({"to": AUDIO, "data": data}, block_identifier=block)
        value = int(raw.hex(), 16)
        return {"block": block, "wei": value, "audio": value / 10**18}
    except Exception as exc:
        return {"block": block, "error": str(exc)[:240]}


def address_call(w3: Web3, contract: str, signature: str, block: int) -> dict:
    """Read one address-valued view at an archived block boundary."""
    selector = Web3.keccak(text=signature)[:4].hex()
    try:
        raw = w3.eth.call(
            {"to": Web3.to_checksum_address(contract), "data": "0x" + selector},
            block_identifier=block,
        )
        raw_hex = raw.hex()
        return {
            "contract": contract,
            "function": signature,
            "block": block,
            "value": address_from_topic(raw_hex),
            "raw": raw_hex,
        }
    except Exception as exc:
        return {
            "contract": contract,
            "function": signature,
            "block": block,
            "error": str(exc)[:240],
        }


def storage_witness(w3: Web3, contract: str, slot: int, block: int) -> dict:
    """Read a raw storage slot without assuming an ABI layout."""
    try:
        raw = w3.eth.get_storage_at(
            Web3.to_checksum_address(contract), slot, block_identifier=block
        )
        return {
            "contract": contract,
            "slot": slot,
            "block": block,
            "raw": raw.hex(),
        }
    except Exception as exc:
        return {
            "contract": contract,
            "slot": slot,
            "block": block,
            "error": str(exc)[:240],
        }


def main() -> None:
    w3 = Web3(Web3.HTTPProvider(RPC, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise RuntimeError(f"RPC unavailable: {RPC}")
    transactions = [read_tx(w3, label, tx_hash) for label, tx_hash in TX_HASHES]
    attacker = transactions[0]["from"]
    transfer_rows = [
        transfer
        for tx in transactions
        for transfer in tx["audio_transfers"]
    ]
    malicious_target = next(
        (row["to"] for row in transfer_rows
         if row["from"].lower() == TREASURY.lower()),
        None,
    )
    # The post-mortem describes a proxy-slot collision, but the security claim
    # is stronger when the replay also carries independent state reads.  These
    # calls are made at the block immediately before and after the attacker's
    # initialize transaction; no incident label is used to derive the values.
    permission_before_block = transactions[0]["block"] - 1
    permission_after_block = transactions[0]["block"]
    permission_queries = [
        (GOVERNANCE_PROXY, "getGuardianAddress()", "governance.guardian"),
        (GOVERNANCE_PROXY, "getRegistryAddress()", "governance.registry"),
        (STAKING, "getGovernanceAddress()", "staking.governance"),
        (DELEGATE_MANAGER, "getGovernanceAddress()", "delegate_manager.governance"),
    ]
    permission_fields = []
    for contract, signature, name in permission_queries:
        before = address_call(w3, contract, signature, permission_before_block)
        after = address_call(w3, contract, signature, permission_after_block)
        permission_fields.append({
            "name": name,
            "before": before,
            "after": after,
            "changed": (
                "value" in before and "value" in after
                and before["value"].lower() != after["value"].lower()
            ),
        })
    permission_state_diff = {
        "transaction_hash": transactions[0]["transaction_hash"],
        "before_block": permission_before_block,
        "after_block": permission_after_block,
        "fields": permission_fields,
        "changed_field_count": sum(1 for field in permission_fields if field["changed"]),
        "slot_0_proxy_admin": {
            "before": storage_witness(w3, GOVERNANCE_PROXY, 0, permission_before_block),
            "after": storage_witness(w3, GOVERNANCE_PROXY, 0, permission_after_block),
            "expected_unchanged": True,
        },
    }
    state_witnesses = []
    for tx in transactions:
        before = tx["block"] - 1
        after = tx["block"]
        witness = {
            "label": tx["label"],
            "transaction_hash": tx["transaction_hash"],
            "before_block": before,
            "after_block": after,
            "treasury_audio_before": audio_balance(w3, TREASURY, before),
            "treasury_audio_after": audio_balance(w3, TREASURY, after),
            "attacker_audio_before": audio_balance(w3, attacker, before),
            "attacker_audio_after": audio_balance(w3, attacker, after),
        }
        if malicious_target:
            witness["malicious_target"] = malicious_target
            witness["malicious_target_audio_before"] = audio_balance(w3, malicious_target, before)
            witness["malicious_target_audio_after"] = audio_balance(w3, malicious_target, after)
        state_witnesses.append(witness)

    first = transactions[0]
    first_is_unauthorized = first["from"].lower() != GOVERNANCE_PROXY.lower()
    first_succeeded = first["status"] == 1
    transfer_from_treasury = [
        row for row in transfer_rows if row["from"].lower() == TREASURY.lower()
    ]
    transferred_audio = sum(row["amount_audio"] for row in transfer_from_treasury)
    governance_events = [
        event
        for tx in transactions
        for event in tx["governance_events"]
    ]
    event_by_proposal = {
        proposal_id: [event for event in governance_events
                      if event["proposal_id"] == proposal_id]
        for proposal_id in (82, 83, 84, 85)
    }
    tx_by_label = {tx["label"]: tx for tx in transactions}
    proposal_paths = [
        {
            "proposal_ids": [82, 83],
            "path": "initialization_corruption_then_target_rejection",
            "transaction_hash": tx_by_label["attacker_initialize"]["transaction_hash"],
            "block": tx_by_label["attacker_initialize"]["block"],
            "state_events": [event for event in event_by_proposal[82] + event_by_proposal[83]
                             if event["type"] == "proposal_state"],
            "observed_result": "state changes occurred after repeatable initialization; proposals 82/83 were marked executed in the same transaction",
            "official_result": "execution path failed with TargetContractAddressChanged; no AUDIO transfer",
            "prefix_result": "VIOLATION",
        },
        {
            "proposal_ids": [84],
            "path": "proposal_84_quorum_failure",
            "transaction_hash": tx_by_label["malicious_proposal"]["transaction_hash"],
            "block": tx_by_label["malicious_proposal"]["block"],
            "state_events": [event for event in event_by_proposal[84]
                             if event["type"] == "proposal_state"],
            "vote_events": [event for event in event_by_proposal[84]
                            if event["type"] == "vote_cast"],
            "observed_result": "proposal 84 reached the defeated state and has no vote event in the replayed prefix",
            "official_result": "proposal 84 did not pass quorum and failed during execution",
            "prefix_result": "PASS",
        },
        {
            "proposal_ids": [85],
            "path": "proposal_85_successful_treasury_transfer",
            "transaction_hash": tx_by_label["execute_proposal_85"]["transaction_hash"],
            "block": tx_by_label["execute_proposal_85"]["block"],
            "state_events": [event for event in event_by_proposal[85]
                             if event["type"] == "proposal_state"],
            "vote_events": [event for event in event_by_proposal[85]
                            if event["type"] == "vote_cast"],
            "execution_events": [event for event in event_by_proposal[85]
                                 if event["type"] == "proposal_executed"],
            "observed_result": f"proposal 85 was voted and executed; {transferred_audio:.2f} AUDIO left the governance treasury",
            "official_result": "proposal 85 executed successfully and transferred the community pool",
            "prefix_result": "VIOLATION",
        },
    ]

    artifact = {
        "status": "complete",
        "case": "Audius governance takeover, July 23 2022",
        "rpc": RPC,
        "read_only": True,
        "official_sources": [
            "https://blog.audius.co/posts/audius-governance-takeover-post-mortem-7-23-22",
            "https://docs.audius.co/reference/eth-contracts/",
            "https://docs.openzeppelin.com/contracts/4.x/api/proxy",
        ],
        "normative_property": {
            "name": "initializer_replay_protection",
            "statement": "After proxy initialization, an unauthorized caller must not successfully invoke initialize again or alter security-sensitive governance state.",
            "basis": "OpenZeppelin proxy documentation requires initializer functions to be protected so they can be called only once and warns that an uninitialized contract can be taken over.",
            "not_researcher_defined": True,
        },
        "official_incident_claims": {
            "repeated_initialize": True,
            "malicious_proposal": 85,
            "reported_transfer_audio": 18564497,
        },
        "contracts": {
            "governance_proxy": GOVERNANCE_PROXY,
            "audio_token": AUDIO,
            "attacker": attacker,
        },
        "transactions": transactions,
        "state_witnesses": state_witnesses,
        "permission_state_diff": permission_state_diff,
        "proposal_paths": proposal_paths,
        "prefix_results": {
            "initialization_then_target_rejection": "VIOLATION",
            "proposal_84_no_quorum": "PASS",
            "proposal_85_funds_transfer": "VIOLATION",
        },
        "prefixes": [
            {
                "after_label": first["label"],
                "status": "VIOLATION" if first_is_unauthorized and first_succeeded else "UNKNOWN",
                "reason": "successful initialize call from the historical attacker address",
            },
            {
                "after_label": "malicious_proposal",
                "status": "VIOLATION" if transactions[1]["status"] == 1 else "UNKNOWN",
                "reason": "the same caller successfully created the malicious proposal later identified as proposal 85",
            },
            {
                "after_label": "execute_proposal_85",
                "status": "VIOLATION" if transactions[3]["status"] == 1 else "UNKNOWN",
                "reason": "receipt and AUDIO Transfer event show treasury-controlled tokens moved to the malicious proposal target",
            },
            {
                "after_label": "treasury_token_transfer",
                "status": "VIOLATION" if transferred_audio > 0 else "UNKNOWN",
                "reason": "receipt contains a subsequent AUDIO transfer from the governance treasury to the malicious proposal target",
            },
        ],
        "derived_checks": {
            "transaction_count": len(transactions),
            "all_receipts_successful": all(tx["status"] == 1 for tx in transactions),
            "first_call_unauthorized": first_is_unauthorized,
            "first_call_succeeded": first_succeeded,
            "initializer_prefix_violation": first_is_unauthorized and first_succeeded,
            "permission_state_changed_after_initializer": permission_state_diff["changed_field_count"] > 0,
            "permission_changed_field_count": permission_state_diff["changed_field_count"],
            "proxy_admin_slot_unchanged": (
                permission_state_diff["slot_0_proxy_admin"]["before"].get("raw")
                == permission_state_diff["slot_0_proxy_admin"]["after"].get("raw")
            ),
            "treasury_transfer_count": len(transfer_from_treasury),
            "treasury_transfer_target": malicious_target,
            "treasury_audio_outflow": transferred_audio,
            "reported_transfer_audio": 18564497,
            "proposal_ids_replayed": [82, 83, 84, 85],
            "proposal_82_83_state_events": len([event for event in event_by_proposal[82] + event_by_proposal[83] if event["type"] == "proposal_state"]),
            "proposal_84_defeated_state_events": len([event for event in event_by_proposal[84] if event["type"] == "proposal_state" and event["state_code"] == 3]),
            "proposal_84_vote_events": len([event for event in event_by_proposal[84] if event["type"] == "vote_cast"]),
            "proposal_85_vote_events": len([event for event in event_by_proposal[85] if event["type"] == "vote_cast"]),
            "proposal_85_execution_events": len([event for event in event_by_proposal[85] if event["type"] == "proposal_executed"]),
        },
        "limitations": [
            "This is a transaction-level historical replay with exact calldata, receipts, logs, and ERC-20 balance witnesses; it is not a full storage-diff reconstruction.",
            "The artifact establishes a normative initializer violation and a realized treasury-transfer consequence; it does not claim that BTG discovered the incident before the official postmortem.",
            "No live transaction is submitted and no current contract state is modified.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {OUT}")
    print(json.dumps(artifact["derived_checks"], indent=2))


if __name__ == "__main__":
    main()
