"""Replay the same governance calldata across the Proposal 29 repair boundary.

The calls are read-only ``eth_call`` requests with a state override.  They do
not mutate a public chain.  The calldata is copied from the later historical
Proposal 94 owner update, while the caller is the aliased owner required by
Proposal 29.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from time import sleep

from web3 import Web3


ROOT = Path(__file__).resolve().parent.parent
ADDITIONAL = ROOT / "experiments" / "results" / "real_replay" / "additional_crosschain_cases.json"
PROPOSAL94 = ROOT / "experiments" / "results" / "real_replay" / "proposal94_replay.json"
OUTPUT = ROOT / "experiments" / "results" / "real_replay" / "proposal29_isolated_call.json"

RPC = "https://arb1.arbitrum.io/rpc"
FACTORY = Web3.to_checksum_address("0x1F98431c8aD98523631AE4a59f267346ea31F984")
ALIASED_OWNER = Web3.to_checksum_address("0x2BAD8182C09F50c8318d769245beA52C32Be46CD")


def call_with_owner_override(w3: Web3, calldata: str, owner: str, label: str) -> dict:
    request = {"from": ALIASED_OWNER, "to": FACTORY, "data": calldata}
    owner_word = "0x" + "00" * 12 + owner[2:].lower()
    # Uniswap V3Factory stores Ownable's owner in slot 3 in the deployed code.
    override = {FACTORY: {"state": {"0x" + "0" * 63 + "3": owner_word}}}
    for attempt in range(1, 5):
        try:
            result = w3.manager.request_blocking("eth_call", [request, "latest", override])
            return_data = result.hex() if hasattr(result, "hex") else result
            return {
                "status": "PASS",
                "label": label,
                "attempt": attempt,
                "request": request,
                "state_override": {"owner_slot": 3, "owner_value": owner_word},
                "return_data": return_data,
            }
        except Exception as exc:
            if attempt == 4:
                return {
                    "status": "REVERT",
                    "label": label,
                    "attempt": attempt,
                    "request": request,
                    "state_override": {"owner_slot": 3, "owner_value": owner_word},
                    "error": str(exc)[:1000],
                }
            sleep(0.5 * attempt)
    raise AssertionError("unreachable")


def main() -> None:
    additional = json.loads(ADDITIONAL.read_text(encoding="utf-8"))
    case = next(item for item in additional["cases"] if item["proposal_id"] == 29)
    pre_state = case["steps"][1]["evidence"]
    pre_block = int(pre_state["before_block"])
    post_block = int(pre_state["after_block"])

    proposal94 = json.loads(PROPOSAL94.read_text(encoding="utf-8"))
    operations = proposal94["chains"]["arbitrum"]["transaction_level_evidence"]["operations"]
    owner_update = next(item for item in operations if item["operation"] == "V3Factory.setOwner")
    calldata = owner_update["input_hex"]
    if not calldata.startswith("0x"):
        calldata = "0x" + calldata
    historical_tx = owner_update["transaction_hash"]

    w3 = Web3(Web3.HTTPProvider(RPC, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise RuntimeError("Arbitrum archive RPC unavailable")

    before_owner = pre_state["before"]
    after_owner = pre_state["after"]
    before = call_with_owner_override(w3, calldata, before_owner, "before_repair")
    after = call_with_owner_override(w3, calldata, after_owner, "after_repair")
    code = w3.eth.get_code(FACTORY, block_identifier="latest")
    same_calldata = before["request"]["data"].lower() == after["request"]["data"].lower()
    same_caller = before["request"]["from"].lower() == after["request"]["from"].lower()
    output = {
        "status": "complete",
        "read_only": True,
        "rpc": RPC,
        "bytecode": {
            "block": "latest",
            "address": FACTORY,
            "sha256": hashlib.sha256(bytes(code)).hexdigest(),
            "length": len(code),
        },
        "case": "uniswap_proposal_29_isolated_authorization_replay",
        "property": "the aliased owner must be able to execute the same governance calldata",
        "input": {
            "factory": FACTORY,
            "caller": ALIASED_OWNER,
            "calldata": calldata,
            "calldata_source_transaction": historical_tx,
            "method": "V3Factory.setOwner(address)",
            "pre_repair_block": pre_block,
            "post_repair_block": post_block,
            "state_source": "saved committed owner witnesses; injected into eth_call state override",
            "owner_storage_slot": 3,
        },
        "state": {
            "owner_before_repair": before_owner,
            "owner_after_repair": after_owner,
            "expected_owner_before": pre_state["expected_before"],
            "expected_owner_after": pre_state["expected_after"],
        },
        "calls": {"before_repair": before, "after_repair": after},
        "conclusion": {
            "same_calldata": same_calldata,
            "same_caller": same_caller,
            "before_repair_reverts": before["status"] == "REVERT",
            "after_repair_succeeds": after["status"] == "PASS",
            "isolated_replay_passed": same_calldata and same_caller and before["status"] == "REVERT" and after["status"] == "PASS",
            "reproduction_mode": "real deployed target bytecode with saved historical owner states overridden at latest call context",
        },
    }
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["conclusion"], indent=2))
    assert output["conclusion"]["isolated_replay_passed"]


if __name__ == "__main__":
    main()
