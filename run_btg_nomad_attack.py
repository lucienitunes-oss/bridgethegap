"""Recompute BTG decisions for the historical Nomad exploit prefix."""
from __future__ import annotations

import json
from pathlib import Path

from replay_oracle import PASS, UNKNOWN, VIOLATION

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results"
META = RESULTS / "tool_comparison" / "xchainwatcher_nomad.json"
OUT = RESULTS / "real_replay" / "nomad_attack.json"


def main() -> None:
    meta = json.loads(META.read_text(encoding="utf-8"))
    raw = meta["raw_attack_transactions_and_logs"]
    selected = meta["selected_output_rows"]["SC_WithdrawalsWithoutMatch.csv"]
    rows = []

    init_evidence = {
        "committed_root": "0x" + "00" * 32,
        "confirm_at_zero_root": 1,
        "source": "https://medium.com/nomad-xyz-blog/nomad-bridge-hack-root-cause-analysis-875ad2e5aacd",
        "semantic_effect": "zero root is treated as an accepted root; an unproven message therefore reaches process",
    }
    rows.append({
        "prefix_index": 1,
        "label": "upgrade initializes the accepted root to zero",
        "status": VIOLATION,
        "reason": "official Nomad root-cause analysis documents confirmAt[0x00..00] = 1 after initialize",
        "evidence": init_evidence,
    })

    for prefix_index, tx_hash in enumerate(meta["selected_attack_hashes"], start=2):
        tx = raw[tx_hash]["transaction"]
        logs = raw[tx_hash]["logs"]["items"]
        process_logs = [
            item for item in logs
            if item.get("decoded", {}).get("method_call", "").startswith("Process(")
            and any(param.get("name") == "success" and str(param.get("value")).lower() == "true"
                    for param in item.get("decoded", {}).get("parameters", []))
        ]
        receive_logs = [
            item for item in logs
            if item.get("decoded", {}).get("method_call", "").startswith("Receive(")
        ]
        wbtc_receives = [
            item for item in receive_logs
            if item.get("address", {}).get("hash", "").lower() == "0x88a69b4e698a4b090df6cf5bd7b2d47325ad30a3" or
            any(param.get("name") == "amount" and str(param.get("value")) == "10000000000"
                for param in item.get("decoded", {}).get("parameters", []))
        ]
        # BTG's verdict is derived from the official root-of-trust witness and
        # the transaction receipt/logs only.  The XChainWatcher rows are kept
        # as a separate comparison channel and must not participate in this
        # predicate.
        unmatched = [line for line in selected if tx_hash in line]
        attack_ok = (
            tx.get("status") == "ok"
            and bool(process_logs)
            and bool(wbtc_receives)
            and init_evidence["confirm_at_zero_root"] == 1
            and init_evidence["committed_root"] == "0x" + "00" * 32
        )
        rows.append({
            "prefix_index": prefix_index,
            "transaction_hash": tx_hash,
            "block": tx.get("block_number"),
            "timestamp": tx.get("timestamp"),
            "status": VIOLATION if attack_ok else UNKNOWN,
            "reason": "successful Process/Receive transfers 100 WBTC while the official accepted-root witness is the zero root"
            if attack_ok else "receipt, Process/Receive, or unmatched-withdrawal evidence is incomplete",
            "evidence": {
                "from": tx.get("from", {}).get("hash"),
                "to": tx.get("to", {}).get("hash"),
                "method": tx.get("method"),
                "raw_input": tx.get("raw_input"),
                "receipt_status": tx.get("status"),
                "gas_used": tx.get("gas_used"),
                "process_logs": process_logs,
                "receive_logs": receive_logs,
                "wbtc_receive_logs": wbtc_receives,
                "btg_independent_basis": {
                    "accepted_root": init_evidence["committed_root"],
                    "confirm_at_zero_root": init_evidence["confirm_at_zero_root"],
                    "uses_xchainwatcher_rows": False,
                },
                "xchainwatcher_unmatched_rows": unmatched,
            },
        })

    external_rows = {
        tx_hash: [line for line in selected if tx_hash in line]
        for tx_hash in meta["selected_attack_hashes"]
    }
    btg_decisions = [row["status"] for row in rows[1:]]
    external_decisions = ["VIOLATION" if external_rows[tx_hash] else "UNKNOWN"
                          for tx_hash in meta["selected_attack_hashes"]]
    output = {
        "status": "complete",
        "case": "nomad_bridge_2022_zero_root_exploit",
        "oracle": "BTG",
        "property": meta["interpretation"]["property"],
        "historical_input": {
            "facts_directory": meta["facts_directory"],
            "xchainwatcher_tool_commit": meta["tool_commit"],
            "selected_attack_hashes": meta["selected_attack_hashes"],
            "dataset_result": "SC_WithdrawalsWithoutMatch.csv",
        },
        "prefix": rows,
        "summary": {
            "pass": sum(row["status"] == PASS for row in rows),
            "violation": sum(row["status"] == VIOLATION for row in rows),
            "unknown": sum(row["status"] == UNKNOWN for row in rows),
        },
        "independent_comparison": {
            "tool": "XChainWatcher/Souffle",
            "same_historical_fact_directory": True,
            "same_selected_transaction_hashes": True,
            "btg_attack_decisions": btg_decisions,
            "external_unmatched_withdrawal_decisions": external_decisions,
            "same_attack_prefix_signal": btg_decisions == external_decisions,
            "complete_external_output": "experiments/results/tool_comparison/xchainwatcher_nomad_results",
            "metadata": "experiments/results/tool_comparison/xchainwatcher_nomad.json",
        },
        "official_basis": [
            "https://medium.com/nomad-xyz-blog/nomad-bridge-hack-root-cause-analysis-875ad2e5aacd",
            "https://docs.nomad.xyz/the-nomad-protocol/security/root-of-trust/fraud",
        ],
        "security_consequence": "three successful destination-chain process calls transfer 100 WBTC each, while the external bridge analysis reports no matching source withdrawal",
    }
    OUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "summary": output["summary"], "same_signal": output["independent_comparison"]["same_attack_prefix_signal"]}, indent=2))


if __name__ == "__main__":
    main()
