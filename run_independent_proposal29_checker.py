"""Independently recompute the Proposal 29 prefix decisions.

This file deliberately does not import BTG's oracle or decision runner.  It
consumes only the saved transaction-level witnesses and applies the published
owner-repair property to the same four historical boundaries.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "experiments" / "results" / "real_replay" / "additional_crosschain_cases.json"
OUTPUT = ROOT / "experiments" / "results" / "tool_comparison" / "independent_proposal29_checker.json"

PASS = "PASS"
VIOLATION = "VIOLATION"
UNKNOWN = "UNKNOWN"


def same(left: object, right: object) -> bool:
    return isinstance(left, str) and isinstance(right, str) and left.lower() == right.lower()


def classify(case: dict) -> list[dict]:
    expected_before = case["contracts"].get("arbitrum_unaliased_owner")
    expected_after = case["contracts"].get("arbitrum_aliased_owner")
    if not expected_before or not expected_after:
        # Older saved files carry the values in the state witness instead.
        state = case["steps"][1]["evidence"]
        expected_before = state.get("expected_before")
        expected_after = state.get("expected_after")

    dispatch = case["steps"][0]["evidence"]
    dispatch_ok = (
        dispatch.get("status") == 1
        and dispatch.get("transaction_hash") == case.get("execution_tx")
        and str(dispatch.get("input_selector", "")).lower().removeprefix("0x") == "fe0d94c1"
    )

    pre = case["steps"][1]["evidence"]
    pre_ok = (
        pre.get("status") == "complete"
        and same(pre.get("before"), expected_before)
        and pre.get("changed") is True
    )

    post = case["steps"][2]["evidence"]
    event = post.get("event", {})
    post_ok = (
        post.get("status") == "complete"
        and same(post.get("after"), expected_after)
        and same(event.get("transaction_hash"), post.get("event", {}).get("transaction_hash"))
        and post.get("changed") is True
    )

    use = case["steps"][3]["evidence"]
    use_ok = (
        use.get("status") == PASS
        and use.get("receipt_status") == 1
        and same(use.get("from"), expected_after)
        and same(use.get("owner_before", {}).get("value"), expected_after)
        and use.get("owner_after", {}).get("value")
    )

    return [
        {
            "index": 1,
            "boundary": "l1_security_repair_dispatch",
            "transaction_hash": dispatch.get("transaction_hash"),
            "status": PASS if dispatch_ok else UNKNOWN,
            "reason": "the saved L1 repair transaction succeeded with the declared proposal executor"
            if dispatch_ok else "L1 receipt, proposal binding, or calldata evidence is incomplete",
        },
        {
            "index": 2,
            "boundary": "arbitrum_pre_repair_owner_state",
            "transaction_hash": pre.get("event", {}).get("transaction_hash"),
            "status": VIOLATION if pre_ok else UNKNOWN,
            "reason": "committed owner is the unaliased Timelock before the repair boundary"
            if pre_ok else "pre-repair owner evidence is incomplete",
        },
        {
            "index": 3,
            "boundary": "arbitrum_post_repair_owner_state",
            "transaction_hash": event.get("transaction_hash"),
            "status": PASS if post_ok else UNKNOWN,
            "reason": "OwnerChanged records the required aliased owner after repair"
            if post_ok else "post-repair owner evidence is incomplete",
        },
        {
            "index": 4,
            "boundary": "later_proposal_94_governance_use",
            "transaction_hash": use.get("transaction_hash"),
            "status": PASS if use_ok else UNKNOWN,
            "reason": "a later Proposal 94 call is executed by the repaired owner"
            if use_ok else "later governance-use evidence is incomplete",
        },
    ]


def main() -> None:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    case = next(item for item in payload["cases"] if item["proposal_id"] == 29)
    rows = classify(case)
    output = {
        "tool": "Independent Proposal 29 prefix checker",
        "status": "complete",
        "implementation": "standalone evidence predicate; no BTG oracle import",
        "input": {
            "proposal_id": case["proposal_id"],
            "proposal_url": case["proposal_url"],
            "property": case["property"],
            "prefix_order": [row["step"] for row in case["steps"]],
            "transaction_hashes": [
                row.get("transaction_hash") or row.get("evidence", {}).get("event", {}).get("transaction_hash")
                for row in case["steps"]
            ],
        },
        "prefix_decisions": rows,
        "summary": {
            "pass": sum(row["status"] == PASS for row in rows),
            "violation": sum(row["status"] == VIOLATION for row in rows),
            "unknown": sum(row["status"] == UNKNOWN for row in rows),
        },
        "comparison": {
            "btg_prefix_decisions": [row["status"] for row in case["steps"]],
            "independent_prefix_decisions": [row["status"] for row in rows],
            "same_decisions": [row["status"] for row in case["steps"]]
            == [row["status"] for row in rows],
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], indent=2))
    assert output["comparison"]["same_decisions"]


if __name__ == "__main__":
    main()
