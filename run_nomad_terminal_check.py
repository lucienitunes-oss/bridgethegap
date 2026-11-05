"""Independent terminal-only projection over the trace-derived Nomad input."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "experiments" / "results" / "real_replay" / "nomad_transaction_sequence.json"
OUTPUT = ROOT / "experiments" / "results" / "tool_comparison" / "nomad_terminal_check.json"


def main() -> None:
    sequence = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = sequence["transactions"]
    state_input = [{"tx_index": row["tx_index"], "transaction_hash": row["transaction_hash"], "block": row["block"], "pre_state": row["pre_state"], "post_state": row["post_state"], "effects": row["effects"]} for row in rows]
    state_hash = hashlib.sha256(json.dumps(state_input, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    final = rows[-1]["post_state"]
    decision = "VIOLATION" if final["confirm_at_zero"] == 1 and final["acceptable_zero"] == "true" and int(final["mapping_storage"], 16) == 1 else "PASS"
    output = {"status": "complete", "tool": "independent terminal accepted-root projection",
              "property": "the final observed accepted root must not be the zero root",
              "state_input_sha256": state_hash, "transaction_hashes": sequence["transaction_hashes"],
              "final_post_state": final, "decision": decision,
              "same_input": state_hash == sequence["state_input_sha256"],
              "source": str(SOURCE.relative_to(ROOT)).replace("\\", "/")}
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "decision": decision, "state_input_sha256": state_hash, "same_input": output["same_input"]}, indent=2))
    assert output["same_input"]


if __name__ == "__main__":
    main()
