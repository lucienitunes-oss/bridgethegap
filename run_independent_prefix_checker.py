"""Run a standalone prefix checker on the saved Uniswap proposal-94 history.

This checker intentionally has no dependency on BTG's oracle implementation.
It consumes the same transaction-boundary state witnesses and recomputes the
case-study predicate with a separate implementation, preserving an
implementation-independent comparison on the same historical input.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REPLAY = ROOT / "experiments" / "results" / "real_replay" / "proposal94_replay.json"
OUT = ROOT / "experiments" / "results" / "tool_comparison" / "independent_prefix_checker_proposal94.json"


def decide(state: dict, expected: dict) -> dict:
    required = ("v3_owner", "v2_fee_to")
    if any(not state.get(name) for name in required):
        missing = [name for name in required if not state.get(name)]
        return {"status": "UNKNOWN", "reason": "missing state witness: " + ", ".join(missing)}
    matches = all(state[name].lower() == expected[name].lower() for name in required)
    return {
        "status": "PASS" if matches else "VIOLATION",
        "reason": "both target attributes match" if matches else "one or more target attributes differ",
    }


def main() -> None:
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    rows = sorted(
        replay["cross_domain_prefix"],
        key=lambda row: (row["timestamp"], row["block"], row["transaction_index"], row["transaction_hash"]),
    )
    decisions = []
    for row in rows:
        chain = replay["chains"][row["chain"]]
        state = row["state_after"]
        decision = decide(
            state,
            {
                "v3_owner": chain["expected_v3_owner"],
                "v2_fee_to": chain["expected_v2_fee_to"],
            },
        )
        decisions.append(
            {
                "index": len(decisions) + 1,
                "chain": row["chain"],
                "operation": row["operation"],
                "transaction_hash": row["transaction_hash"],
                "block": row["block"],
                "observed": {
                    "v3_owner": state.get("v3_owner"),
                    "v2_fee_to": state.get("v2_fee_to"),
                },
                "expected": {
                    "v3_owner": chain["expected_v3_owner"],
                    "v2_fee_to": chain["expected_v2_fee_to"],
                },
                **decision,
            }
        )
    terminal = []
    seen = set()
    for row in reversed(rows):
        if row["chain"] in seen:
            continue
        seen.add(row["chain"])
        chain = replay["chains"][row["chain"]]
        terminal.append(
            {
                "chain": row["chain"],
                "transaction_hash": row["transaction_hash"],
                "block": row["block"],
                **decide(
                    row["state_after"],
                    {
                        "v3_owner": chain["expected_v3_owner"],
                        "v2_fee_to": chain["expected_v2_fee_to"],
                    },
                ),
            }
        )
    output = {
        "tool": "Independent archive prefix checker",
        "status": "complete",
        "implementation": "standalone state/predicate evaluator; no BTG oracle import",
        "input": {
            "proposal_id": replay["proposal_id"],
            "proposal_page_sha256": replay["proposal_page_sha256"],
            "transaction_hashes": [row["transaction_hash"] for row in rows],
            "property": replay["policy"]["name"],
        },
        "prefix_decisions": decisions,
        "terminal_decisions": terminal,
        "summary": {
            "pass": sum(item["status"] == "PASS" for item in decisions),
            "violation": sum(item["status"] == "VIOLATION" for item in decisions),
            "unknown": sum(item["status"] == "UNKNOWN" for item in decisions),
            "terminal_status": "PASS" if all(item["status"] == "PASS" for item in terminal) else "VIOLATION",
        },
    }
    OUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], indent=2))


if __name__ == "__main__":
    main()
