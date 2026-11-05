"""Recompute BTG decisions from the real adapter's hashed state input."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "experiments" / "results" / "real_replay" / "nomad_transaction_sequence.json"
OUTPUT = ROOT / "experiments" / "results" / "real_replay" / "btg_nomad_transaction_sequence.json"
ZERO = "0x" + "0" * 64


def main() -> None:
    sequence = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = sequence["transactions"]
    state_input = [{"tx_index": row["tx_index"], "transaction_hash": row["transaction_hash"], "block": row["block"], "pre_state": row["pre_state"], "post_state": row["post_state"], "effects": row["effects"]} for row in rows]
    state_hash = hashlib.sha256(json.dumps(state_input, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    decisions = []
    for row in rows:
        pre, post, effects = row["pre_state"], row["post_state"], row["effects"]
        violation = (effects["receipt_status"] == 1 and post["confirm_at_zero"] == 1 and post["acceptable_zero"] == "true" and int(post["mapping_storage"], 16) == 1 and (not pre["message_hash"] or (pre["message_status"] == ZERO and pre["acceptable_message"] == "true")))
        decisions.append({"tx_index": row["tx_index"], "transaction_hash": row["transaction_hash"], "decision": "VIOLATION" if violation else "PASS"})
    output = {"status": "complete", "oracle": "BTG", "state_input_sha256": state_hash,
              "transaction_hashes": sequence["transaction_hashes"], "decisions": decisions,
              "summary": {status.lower(): sum(item["decision"] == status for item in decisions) for status in ("PASS", "VIOLATION", "UNKNOWN")},
              "same_input": state_hash == sequence["state_input_sha256"], "source": str(SOURCE.relative_to(ROOT)).replace("\\", "/")}
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "decisions": [item["decision"] for item in decisions], "state_input_sha256": state_hash, "same_input": output["same_input"]}, indent=2))
    assert output["same_input"]


if __name__ == "__main__":
    main()
