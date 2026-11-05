"""Replay the observable state boundary of Uniswap proposal 94.

This is an evidence collector, not a vulnerability oracle.  It records only
states and receipts returned by public RPC endpoints and evaluates a
specification-derived local consistency property.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from replay_oracle import (
    PASS,
    VIOLATION,
    UNKNOWN,
    final_only_status,
    global_coherence_status,
    local_pair_status,
    normal_async_status,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "experiments" / "results" / "real_replay"
PROPOSAL_URL = "https://vote.uniswapfoundation.org/proposals/94"
TARGET_TIME = 1772781599  # proposal 94 execution block timestamp, UTC
OWNER_CHANGED = "0xb532073b38c83145e3e5135377a08bf9aab55bc0fd7c1179cd4fb995d2a5159c"
PROPOSAL_RE = re.compile(r"executedTransactionHash\\?\"?:\\?\"(0x[0-9a-fA-F]{64})")

CHAINS = {
    "arbitrum": {
        "rpc": "https://arb1.arbitrum.io/rpc",
        "v3_factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
        "v2_factory": "0xf1D7CC64Fb4452F05c498126312eBE29f30Fbcf9",
        "expected_v3_owner": "0xFF7aD5dA31fECdC678796c88B05926dB896b0699",
        "expected_v2_fee_to": "0x95E337C5B155385945D407f5396387D0c2a3A263",
        "event_block_hint": 438865985,
    },
    "base": {
        "rpc": "https://mainnet.base.org",
        "v3_factory": "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
        "v2_factory": "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6",
        "expected_v3_owner": "0xaBEA76658b205696d49B5F91b2a03536cB8A3bE1",
        "expected_v2_fee_to": "0x9bD25e67bF390437C8fAF480AC735a27BcF6168c",
        "event_block_hint": 42996217,
    },
    "op-mainnet": {
        "rpc": "https://mainnet.optimism.io",
        "v3_factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
        "v2_factory": "0x0c3c1c532F1e39EdF36BE9Fe0bE1410313E074Bf",
        "expected_v3_owner": "0xec23Cf5A1db3dcC6595385D28B2a4D9B52503Be4",
        "expected_v2_fee_to": "0xb13285DF724ea75f3f1E9912010B7e491dCd5EE3",
        "event_block_hint": 148591451,
    },
}


def utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def address_from_word(value: bytes | str) -> str:
    raw = value.hex() if isinstance(value, bytes) else value.removeprefix("0x")
    return Web3.to_checksum_address("0x" + raw[-40:])


def call_address(w3: Web3, contract: str, selector: str, block: int) -> dict:
    last_error = None
    for attempt in range(4):
        try:
            value = w3.eth.call(
                {"to": Web3.to_checksum_address(contract), "data": selector},
                block_identifier=block,
            )
            return {"value": address_from_word(value), "block": block, "attempt": attempt + 1}
        except Exception as exc:  # public RPCs can transiently fail on old state
            last_error = str(exc)[:240]
            time.sleep(0.35)
    return {"value": None, "block": block, "error": last_error, "attempts": 4}


def tx_receipt(w3: Web3, tx_hash: str) -> dict:
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    transaction = w3.eth.get_transaction(tx_hash)
    block = w3.eth.get_block(receipt["blockNumber"])
    return {
        "transaction_hash": tx_hash,
        "block": receipt["blockNumber"],
        "timestamp": block["timestamp"],
        "timestamp_utc": utc(block["timestamp"]),
        "status": receipt["status"],
        "transaction_index": receipt["transactionIndex"],
        "from": receipt["from"],
        "to": receipt["to"],
        "input_hex": transaction["input"].hex(),
        "input_selector": transaction["input"][:4].hex(),
        "nonce": transaction["nonce"],
        "gas_used": receipt["gasUsed"],
        "log_count": len(receipt["logs"]),
        "logs": [
            {
                "address": log["address"],
                "topics": [topic.hex() for topic in log["topics"]],
                "data": log["data"].hex(),
                "log_index": log["logIndex"],
            }
            for log in receipt["logs"]
        ],
    }


def find_owner_log(w3: Web3, chain: dict) -> dict:
    hint = chain["event_block_hint"]
    # Small chunks keep public Base/OP endpoints below their log-payload limit.
    for start in range(hint - 2500, hint + 2501, 100):
        end = start + 99
        try:
            logs = w3.eth.get_logs(
                {
                    "fromBlock": start,
                    "toBlock": end,
                    "address": Web3.to_checksum_address(chain["v3_factory"]),
                    "topics": [OWNER_CHANGED],
                }
            )
        except Exception:
            continue
        for log in logs:
            return {
                "block": log["blockNumber"],
                "transaction_hash": "0x" + log["transactionHash"].hex().removeprefix("0x"),
                "old_owner": address_from_word(log["topics"][1]),
                "new_owner": address_from_word(log["topics"][2]),
                "log_index": log["logIndex"],
            }
    raise RuntimeError("OwnerChanged event not found in bounded historical window")


def find_transaction_level_evidence(w3: Web3, chain: dict, event_block: int) -> dict:
    """Recover the two exact fee-routing calls from a narrow block neighborhood.

    OP/Base wrap the destination calls in the standard L2 messenger envelope;
    Arbitrum executes the calls directly.  The receipt and full calldata are
    retained for each matched operation so the pair is not inferred from a
    state delta alone.
    """
    v3_marker = chain["v3_factory"].lower().removeprefix("0x")
    v2_marker = chain["v2_factory"].lower().removeprefix("0x")
    owner_arg = chain["expected_v3_owner"].lower().removeprefix("0x")
    fee_to_arg = chain["expected_v2_fee_to"].lower().removeprefix("0x")
    seen = set()
    operations = []
    errors = []
    for block_number in range(event_block - 2, event_block + 3):
        try:
            block = w3.eth.get_block(block_number, full_transactions=True)
        except Exception as exc:
            errors.append(f"block {block_number}: {str(exc)[:180]}")
            continue
        for tx in block["transactions"]:
            tx_hash = "0x" + tx["hash"].hex().removeprefix("0x")
            data = "0x" + tx["input"].hex().removeprefix("0x")
            data_lower = data.lower()
            to = (tx["to"] or "").lower()
            operation = None
            if to == chain["v3_factory"].lower() and data_lower.startswith("0x13af4035"):
                if owner_arg in data_lower:
                    operation = "V3Factory.setOwner"
            elif to == chain["v2_factory"].lower() and data_lower.startswith("0xf46901ed"):
                if fee_to_arg in data_lower:
                    operation = "V2Factory.setFeeTo"
            elif to == "0x4200000000000000000000000000000000000007" and v3_marker in data_lower and "13af4035" in data_lower and owner_arg in data_lower:
                operation = "V3Factory.setOwner (messenger envelope)"
            elif to == "0x4200000000000000000000000000000000000007" and v2_marker in data_lower and "f46901ed" in data_lower and fee_to_arg in data_lower:
                operation = "V2Factory.setFeeTo (messenger envelope)"
            if operation is None or tx_hash in seen:
                continue
            seen.add(tx_hash)
            receipt = tx_receipt(w3, tx_hash)
            receipt["operation"] = operation
            receipt["evidence_window"] = {
                "from_block": event_block - 2,
                "to_block": event_block + 2,
            }
            operations.append(receipt)
    has_v3 = any(entry["operation"].startswith("V3Factory.setOwner") for entry in operations)
    has_v2 = any(entry["operation"].startswith("V2Factory.setFeeTo") for entry in operations)
    successful = all(entry["status"] == 1 for entry in operations)
    status = "PASS" if has_v3 and has_v2 and successful else "UNKNOWN"
    return {
        "status": status,
        "reason": (
            "both fee-routing operations have successful transaction receipts"
            if status == "PASS"
            else "could not prove both operations from transaction-level evidence"
        ),
        "operation_count": len(operations),
        "operations": sorted(operations, key=lambda item: (item["block"], item["transaction_hash"])),
        "atomic": False if len({entry["transaction_hash"] for entry in operations}) > 1 else None,
        "search_window": {"from_block": event_block - 2, "to_block": event_block + 2},
        "errors": errors,
    }


def replay_chain(name: str, chain: dict) -> dict:
    w3 = Web3(Web3.HTTPProvider(chain["rpc"], request_kwargs={"timeout": 30}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    event = find_owner_log(w3, chain)
    block = event["block"]
    receipt = tx_receipt(w3, event["transaction_hash"])
    before = block - 1
    after = block + 1
    v3_before = event["old_owner"]
    v3_after = event["new_owner"]
    v2_before = call_address(w3, chain["v2_factory"], "0x017e7e58", before)
    v2_after = call_address(w3, chain["v2_factory"], "0x017e7e58", after)
    transaction_level = find_transaction_level_evidence(w3, chain, block)
    observation = {
        "tx_status": receipt["status"],
        "block": receipt["block"],
        "transaction_hash": receipt["transaction_hash"],
        "v3_owner": v3_after,
        "v2_fee_to": v2_after.get("value"),
    }
    local_result = local_pair_status(
        observation,
        {
            "v3_owner": chain["expected_v3_owner"],
            "v2_fee_to": chain["expected_v2_fee_to"],
        },
    )
    local_prefix = {
        "before": {"v3_owner": v3_before, "v2_fee_to": v2_before.get("value")},
        "after": {"v3_owner": v3_after, "v2_fee_to": v2_after.get("value")},
        "v2_before_evidence": v2_before,
        "v2_after_evidence": v2_after,
        "pair_complete_after_observed_boundary": local_result["status"] == PASS,
        "oracle_observation": observation,
        "oracle_result": local_result,
    }
    return {
        "chain": name,
        "rpc": chain["rpc"],
        "v3_factory": chain["v3_factory"],
        "v2_factory": chain["v2_factory"],
        "expected_v3_owner": chain["expected_v3_owner"],
        "expected_v2_fee_to": chain["expected_v2_fee_to"],
        "owner_changed": event,
        "execution": receipt,
        "local_prefix": local_prefix,
        "local_oracle_result": local_result,
        "transaction_level_evidence": transaction_level,
        "source": "OwnerChanged log, destination receipt, and eth_call at adjacent committed blocks",
    }


def fetch_source() -> tuple[str, str]:
    from urllib.request import Request, urlopen

    request = Request(PROPOSAL_URL, headers={"User-Agent": "BTG-artifact/1.0"})
    with urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    return body, hashlib.sha256(body.encode()).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    html, source_hash = fetch_source()
    match = PROPOSAL_RE.search(html)
    if not match:
        # The page has changed its escaping twice; retain provenance but fail
        # closed instead of silently associating a different transaction.
        raise RuntimeError("Could not extract executedTransactionHash from proposal page")
    source_tx = match.group(1)
    eth = Web3(Web3.HTTPProvider("https://eth.drpc.org", request_kwargs={"timeout": 30}))
    source_execution = tx_receipt(eth, source_tx)
    chains = {}
    for name, config in CHAINS.items():
        chains[name] = replay_chain(name, config)
        time.sleep(0.2)

    ordered = sorted(
        [
            {
                "chain": name,
                "timestamp": value["execution"]["timestamp"],
                "timestamp_utc": value["execution"]["timestamp_utc"],
            }
            for name, value in chains.items()
        ],
        key=lambda item: item["timestamp"],
    )
    expected_domains = list(chains)
    activation_prefix = []
    active = []
    local_results = {}
    for item in ordered:
        chain = chains[item["chain"]]
        local_results[item["chain"]] = chain["local_oracle_result"]
        if chain["local_oracle_result"]["status"] == PASS:
            active.append(item["chain"])
        global_result = (
            global_coherence_status(active, expected_domains)
            if all(result["status"] == PASS for result in local_results.values())
            else {"status": UNKNOWN, "reason": "an observed local pair is not proven complete"}
        )
        async_result = normal_async_status(local_results, expected_domains)
        activation_prefix.append(
            {
                "after": item["chain"],
                "active_chains": list(active),
                "global_coherence": global_result,
                "normal_async": async_result,
            }
        )
    transaction_order = sorted(
        [
            {
                "chain": name,
                **operation,
            }
            for name, chain in chains.items()
            for operation in chain["transaction_level_evidence"]["operations"]
        ],
        key=lambda item: (item["timestamp"], item["block"], item["transaction_index"], item["transaction_hash"]),
    )
    transaction_prefix = []
    states = {
        name: {
            "v3_owner": chain["local_prefix"]["before"]["v3_owner"],
            "v2_fee_to": chain["local_prefix"]["before"]["v2_fee_to"],
        }
        for name, chain in chains.items()
    }
    active_after_transaction = []
    for item in transaction_order:
        state = states[item["chain"]]
        if item["operation"].startswith("V3Factory.setOwner"):
            state["v3_owner"] = chains[item["chain"]]["expected_v3_owner"]
        elif item["operation"].startswith("V2Factory.setFeeTo"):
            state["v2_fee_to"] = chains[item["chain"]]["expected_v2_fee_to"]
        observation = {
            "tx_status": item["status"],
            "block": item["block"],
            "transaction_hash": item["transaction_hash"],
            "v3_owner": state["v3_owner"],
            "v2_fee_to": state["v2_fee_to"],
        }
        local_status = local_pair_status(
            observation,
            {
                "v3_owner": chains[item["chain"]]["expected_v3_owner"],
                "v2_fee_to": chains[item["chain"]]["expected_v2_fee_to"],
            },
        )
        if local_status["status"] == PASS and item["chain"] not in active_after_transaction:
            active_after_transaction.append(item["chain"])
        global_status = global_coherence_status(active_after_transaction, expected_domains)
        # The primary oracle is the specification-derived local pair.  The
        # global rollout status is retained as a separate diagnostic and is
        # never folded into the protocol property.
        prefix_status = local_status
        transaction_prefix.append(
            {
                "chain": item["chain"],
                "operation": item["operation"],
                "transaction_hash": item["transaction_hash"],
                "block": item["block"],
                "transaction_index": item["transaction_index"],
                "status": item["status"],
                "timestamp": item["timestamp"],
                "timestamp_utc": item["timestamp_utc"],
                "state_after": dict(state),
                "local_pair_oracle": local_status,
                "global_rollout_oracle": global_status,
                "prefix_oracle": prefix_status,
                "active_domains": list(active_after_transaction),
            }
        )
    final_only = final_only_status(local_results, expected_domains)
    policy_violation = any(row["prefix_oracle"]["status"] == VIOLATION for row in transaction_prefix)
    final_only_result = final_only["status"] == PASS
    complete_evidence = all(
        chain["execution"]["status"] == 1
        and chain["local_oracle_result"]["status"] == PASS
        and chain["transaction_level_evidence"]["status"] == PASS
        for chain in chains.values()
    )
    output = {
        "status": "complete" if complete_evidence and policy_violation and final_only_result else "UNKNOWN",
        "proposal_id": 94,
        "proposal_url": PROPOSAL_URL,
        "proposal_page_sha256": source_hash,
        "executed_transaction_hash": source_tx,
        "target_time_from_prior_observation": TARGET_TIME,
        "source_execution": source_execution,
        "chains": chains,
        "cross_domain_prefix": transaction_prefix,
        "domain_prefix_summary": activation_prefix,
        "policy": {
            "name": "protocol_derived_fee_activation_consistency",
            "kind": "specification_derived_configuration_property",
            "description": "After an observed fee-activation update, the declared V3 owner and V2 feeTo must jointly match the proposal's adapter and TokenJar. The property is derived from the protocol fee-switch semantics and is checked at every transaction boundary.",
            "independent_basis": [
                "Uniswap V2 protocol-fee specification: a nonzero feeTo enables protocol-fee collection and routes it to feeTo.",
                "Uniswap V3 factory specification: owner is the authorization state for setOwner.",
                "Proposal 94 specifies the adapter and TokenJar destinations for the paired updates.",
            ],
            "prefix_violation_found": policy_violation,
            "prefix_statuses": [row["prefix_oracle"] for row in transaction_prefix],
            "final_only_result": final_only_result,
            "final_only_oracle": final_only,
            "final_only_misses_prefix": policy_violation and final_only_result,
            "local_pair_result": complete_evidence,
            "normal_async_result": all(row["normal_async"]["status"] == PASS for row in activation_prefix),
        },
        "limitations": [
            "The replay population is the three destination domains assigned to Vote 1; Celo is outside this declared subcase.",
            "The independent specifications define each component's fee and authorization semantics, but do not promise atomic cross-domain activation; the replay therefore makes no atomicity claim.",
            "No exploitability or financial-loss claim is made.",
        ],
    }
    (OUT / "proposal94_replay.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    (OUT / "proposal94_page.html").write_text(html, encoding="utf-8")
    (OUT / "summary.json").write_text(
        json.dumps(
            {
                "status": output["status"],
                "proposal_id": 94,
                "source_execution": source_execution,
                "ordered_l2_executions": ordered,
                "transaction_prefix_length": len(transaction_prefix),
                "transaction_prefix": transaction_prefix,
                "prefix_violation_found": policy_violation,
                "final_only_misses_prefix": output["policy"]["final_only_misses_prefix"],
                "local_pair_result": output["policy"]["local_pair_result"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output["policy"], indent=2))


if __name__ == "__main__":
    main()
