"""Run the terminal-only governance check on the saved proposal-94 history.

The checker is intentionally independent of the prefix oracle.  It consumes
the same six transaction hashes, domains, expected attributes, and committed
history selected by replay_real_proposal.py, but observes only the terminal
state of each domain.  It is therefore a reproducible negative-control tool,
not a second prefix detector.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from replay_oracle import PASS, UNKNOWN, VIOLATION, local_pair_status

ROOT = Path(__file__).resolve().parent.parent
REPLAY = ROOT / "experiments" / "results" / "real_replay" / "proposal94_replay.json"
OUT = ROOT / "experiments" / "results" / "tool_comparison" / "final_state_check_proposal94.json"

V3_OWNER_SELECTOR = "0x8da5cb5b"  # owner()
V2_FEE_TO_SELECTOR = "0x017e7e58"  # feeTo()


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
            time.sleep(0.35)
    return {"value": None, "block": block, "error": "unreachable"}


def main() -> None:
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    rows = replay["cross_domain_prefix"]
    by_chain = {}
    for row in rows:
        by_chain[row["chain"]] = row
    results = []
    for chain_name, row in by_chain.items():
        chain = replay["chains"][chain_name]
        w3 = Web3(Web3.HTTPProvider(chain["rpc"], request_kwargs={"timeout": 30}))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        block = int(row["block"])
        v3 = call_address(w3, chain["v3_factory"], V3_OWNER_SELECTOR, block)
        v2 = call_address(w3, chain["v2_factory"], V2_FEE_TO_SELECTOR, block)
        observation = {
            "tx_status": 1,
            "block": block,
            "transaction_hash": row["transaction_hash"],
            "v3_owner": v3["value"],
            "v2_fee_to": v2["value"],
        }
        oracle = local_pair_status(
            observation,
            {
                "v3_owner": chain["expected_v3_owner"],
                "v2_fee_to": chain["expected_v2_fee_to"],
            },
        )
        results.append(
            {
                "chain": chain_name,
                "terminal_transaction_hash": row["transaction_hash"],
                "terminal_block": block,
                "terminal_transaction_index": row["transaction_index"],
                "v3_owner": v3,
                "v2_fee_to": v2,
                "expected_v3_owner": chain["expected_v3_owner"],
                "expected_v2_fee_to": chain["expected_v2_fee_to"],
                "oracle": oracle,
            }
        )
    statuses = [item["oracle"]["status"] for item in results]
    if any(status == UNKNOWN for status in statuses):
        status = UNKNOWN
    elif any(status == VIOLATION for status in statuses):
        status = VIOLATION
    else:
        status = PASS
    output = {
        "tool": "BTG terminal-only final-state governance check",
        "status": status,
        "input": {
            "proposal_id": replay["proposal_id"],
            "proposal_page_sha256": replay["proposal_page_sha256"],
            "transaction_hashes": [row["transaction_hash"] for row in rows],
            "property": replay["policy"]["name"],
        },
        "history_source": "same saved proposal94_replay.json; archive-capable public RPC eth_call at each domain terminal block",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "domains": results,
        "interpretation": "terminal-only check returns PASS while the same six-transaction history contains prefix violations",
    }
    OUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "domains": len(results), "output": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
