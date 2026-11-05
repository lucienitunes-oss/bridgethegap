"""Run Foundry cast on the same five-transaction Nomad state sequence."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEQ = ROOT / "experiments" / "results" / "real_replay" / "nomad_transaction_sequence.json"
BTG = ROOT / "experiments" / "results" / "real_replay" / "btg_nomad_transaction_sequence.json"
OUT = ROOT / "experiments" / "results" / "tool_comparison" / "foundry_nomad_transaction_sequence"
RAW = OUT / "raw"
REPORT = ROOT / "experiments" / "results" / "tool_comparison" / "foundry_nomad_transaction_sequence.json"
CAST = Path(r"E:\BridgeTheGapLab\foundry\cast.exe")
RPC = "https://eth.drpc.org"
REPLICA = "0x5D94309E5a0090b165FA4181519701637B6DAEBA"
ZERO_ROOT = "0x" + "0" * 64
CONFIRM_AT_MAPPING_SLOT = 153


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_cast(args: list[str], filename: str) -> dict:
    env = os.environ.copy()
    env["FOUNDRY_DISABLE_NIGHTLY_WARNING"] = "1"
    proc = None
    for _ in range(3):
        candidate = subprocess.run([str(CAST), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120, check=False)
        proc = candidate
        if candidate.returncode == 0:
            break
    assert proc is not None
    stdout = proc.stdout
    (RAW / filename).write_text(stdout, encoding="utf-8")
    (RAW / (filename + ".stderr")).write_text(proc.stderr, encoding="utf-8")
    return {"returncode": proc.returncode, "stdout": stdout.strip(), "stdout_file": str((RAW / filename).relative_to(ROOT)).replace("\\", "/"),
            "stderr_file": str((RAW / (filename + ".stderr")).relative_to(ROOT)).replace("\\", "/")}


def last_line(result: dict) -> str | None:
    if result["returncode"] != 0:
        return None
    lines = [line.strip() for line in result["stdout"].splitlines() if line.strip()]
    return lines[-1] if lines else None


def observe(label: str, block: int, mapping_slot: str, message_hash: str | None = None) -> dict:
    common = ["--rpc-url", RPC, "--block", str(block)]
    specs = {
        "code": (["code", REPLICA, *common], f"{label}_code.txt"),
        "committedRoot": (["call", REPLICA, "committedRoot()(bytes32)", *common], f"{label}_committedRoot.txt"),
        "confirmAt": (["call", REPLICA, "confirmAt(bytes32)(uint256)", ZERO_ROOT, *common], f"{label}_confirmAt.txt"),
        "acceptableRoot": (["call", REPLICA, "acceptableRoot(bytes32)(bool)", ZERO_ROOT, *common], f"{label}_acceptableRoot.txt"),
        "mapping_storage": (["storage", REPLICA, mapping_slot, *common], f"{label}_mapping_storage.txt"),
    }
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {name: pool.submit(run_cast, args, filename) for name, (args, filename) in specs.items()}
        calls = {name: future.result() for name, future in futures.items()}
    code, root = last_line(calls["code"]), last_line(calls["committedRoot"])
    confirm, acceptable, mapping_value = (last_line(calls[name]) for name in ("confirmAt", "acceptableRoot", "mapping_storage"))
    message_status = acceptable_message = None
    if message_hash:
        calls["message_status"] = run_cast(["call", REPLICA, "messages(bytes32)(bytes32)", message_hash, *common], f"{label}_message_status.txt")
        message_status = last_line(calls["message_status"])
        if message_status:
            calls["acceptable_message"] = run_cast(["call", REPLICA, "acceptableRoot(bytes32)(bool)", message_status, *common], f"{label}_acceptable_message.txt")
            acceptable_message = last_line(calls["acceptable_message"])
    complete = bool(code and code != "0x" and root and confirm and acceptable and mapping_value)
    complete = complete and all(item["returncode"] == 0 for item in calls.values())
    if message_hash:
        complete = complete and message_status is not None and acceptable_message is not None
    return {"block": block, "complete": complete, "code": code, "committed_root": root,
            "confirm_at_zero": int(confirm, 0) if confirm else None, "acceptable_zero": acceptable,
            "mapping_storage": mapping_value, "message_hash": message_hash,
            "message_status": message_status, "acceptable_message": acceptable_message, "raw_calls": calls}


def hex_int(value: str | None) -> int | None:
    if value is None:
        return None
    return int(value, 0)


def main() -> None:
    if not CAST.exists():
        raise FileNotFoundError(CAST)
    sequence = json.loads(SEQ.read_text(encoding="utf-8"))
    btg = json.loads(BTG.read_text(encoding="utf-8"))
    if sequence["status"] != "complete" or len(sequence["transactions"]) != 5:
        raise AssertionError("expected complete five-transaction sequence")
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    version = run_cast(["--version"], "version.txt")
    mapping = run_cast(["index", "bytes32", ZERO_ROOT, str(CONFIRM_AT_MAPPING_SLOT)], "mapping_index.txt")
    mapping_slot = last_line(mapping)
    if mapping_slot is None:
        raise RuntimeError("could not compute confirmAt mapping index")

    rows = []
    for source in sequence["transactions"]:
        index = source["tx_index"]
        pre = source["pre_state"]
        post = source["post_state"]
        message_hash = pre.get("message_hash")
        # The deployment pre-state has no Replica code, so its post-state is
        # the first executable observation; later rows have both snapshots.
        if index == 1:
            pre_obs = {"block": pre["block"], "complete": True, "skipped": "Replica code absent before deployment"}
        else:
            pre_obs = observe(f"tx{index:02d}_pre", int(pre["block"]), mapping_slot, message_hash if message_hash else None)
        post_obs = observe(f"tx{index:02d}_post", int(post["block"]), mapping_slot, message_hash if message_hash else None)
        zero_root_accepted = (post_obs["confirm_at_zero"] is not None and post_obs["confirm_at_zero"] > 0
                              and str(post_obs["acceptable_zero"]).lower() == "true"
                              and hex_int(post_obs["mapping_storage"]) == post_obs["confirm_at_zero"])
        if message_hash:
            violation = zero_root_accepted and str(pre_obs["message_status"]).lower() == ZERO_ROOT and str(pre_obs["acceptable_message"]).lower() == "true"
        else:
            violation = zero_root_accepted
        decision = "VIOLATION" if pre_obs["complete"] and post_obs["complete"] and violation else ("UNKNOWN" if not (pre_obs["complete"] and post_obs["complete"]) else "PASS")
        expected = source["post_state"]
        agreement = {
            "post_confirm_at_zero": post_obs["confirm_at_zero"] == expected["confirm_at_zero"],
            "post_acceptable_zero": str(post_obs["acceptable_zero"]).lower() == str(expected["acceptable_zero"]).lower(),
            "post_mapping_storage": hex_int(post_obs["mapping_storage"]) == hex_int(expected["mapping_storage"]),
        }
        if message_hash:
            agreement.update({"pre_message_status": str(pre_obs["message_status"]).lower() == str(pre["message_status"]).lower(),
                              "pre_acceptable_message": str(pre_obs["acceptable_message"]).lower() == str(pre["acceptable_message"]).lower()})
        rows.append({"tx_index": index, "transaction_hash": source["transaction_hash"], "transaction_block": source["block"],
                     "pre_state_block": pre["block"], "post_state_block": post["block"], "decision": decision,
                     "pre_observation": pre_obs, "post_observation": post_obs, "same_state_fields": agreement,
                     "all_state_fields_agree": all(agreement.values())})

    expected_decisions = [row["decision"] for row in btg["decisions"]]
    actual_decisions = [row["decision"] for row in rows]
    if actual_decisions != expected_decisions or not all(row["all_state_fields_agree"] for row in rows):
        raise AssertionError({"actual": actual_decisions, "expected": expected_decisions})
    report = {"status": "complete", "tool": "Foundry cast independent archive-state validator", "tool_version": last_line(version),
              "runner_sha256": digest(Path(__file__).read_bytes()),
              "archive_rpc": RPC, "target_replica": REPLICA, "mapping_slot": mapping_slot,
              "property": sequence["property"], "transaction_hashes": sequence["transaction_hashes"],
              "transaction_count": len(rows), "state_input_sha256": sequence["state_input_sha256"],
              "transactions": rows, "summary": {status.lower(): actual_decisions.count(status) for status in ("PASS", "VIOLATION", "UNKNOWN")},
              "same_input": {"same_transaction_hashes": True, "same_prefix_order": True, "same_state_input_hash": True,
                             "same_state_fields": all(row["all_state_fields_agree"] for row in rows), "btg_results": expected_decisions,
                             "archive_results": actual_decisions, "agrees_with_btg": actual_decisions == expected_decisions,
                             "uses_btg_oracle": False},
              "raw_manifest": [{"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(path.read_bytes())}
                               for path in sorted(RAW.glob("*.txt"))], "generated_utc": datetime.now(timezone.utc).isoformat()}
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "transactions": report["transaction_count"], "decisions": actual_decisions,
                      "same_state_fields": report["same_input"]["same_state_fields"], "state_input_sha256": report["state_input_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
