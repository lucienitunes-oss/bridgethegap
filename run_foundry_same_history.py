"""Run Foundry cast against the exact six-transaction Proposal 94 history.

The external tool fetches each raw receipt and transaction, then queries the
two declared attributes at the committed prefix boundary.  The small adapter
applies the paper's saved case-study predicate to those independently fetched
observations.  OP/Base deposit transactions are system transactions, so cast
cannot locally re-execute them; archive RPC state reads and receipt ordering
are retained instead.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPLAY = ROOT / "experiments" / "results" / "real_replay" / "proposal94_replay.json"
OUT = ROOT / "experiments" / "results" / "tool_comparison" / "foundry_cast_proposal94"
CAST = Path(r"E:\BridgeTheGapLab\foundry\cast.exe")


def run_cast(args: list[str], raw_path: Path) -> tuple[int, str, str, object | None]:
    env = os.environ.copy()
    env["FOUNDRY_DISABLE_NIGHTLY_WARNING"] = "1"
    proc = subprocess.run(
        [str(CAST), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    raw_path.write_text(proc.stdout, encoding="utf-8")
    raw_path.with_suffix(raw_path.suffix + ".stderr").write_text(proc.stderr, encoding="utf-8")
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        parsed = None
    return proc.returncode, proc.stdout, proc.stderr, parsed


def first_call_value(parsed: object) -> str | None:
    if not isinstance(parsed, list) or not parsed:
        return None
    value = parsed[0]
    return value if isinstance(value, str) else None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    rows = replay["cross_domain_prefix"]
    property_name = replay["policy"]["name"]
    decisions: list[dict[str, object]] = []
    command_count = 0
    all_ok = CAST.exists()

    version_code, version_stdout, version_stderr, _ = run_cast(
        ["--version"], OUT / "cast_version.txt"
    )
    command_count += 1
    version = version_stdout.strip()
    if version_code != 0:
        all_ok = False

    for index, row in enumerate(rows, start=1):
        chain = replay["chains"][row["chain"]]
        rpc = chain["rpc"]
        block = int(row["block"])
        operation = row["operation"]
        tx_hash = row["transaction_hash"]
        folder = OUT / f"prefix_{index:02d}_{row['chain']}"
        folder.mkdir(parents=True, exist_ok=True)

        receipt_code, receipt_stdout, receipt_stderr, receipt = run_cast(
            ["receipt", "--json", "--rpc-url", rpc, tx_hash], folder / "receipt.json"
        )
        tx_code, tx_stdout, tx_stderr, tx = run_cast(
            ["tx", "--json", "--rpc-url", rpc, tx_hash], folder / "transaction.json"
        )
        command_count += 2

        # When the first V3 update and the V2 update share a block, the V2
        # value after the first prefix is read from the preceding block.  The
        # second transaction can use the committed block for both fields.
        v3_block = block
        v2_block = block - 1 if operation.startswith("V3Factory") else block
        calls: dict[str, object] = {}
        observed: dict[str, str | None] = {}
        for name, address, signature, query_block in (
            ("v3_owner", chain["v3_factory"], "owner()(address)", v3_block),
            ("v2_fee_to", chain["v2_factory"], "feeTo()(address)", v2_block),
        ):
            call_code, call_stdout, call_stderr, call = run_cast(
                [
                    "call",
                    "--json",
                    "--rpc-url",
                    rpc,
                    address,
                    signature,
                    "--block",
                    str(query_block),
                ],
                folder / f"{name}.json",
            )
            command_count += 1
            value = first_call_value(call)
            observed[name] = value
            calls[name] = {
                "address": address,
                "signature": signature,
                "block": query_block,
                "return_code": call_code,
                "value": value,
                "raw_output": f"prefix_{index:02d}_{row['chain']}/{name}.json",
                "raw_stderr": f"prefix_{index:02d}_{row['chain']}/{name}.json.stderr",
            }
            if call_code != 0 or value is None:
                all_ok = False

        expected = {
            "v3_owner": chain["expected_v3_owner"],
            "v2_fee_to": chain["expected_v2_fee_to"],
        }
        complete = (
            receipt_code == 0
            and tx_code == 0
            and isinstance(receipt, dict)
            and isinstance(tx, dict)
            and observed["v3_owner"] is not None
            and observed["v2_fee_to"] is not None
        )
        if not complete:
            status = "UNKNOWN"
            reason = "receipt, transaction, or historical attribute output is incomplete"
        else:
            matches = all(
                str(observed[name]).lower() == str(expected[name]).lower()
                for name in expected
            )
            status = "PASS" if matches else "VIOLATION"
            reason = "both target fields match" if matches else "one or more target fields differ"

        receipt_hash = receipt.get("transactionHash") if isinstance(receipt, dict) else None
        tx_data = tx.get("data", {}) if isinstance(tx, dict) else {}
        tx_hash_echo = tx_data.get("hash") if isinstance(tx_data, dict) else None
        decisions.append(
            {
                "index": index,
                "chain": row["chain"],
                "operation": operation,
                "transaction_hash": tx_hash,
                "block": block,
                "receipt_status": receipt.get("status") if isinstance(receipt, dict) else None,
                "receipt_hash": receipt_hash,
                "transaction_hash_echo": tx_hash_echo,
                "receipt_return_code": receipt_code,
                "transaction_return_code": tx_code,
                "state_query_blocks": {"v3_owner": v3_block, "v2_fee_to": v2_block},
                "observed": observed,
                "expected": expected,
                "status": status,
                "reason": reason,
                "raw_receipt": f"prefix_{index:02d}_{row['chain']}/receipt.json",
                "raw_receipt_stderr": f"prefix_{index:02d}_{row['chain']}/receipt.json.stderr",
                "raw_transaction": f"prefix_{index:02d}_{row['chain']}/transaction.json",
                "raw_transaction_stderr": f"prefix_{index:02d}_{row['chain']}/transaction.json.stderr",
                "state_queries": calls,
            }
        )
        if receipt_code != 0 or tx_code != 0:
            all_ok = False
        if receipt_hash and receipt_hash.lower().removeprefix("0x") != tx_hash.lower().removeprefix("0x"):
            all_ok = False
        if tx_hash_echo and tx_hash_echo.lower() != tx_hash.lower():
            all_ok = False

    summary = {
        "pass": sum(row["status"] == "PASS" for row in decisions),
        "violation": sum(row["status"] == "VIOLATION" for row in decisions),
        "unknown": sum(row["status"] == "UNKNOWN" for row in decisions),
    }
    btg_statuses = [row["prefix_oracle"]["status"] for row in rows]
    cast_statuses = [row["status"] for row in decisions]
    output = {
        "tool": "Foundry cast",
        "status": "complete" if all_ok and summary["unknown"] == 0 else "incomplete",
        "tool_version": version,
        "repository": "https://github.com/foundry-rs/foundry",
        "executable": str(CAST),
        "input": {
            "proposal_id": 94,
            "proposal_page_sha256": replay["proposal_page_sha256"],
            "property": property_name,
            "transaction_hashes": [row["transaction_hash"] for row in rows],
            "prefix_order": "saved cross_domain_prefix order",
        },
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "command_count": command_count,
        "decisions": decisions,
        "summary": summary,
        "comparison": {
            "btg_statuses": btg_statuses,
            "cast_adapter_statuses": cast_statuses,
            "same_decisions": btg_statuses == cast_statuses,
            "terminal_status": cast_statuses[-1] if cast_statuses else "UNKNOWN",
        },
        "limitations": [
            "cast cannot locally re-execute OP/Base deposit system transactions; raw receipts and archive state queries are retained.",
            "For a same-block V3-first prefix, the untouched V2 attribute is read at block-1 and the changed V3 attribute at the committed block.",
            "The case-study predicate is evaluated by this thin adapter; cast supplies the external chain data and transaction/state boundary evidence.",
        ],
        "raw_tool_version_stderr": version_stderr,
    }
    (OUT / "foundry_cast_proposal94.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: output[k] for k in ("tool", "status", "tool_version", "command_count", "summary", "comparison")}, indent=2))


if __name__ == "__main__":
    main()
