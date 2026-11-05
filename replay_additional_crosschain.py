"""Replay three additional public Uniswap cross-chain governance paths.

The script is deliberately small and read-only. Proposal 69 has archived
L1 receipt evidence and archived Base state witnesses. Proposal 29 has an
officially documented Arbitrum bridge misconfiguration. Its replay joins the
L1 repair dispatch, the distinct destination OwnerChanged transaction, and a
later Proposal 94 Arbitrum governance transaction that uses the repaired
owner. The resulting path is a cross-transaction operational witness.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from web3 import Web3

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "experiments" / "results" / "real_replay" / "additional_crosschain_cases.json"
PROPOSAL94_REPLAY = ROOT / "experiments" / "results" / "real_replay" / "proposal94_replay.json"
ETH_RPC = "https://eth.drpc.org"
BASE_RPC = "https://base.drpc.org"
ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"
CELO_RPC = "https://forno.celo.org"

GOVERNOR = Web3.to_checksum_address("0x408ED6354d4973f66138C91495F2f2FCbd8724C3")
BASE_FACTORY = Web3.to_checksum_address("0x33128a8fC17869897dCE68Ed026d694621f6fDFD")
BASE_SENDER = Web3.to_checksum_address("0x866E82a600A1414e583f7F13623F1aC5d58b0Afa")
ARBITRUM_FACTORY = Web3.to_checksum_address("0x1F98431c8aD98523631AE4a59f267346ea31F984")
ARBITRUM_UNALIASED_OWNER = Web3.to_checksum_address("0x1a9C8182C09F50C8318d769245beA52c32BE35BC")
ARBITRUM_ALIASED_OWNER = Web3.to_checksum_address("0x2BAD8182C09F50c8318d769245beA52C32Be46CD")
OWNER_CHANGED_TOPIC = "0xb532073b38c83145e3e5135377a08bf9aab55bc0fd7c1179cd4fb995d2a5159c"
CELO_FACTORY = Web3.to_checksum_address("0xafe208a311b21f13ef87e33a90049fc17a7acdec")
CELO_OPTICS_OWNER = Web3.to_checksum_address("0x5ee2ba07742d9276b2f51ee4ad949016b7f164c1")
CELO_WORMHOLE_OWNER = Web3.to_checksum_address("0x0eb863541278308c3a64f8e908bc646e27bfd071")
CELO_PROPOSAL43_DESTINATION_TX = "0xa4e2f1aa3cf4d457e0238cd9afdb4ad7ebe96bc19238dfac079b82eebd5542e9"
CELO_PROPOSAL43_DESTINATION_BLOCK = 21_165_468

PROPOSALS = {
    "uniswap_69_base_fee_tiers": {
        "proposal_id": 69,
        "proposal_url": "https://vote.uniswapfoundation.org/proposals/69",
        "execution_tx": "0xc9246c12f4f78f74be3cb2fba49cc1386b07b9484a4c39e28833b75fc44de441",
        "property": "Base V3 fee tiers 200, 300, and 400 are enabled after the corresponding cross-chain calls; pending delivery is safe under the normal-asynchronous policy.",
        "kind": "normal_async_safe",
    },
    "uniswap_29_arbitrum_bridge_repair": {
        "proposal_id": 29,
        "proposal_url": "https://vote.uniswapfoundation.org/proposals/29",
        "execution_tx": "0x990f88c0558b8a37ec784c6d6d70a650bbc3df817ff42272c4e296ff80523cd2",
        "property": "The Arbitrum bridge factory owner must be the aliased cross-chain owner required by the published bridge repair at every committed destination boundary.",
        "kind": "cross_transaction_owner_repair_and_use",
    },
    "uniswap_43_celo_bridge_authority_migration": {
        "proposal_id": 43,
        "proposal_url": "https://vote.uniswapfoundation.org/proposals/43",
        "execution_tx": "0xd348519fac24c98ca7173dac83a611330713ccc9c20be5ebba8a3266b2b04d28",
        "property": "After the approved Celo bridge migration, the V3Factory owner must be the Wormhole receiver; the retired Optics receiver must not retain authorization to change the factory.",
        "kind": "normative_bridge_authority_migration",
        "official_basis": {
            "url": "https://vote.uniswapfoundation.org/proposals/43",
            "requirement": "The proposal explicitly replaces the Celo V3Factory owner from the existing Optics bridge receiver with the new Wormhole bridge receiver, after noting that Optics was not approved by the Bridge Assessment Committee.",
            "security_consequence": "The owner transition changes who can invoke the factory's privileged setOwner operation; the archived calls below show revocation of the retired route and authorization of the new route.",
        },
    },
}


def utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def normalize_log(log) -> dict:
    def as_hex(value):
        if hasattr(value, "hex"):
            return value.hex()
        return value

    return {
        "address": log["address"],
        "topics": [as_hex(topic) for topic in log["topics"]],
        "data": as_hex(log["data"]),
        "block": log.get("blockNumber"),
        "transaction_hash": log.get("transactionHash").hex() if log.get("transactionHash") else None,
        "transaction_index": log.get("transactionIndex"),
        "log_index": log.get("logIndex"),
    }


def tx_receipt(w3: Web3, tx_hash: str) -> dict:
    try:
        tx = w3.eth.get_transaction(tx_hash)
    except Exception:
        # Celo's public RPC returns the transaction object with a legacy
        # ``hash`` field that some Web3 formatters reject.  Preserve that raw
        # object rather than dropping a receipt that is available over JSON-RPC.
        raw_tx = w3.manager.request_blocking("eth_getTransactionByHash", [tx_hash])
        if not raw_tx:
            raise
        tx = raw_tx
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    try:
        block = w3.eth.get_block(receipt["blockNumber"])
        timestamp = block["timestamp"]
    except Exception:
        raw_response = w3.provider.make_request(
            "eth_getBlockByNumber", [hex(receipt["blockNumber"]), False]
        )
        raw_block = raw_response["result"]
        timestamp = int(raw_block["timestamp"], 16)
    normalized_logs = [normalize_log(log) for log in receipt["logs"]]
    input_value = tx["input"]
    input_hex = input_value.hex() if hasattr(input_value, "hex") else input_value.removeprefix("0x")
    raw_receipt = {
        "transactionHash": receipt["transactionHash"].hex(),
        "transactionIndex": receipt["transactionIndex"],
        "blockHash": receipt["blockHash"].hex(),
        "blockNumber": receipt["blockNumber"],
        "from": receipt["from"],
        "to": receipt["to"],
        "cumulativeGasUsed": receipt["cumulativeGasUsed"],
        "gasUsed": receipt["gasUsed"],
        "effectiveGasPrice": receipt.get("effectiveGasPrice"),
        "type": receipt.get("type"),
        "status": receipt["status"],
        "logsBloom": receipt["logsBloom"].hex(),
        "logs": normalized_logs,
    }
    return {
        "transaction_hash": tx_hash,
        "block": receipt["blockNumber"],
        "timestamp": timestamp,
        "timestamp_utc": utc(timestamp),
        "transaction_index": receipt["transactionIndex"],
        "status": receipt["status"],
        "from": tx["from"],
        "to": tx["to"],
        "input_selector": "0x" + input_hex[:8],
        "input_hex": input_hex,
        "gas_used": receipt["gasUsed"],
        "receipt": raw_receipt,
        "log_count": len(normalized_logs),
        "logs": normalized_logs,
        "sender_log_count": sum(
            1 for log in receipt["logs"] if log["address"].lower() == BASE_SENDER.lower()
        ),
    }


def address_from_word(value: bytes | str) -> str:
    raw = value.hex() if isinstance(value, bytes) else value.removeprefix("0x")
    return Web3.to_checksum_address("0x" + raw[-40:])


def call_address(w3: Web3, contract: str, selector: str, block: int) -> dict:
    for attempt in range(4):
        try:
            value = w3.eth.call(
                {"to": Web3.to_checksum_address(contract), "data": selector},
                block_identifier=block,
            )
            return {"value": address_from_word(value), "block": block, "attempt": attempt + 1}
        except Exception as exc:
            if attempt == 3:
                return {"value": None, "block": block, "error": str(exc)[:240], "attempts": 4}
    return {"value": None, "block": block, "error": "unreachable"}


def fee_spacing(w3: Web3, fee: int, block: int) -> dict:
    selector = Web3.keccak(text="feeAmountTickSpacing(uint24)")[:4].hex()
    data = "0x" + selector + int(fee).to_bytes(32, "big").hex()
    try:
        raw = w3.eth.call({"to": BASE_FACTORY, "data": data}, block_identifier=block)
        return {"fee": fee, "block": block, "spacing": int(raw.hex(), 16), "raw": raw.hex()}
    except Exception as exc:
        return {"fee": fee, "block": block, "error": str(exc)[:240]}


def authorization_call(w3: Web3, caller: str, block: int) -> dict:
    target = "0000000000000000000000000000000000000001"
    data = "0x13af4035" + "000000000000000000000000" + target
    request = {"from": caller, "to": CELO_FACTORY, "data": data}
    try:
        raw = w3.eth.call(request, block_identifier=block)
        return {"status": "PASS", "block": block, "caller": caller, "request": request, "return_data": raw.hex()}
    except Exception as exc:
        return {"status": "REVERT", "block": block, "caller": caller, "request": request, "error": str(exc)[:500]}


def replay_base_case(eth: Web3, base: Web3) -> dict:
    execution = tx_receipt(eth, PROPOSALS["uniswap_69_base_fee_tiers"]["execution_tx"])
    fees = [200, 300, 400]
    before_block = 19_800_000
    after_block = 20_000_000
    before = [fee_spacing(base, fee, before_block) for fee in fees]
    after = [fee_spacing(base, fee, after_block) for fee in fees]
    expected = {200: 4, 300: 6, 400: 8}
    state_complete = all(row.get("spacing") == expected[row["fee"]] for row in after)
    state_before_disabled = all(row.get("spacing") == 0 for row in before)
    dispatch_complete = execution["status"] == 1 and execution["sender_log_count"] >= 3
    steps = [
        {
            "step": "l1_execution_and_dispatch",
            "transaction_hash": execution["transaction_hash"],
            "status": "PASS" if dispatch_complete else "UNKNOWN",
            "reason": "successful L1 execution receipt contains three Base sender logs" if dispatch_complete else "receipt or dispatch evidence incomplete",
            "evidence": execution,
        },
        {
            "step": "base_pending_prefix",
            "status": "PASS" if dispatch_complete and state_before_disabled else "UNKNOWN",
            "reason": "all three destination attributes are still disabled; normal asynchronous policy permits pending delivery",
            "evidence": {"block": before_block, "timestamp": 1726389347, "fee_tiers": before},
        },
        {
            "step": "base_all_messages_delivered",
            "status": "PASS" if state_complete else "UNKNOWN",
            "reason": "all three archived destination attributes equal the published fee-tier spacings" if state_complete else "one or more destination reads are missing or mismatched",
            "evidence": {"block": after_block, "timestamp": 1726789347, "fee_tiers": after, "expected": expected},
        },
    ]
    return {
        **PROPOSALS["uniswap_69_base_fee_tiers"],
        "rpc": {"source": ETH_RPC, "destination": BASE_RPC},
        "contracts": {"governor": GOVERNOR, "base_factory": BASE_FACTORY, "base_sender": BASE_SENDER},
        "execution": execution,
        "steps": steps,
        "btg_result": "PASS" if all(step["status"] == "PASS" for step in steps) else "UNKNOWN",
        "limitations": ["The before/after destination witnesses bracket the published L1 execution date; they are not presented as one atomic cross-chain transaction."],
    }


def replay_arbitrum_case(eth: Web3, arbitrum: Web3) -> dict:
    execution = tx_receipt(eth, PROPOSALS["uniswap_29_arbitrum_bridge_repair"]["execution_tx"])
    destination = {"status": "UNKNOWN", "contract": ARBITRUM_FACTORY}
    owner_logs = arbitrum.eth.get_logs({
        "fromBlock": 48_900_000,
        "toBlock": 49_000_000,
        "address": ARBITRUM_FACTORY,
        "topics": [OWNER_CHANGED_TOPIC],
    })
    matching = [log for log in owner_logs if len(log["topics"]) >= 3]
    if matching:
        event = matching[0]
        old_owner = Web3.to_checksum_address("0x" + event["topics"][1].hex()[-40:])
        new_owner = Web3.to_checksum_address("0x" + event["topics"][2].hex()[-40:])
        destination.update({
            "status": "complete",
            "property": "arbitrum_factory.owner",
            "before_block": event["blockNumber"] - 1,
            "after_block": event["blockNumber"],
            "before": old_owner,
            "after": new_owner,
            "expected_before": ARBITRUM_UNALIASED_OWNER,
            "expected_after": ARBITRUM_ALIASED_OWNER,
            "changed": old_owner.lower() != new_owner.lower(),
            "event": normalize_log(event),
            "reason": "OwnerChanged indexed arguments provide the historical owner transition at the repair boundary",
        })
    else:
        destination["reason"] = "no OwnerChanged event was returned for the declared historical search window"
    try:
        latest_owner = arbitrum.eth.call(
            {"to": ARBITRUM_FACTORY, "data": "0x8da5cb5b"}
        )
        destination["latest_owner"] = Web3.to_checksum_address("0x" + latest_owner.hex()[-40:])
    except Exception as exc:
        destination["latest_owner_error"] = str(exc)[:240]
    dispatch_complete = execution["status"] == 1
    follow_on = {"status": "UNKNOWN", "reason": "later Proposal 94 evidence unavailable"}
    if PROPOSAL94_REPLAY.exists():
        proposal94 = json.loads(PROPOSAL94_REPLAY.read_text(encoding="utf-8"))
        arbitrum94 = proposal94.get("chains", {}).get("arbitrum", {})
        operations = arbitrum94.get("transaction_level_evidence", {}).get("operations", [])
        later = next((item for item in operations if item.get("operation") == "V3Factory.setOwner"), None)
        if later:
            later_block = int(later["block"])
            owner_before = call_address(arbitrum, ARBITRUM_FACTORY, "0x8da5cb5b", later_block - 1)
            owner_after = call_address(arbitrum, ARBITRUM_FACTORY, "0x8da5cb5b", later_block)
            follow_ok = (
                later.get("status") == 1
                and (owner_before.get("value") or "").lower() == ARBITRUM_ALIASED_OWNER.lower()
                and owner_after.get("value")
            )
            follow_on = {
                "status": "PASS" if follow_ok else "UNKNOWN",
                "proposal_id": 94,
                "operation": later.get("operation"),
                "transaction_hash": later.get("transaction_hash"),
                "block": later_block,
                "transaction_index": later.get("transaction_index"),
                "from": later.get("from"),
                "to": later.get("to"),
                "receipt_status": later.get("status"),
                "owner_before": owner_before,
                "owner_after": owner_after,
                "reason": "later Proposal 94 setOwner executed from the repaired aliased owner" if follow_ok else "later governance evidence is incomplete",
                "evidence_window": later.get("evidence_window"),
            }
    pre_violation = (
        destination.get("status") == "complete"
        and destination.get("before", "").lower() == ARBITRUM_UNALIASED_OWNER.lower()
    )
    post_pass = (
        destination.get("status") == "complete"
        and destination.get("after", "").lower() == ARBITRUM_ALIASED_OWNER.lower()
    )
    steps = [
        {
            "step": "l1_security_repair_dispatch",
            "transaction_hash": execution["transaction_hash"],
            "status": "PASS" if dispatch_complete else "UNKNOWN",
            "reason": "the official proposal's executed L1 transaction succeeded" if dispatch_complete else "L1 execution receipt failed",
            "evidence": execution,
        },
        {
            "step": "arbitrum_pre_repair_owner_state",
            "status": "VIOLATION" if pre_violation else "UNKNOWN",
            "reason": "the historical owner was the unaliased L1 Timelock, so governance could not execute on Arbitrum" if pre_violation else destination["reason"],
            "evidence": destination,
        },
        {
            "step": "arbitrum_post_repair_owner_state",
            "status": "PASS" if post_pass else "UNKNOWN",
            "reason": "the destination OwnerChanged event records the required aliased owner" if post_pass else destination["reason"],
            "evidence": destination,
        },
        {
            "step": "later_proposal_94_governance_use",
            "transaction_hash": follow_on.get("transaction_hash"),
            "status": follow_on.get("status", "UNKNOWN"),
            "reason": follow_on.get("reason", "later governance evidence is incomplete"),
            "evidence": follow_on,
        },
    ]
    return {
        **PROPOSALS["uniswap_29_arbitrum_bridge_repair"],
        "rpc": {"source": ETH_RPC, "destination": ARBITRUM_RPC},
        "contracts": {"governor": GOVERNOR, "arbitrum_factory": ARBITRUM_FACTORY},
        "execution": execution,
        "steps": steps,
        "btg_result": "VIOLATION" if pre_violation else "UNKNOWN",
        "security_basis": "The official proposal documents that the unaliased owner left Arbitrum governance unusable. The destination OwnerChanged event records the repair, and the later Proposal 94 setOwner transaction shows the repaired alias being used by a subsequent governance action.",
        "cross_transaction_witness": {
            "l1_repair_dispatch": execution["transaction_hash"],
            "destination_repair": destination.get("event", {}).get("transaction_hash"),
            "later_governance_use": follow_on.get("transaction_hash"),
            "ordered": bool(
                destination.get("event", {}).get("block", 0) < follow_on.get("block", 0)
                if follow_on.get("block") else False
            ),
        },
        "limitations": ["The owner property is evaluated at committed transaction boundaries; the later Proposal 94 transaction is a forward use witness, not an exploit attempt."],
    }


def replay_celo_case(eth: Web3, celo: Web3) -> dict:
    """Replay Proposal 43's bridge-authority migration and authorization effect."""
    proposal = PROPOSALS["uniswap_43_celo_bridge_authority_migration"]
    execution = tx_receipt(eth, proposal["execution_tx"])
    destination = tx_receipt(celo, CELO_PROPOSAL43_DESTINATION_TX)
    before_block = CELO_PROPOSAL43_DESTINATION_BLOCK - 1
    after_block = CELO_PROPOSAL43_DESTINATION_BLOCK
    before_owner = call_address(celo, CELO_FACTORY, "0x8da5cb5b", before_block)
    after_owner = call_address(celo, CELO_FACTORY, "0x8da5cb5b", after_block)
    old_before = authorization_call(celo, CELO_OPTICS_OWNER, before_block)
    new_before = authorization_call(celo, CELO_WORMHOLE_OWNER, before_block)
    old_after = authorization_call(celo, CELO_OPTICS_OWNER, after_block)
    new_after = authorization_call(celo, CELO_WORMHOLE_OWNER, after_block)
    event = next(
        (
            log for log in destination["logs"]
            if len(log["topics"]) >= 3
            and ("0x" + log["topics"][0].removeprefix("0x")).lower() == OWNER_CHANGED_TOPIC.lower()
        ),
        None,
    )
    event_old = Web3.to_checksum_address("0x" + event["topics"][1][-40:]) if event else None
    event_new = Web3.to_checksum_address("0x" + event["topics"][2][-40:]) if event else None
    transition_ok = (
        execution["status"] == 1
        and destination["status"] == 1
        and before_owner.get("value", "").lower() == CELO_OPTICS_OWNER.lower()
        and after_owner.get("value", "").lower() == CELO_WORMHOLE_OWNER.lower()
        and event_old and event_old.lower() == CELO_OPTICS_OWNER.lower()
        and event_new and event_new.lower() == CELO_WORMHOLE_OWNER.lower()
    )
    # The authoritative permission witness is the committed owner slot plus
    # the OwnerChanged event.  The eth_call probes are retained as supporting
    # evidence, but are not used to turn an RPC-side historical trie error into
    # a false violation or false pass.
    steps = [
        {
            "step": "l1_bridge_authority_migration_dispatch",
            "transaction_hash": execution["transaction_hash"],
            "status": "PASS" if execution["status"] == 1 else "UNKNOWN",
            "reason": "Proposal 43 execution receipt succeeded" if execution["status"] == 1 else "L1 execution receipt failed",
            "evidence": execution,
        },
        {
            "step": "celo_pre_migration_authority",
            "transaction_hash": None,
            "status": "PASS" if before_owner.get("value", "").lower() == CELO_OPTICS_OWNER.lower() else "UNKNOWN",
            "reason": "the committed pre-delivery state still records the Optics receiver as owner; this is the normal asynchronous prefix before delivery",
            "evidence": {"block": before_block, "owner": before_owner, "retired_optics_authorization": old_before, "wormhole_authorization": new_before},
        },
        {
            "step": "celo_post_migration_authority",
            "transaction_hash": destination["transaction_hash"],
            "status": "PASS" if transition_ok else "UNKNOWN",
            "reason": "the destination receipt and OwnerChanged event match the official Optics-to-Wormhole migration",
            "evidence": {"destination_receipt": destination, "owner_before": before_owner, "owner_after": after_owner, "event": event, "expected_old": CELO_OPTICS_OWNER, "expected_new": CELO_WORMHOLE_OWNER},
        },
        {
            "step": "celo_retired_route_revoked",
            "transaction_hash": destination["transaction_hash"],
            "status": "PASS" if transition_ok else "UNKNOWN",
            "reason": "the committed owner transition revokes the retired Optics route" if transition_ok else "retired-route state evidence is incomplete",
            "evidence": old_after,
        },
        {
            "step": "celo_new_route_authorized",
            "transaction_hash": destination["transaction_hash"],
            "status": "PASS" if transition_ok else "UNKNOWN",
            "reason": "the committed owner transition authorizes the Wormhole route" if transition_ok else "new-route state evidence is incomplete",
            "evidence": new_after,
        },
    ]
    return {
        **proposal,
        "rpc": {"source": ETH_RPC, "destination": CELO_RPC},
        "contracts": {"celo_factory": CELO_FACTORY, "retired_optics_receiver": CELO_OPTICS_OWNER, "wormhole_receiver": CELO_WORMHOLE_OWNER},
        "execution": execution,
        "destination": destination,
        "state_witnesses": {"before": before_owner, "after": after_owner},
        "authorization_witnesses": {"before": {"optics": old_before, "wormhole": new_before}, "after": {"optics": old_after, "wormhole": new_after}},
        "steps": steps,
        "btg_result": "PASS" if transition_ok else "UNKNOWN",
        "security_basis": proposal["official_basis"],
        "limitations": ["The authorization probes use eth_call with a harmless setOwner target; they do not mutate the public Celo chain."],
    }


def main() -> None:
    eth = Web3(Web3.HTTPProvider(ETH_RPC, request_kwargs={"timeout": 30}))
    base = Web3(Web3.HTTPProvider(BASE_RPC, request_kwargs={"timeout": 30}))
    arbitrum = Web3(Web3.HTTPProvider(ARBITRUM_RPC, request_kwargs={"timeout": 30}))
    celo = Web3(Web3.HTTPProvider(CELO_RPC, request_kwargs={"timeout": 30}))
    if not eth.is_connected() or not base.is_connected() or not celo.is_connected():
        raise RuntimeError("Ethereum, Base, or Celo RPC unavailable")
    output = {
        "status": "complete",
        "read_only": True,
        "cases": [replay_base_case(eth, base), replay_arbitrum_case(eth, arbitrum), replay_celo_case(eth, celo)],
        "method": "Each status is computed from the receipt and archived state fields in this script; official proposal labels are retained only as provenance.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "cases": [(case["proposal_id"], case["btg_result"]) for case in output["cases"]]}, indent=2))


if __name__ == "__main__":
    main()
