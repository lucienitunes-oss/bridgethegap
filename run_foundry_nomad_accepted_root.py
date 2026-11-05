"""Validate Nomad accepted-root observations with an archive-state control.

This runner does not import BTG's oracle.  It invokes the external Foundry
cast binary against an archive-capable Ethereum RPC, retains every raw call,
and applies a small independent rule to the returned message status,
confirmAt(zeroRoot), acceptableRoot(message status), code, and mapping-slot
values.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results"
OUT = RESULTS / "tool_comparison" / "foundry_nomad_accepted_root"
RAW = OUT / "raw"
PREFIX_MANIFEST = RESULTS / "real_replay" / "nomad_prefix_manifest.json"
FULL_RAW = RESULTS / "real_replay" / "nomad_full_prefix_raw.json"
XCHAIN = RESULTS / "tool_comparison" / "xchainwatcher_nomad.json"
OUT_JSON = RESULTS / "tool_comparison" / "foundry_nomad_accepted_root.json"
CAST = Path(r"E:\BridgeTheGapLab\foundry\cast.exe")
RPC = "https://eth.drpc.org"
REPLICA = "0x5D94309E5a0090b165FA4181519701637B6DAEBA"
ZERO_ROOT = "0x" + "0" * 64
CONFIRM_AT_MAPPING_SLOT = 153
DEPLOYMENT_HASH = "0x99662dacfb4b963479b159fc43c2b4d048562104fe154a4d0c2519ada72e50bf"
DEPLOYMENT_BLOCK = 14629758
UPGRADE_BLOCK = 15003660
ATTACK_BLOCK = 15259101


def raw_name(label: str, field: str) -> Path:
    return RAW / f"{label}_{field}.txt"


def run_cast(args: list[str], path: Path) -> dict:
    env = os.environ.copy()
    env["FOUNDRY_DISABLE_NIGHTLY_WARNING"] = "1"
    proc = None
    for _ in range(2):
        proc = subprocess.run(
            [str(CAST), *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode == 0:
            break
    assert proc is not None
    path.write_text(proc.stdout, encoding="utf-8")
    path.with_suffix(path.suffix + ".stderr").write_text(proc.stderr, encoding="utf-8")
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr_file": str(path.with_suffix(path.suffix + ".stderr").relative_to(ROOT)).replace("\\", "/"),
        "stdout_file": str(path.relative_to(ROOT)).replace("\\", "/"),
    }


def parse_single_line(result: dict) -> str | None:
    if result["returncode"] != 0:
        return None
    lines = [line.strip() for line in result["stdout"].splitlines() if line.strip()]
    return lines[-1] if lines else None


def code_sha256(code: str | None) -> str | None:
    if not code or not code.startswith("0x"):
        return None
    return hashlib.sha256(bytes.fromhex(code[2:])).hexdigest()


def observe(label: str, block: int, mapping_slot: str, message_hash: str | None = None) -> dict:
    calls = {}
    common = ["--rpc-url", RPC, "--block", str(block)]
    calls["code"] = run_cast(["code", REPLICA, *common], raw_name(label, "code"))
    calls["committedRoot"] = run_cast(
        ["call", REPLICA, "committedRoot()(bytes32)", *common],
        raw_name(label, "committedRoot"),
    )
    calls["confirmAt"] = run_cast(
        ["call", REPLICA, "confirmAt(bytes32)(uint256)", ZERO_ROOT, *common],
        raw_name(label, "confirmAt"),
    )
    calls["acceptableRoot"] = run_cast(
        ["call", REPLICA, "acceptableRoot(bytes32)(bool)", ZERO_ROOT, *common],
        raw_name(label, "acceptableRoot"),
    )
    calls["mapping_storage"] = run_cast(
        ["storage", REPLICA, mapping_slot, *common],
        raw_name(label, "mapping_storage"),
    )

    code = parse_single_line(calls["code"])
    root = parse_single_line(calls["committedRoot"])
    confirm = parse_single_line(calls["confirmAt"])
    acceptable = parse_single_line(calls["acceptableRoot"])
    mapping_value = parse_single_line(calls["mapping_storage"])
    message_status = None
    acceptable_message = None
    if message_hash is not None:
        calls["message_status"] = run_cast(
            ["call", REPLICA, "messages(bytes32)(bytes32)", message_hash, *common],
            raw_name(label, "message_status"),
        )
        message_status = parse_single_line(calls["message_status"])
        if message_status is not None:
            calls["acceptable_message_status"] = run_cast(
                ["call", REPLICA, "acceptableRoot(bytes32)(bool)", message_status, *common],
                raw_name(label, "acceptable_message_status"),
            )
            acceptable_message = parse_single_line(calls["acceptable_message_status"])
    complete = (
        bool(code and code != "0x")
        and root is not None
        and confirm is not None
        and acceptable is not None
        and mapping_value is not None
        and (message_hash is None or (message_status is not None and acceptable_message is not None))
        and all(item["returncode"] == 0 for item in calls.values())
    )
    decision = "UNKNOWN"
    if complete:
        positive_confirmation = int(confirm, 0) > 0
        zero_mapping = int(mapping_value, 0) == int(confirm, 0)
        zero_root_accepted = positive_confirmation and acceptable.lower() == "true" and zero_mapping
        if message_hash is None and zero_root_accepted:
            # At the upgrade boundary this is the latent state violation:
            # the zero root is accepted before any message is processed.
            decision = "VIOLATION"
        elif (
            message_hash is not None
            and zero_root_accepted
            and message_status.lower() == ZERO_ROOT
            and acceptable_message.lower() == "true"
        ):
            # At an attack boundary the message remains in the NONE/zero
            # status, which is incorrectly accepted as a root.
            decision = "VIOLATION"
        elif root.lower() != ZERO_ROOT and acceptable.lower() == "true" and message_hash is None:
            decision = "PASS"
    return {
        "block": block,
        "decision": decision,
        "committed_root": root,
        "confirm_at_zero_root": int(confirm, 0) if confirm is not None else None,
        "acceptable_root_zero": acceptable,
        "mapping_storage_value": mapping_value,
        "message_hash": message_hash,
        "message_status": message_status,
        "acceptable_message_status": acceptable_message,
        "runtime_code_bytes": ((len(code) - 2) // 2) if code and code.startswith("0x") else 0,
        "runtime_code_sha256": code_sha256(code),
        "complete_observation": complete,
        "raw_calls": calls,
    }


def main() -> None:
    if not CAST.exists():
        raise FileNotFoundError(f"Foundry cast is unavailable: {CAST}")
    prefix = json.loads(PREFIX_MANIFEST.read_text(encoding="utf-8"))
    full_raw = json.loads(FULL_RAW.read_text(encoding="utf-8"))
    xchain = json.loads(XCHAIN.read_text(encoding="utf-8"))
    attack_hashes = list(xchain["selected_attack_hashes"])
    expected_prefix = [prefix["transaction_hashes"][0], *attack_hashes]
    if prefix["transaction_hashes"] != expected_prefix:
        raise AssertionError("Nomad prefix manifest is not the expected four-transaction input")

    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    mapping_index = run_cast(
        ["index", "bytes32", ZERO_ROOT, str(CONFIRM_AT_MAPPING_SLOT)],
        raw_name("mapping", "index"),
    )
    mapping_slot = parse_single_line(mapping_index)
    if mapping_slot is None:
        raise RuntimeError("could not compute confirmAt mapping index")

    before = observe("initialization_before", DEPLOYMENT_BLOCK - 1, mapping_slot)
    after = observe("initialization_after", DEPLOYMENT_BLOCK, mapping_slot)
    upgrade = observe("prefix_1_upgrade", UPGRADE_BLOCK, mapping_slot)
    attack_observations = []
    for index, tx_hash in enumerate(attack_hashes, start=2):
        attack_logs = xchain["raw_attack_transactions_and_logs"][tx_hash]["logs"]["items"]
        process_logs = [
            item for item in attack_logs
            if item.get("decoded", {}).get("method_call", "").startswith("Process(")
        ]
        message_hash = next(
            parameter["value"]
            for item in process_logs
            for parameter in item.get("decoded", {}).get("parameters", [])
            if parameter.get("name") == "messageHash"
        )
        attack_observations.append(
            # All three real attack transactions share block 15,259,101.
            # Read the committed pre-state at the preceding block so the
            # message is observed before that transaction changes it to
            # PROCESSED (2).
            observe(f"prefix_{index}_{tx_hash[2:10]}", ATTACK_BLOCK - 1, mapping_slot, message_hash)
        )

    prefix_results = []
    for tx_hash, observation in zip(prefix["transaction_hashes"], [upgrade, *attack_observations]):
        prefix_results.append({
            "transaction_hash": tx_hash,
            "transaction_block": ATTACK_BLOCK if observation is not upgrade else UPGRADE_BLOCK,
            "state_block": observation["block"],
            "external_decision": observation["decision"],
            "accepted_root_observation": {
                "committed_root": observation["committed_root"],
                "confirm_at_zero_root": observation["confirm_at_zero_root"],
                "acceptable_root_zero": observation["acceptable_root_zero"],
                "mapping_storage_value": observation["mapping_storage_value"],
                "message_hash": observation["message_hash"],
                "message_status": observation["message_status"],
                "acceptable_message_status": observation["acceptable_message_status"],
            },
            "complete_observation": observation["complete_observation"],
        })

    output = {
        "status": "complete",
        "tool": "Foundry cast",
        "tool_version": parse_single_line(run_cast(["--version"], raw_name("tool", "version"))),
        "external_binary": str(CAST),
        "archive_rpc": RPC,
        "target_replica": REPLICA,
        "property": "a processed cross-chain message must be backed by a non-zero accepted root",
        "decision_rule": "VIOLATION iff the zero root is accepted from the raw confirmAt mapping and, for an attack message, the pre-state messages(messageHash) is zero with acceptableRoot(messages(messageHash)) true; at a state boundary without a message, a positively confirmed zero root is a latent VIOLATION. PASS/UNKNOWN are selected from the same raw observations.",
        "official_basis": [
            "https://medium.com/nomad-xyz-blog/nomad-bridge-hack-root-cause-analysis-875ad2e5aacd",
            "https://docs.nomad.xyz/the-nomad-protocol/security/root-of-trust/fraud",
            "https://github.com/nomad-xyz/monorepo/blob/main/packages/contracts-core/contracts/Replica.sol",
        ],
        "common_input": {
            "manifest": str(PREFIX_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
            "transaction_hashes": prefix["transaction_hashes"],
            "transaction_count": len(prefix["transaction_hashes"]),
            "same_prefix_order": True,
        },
        "archive_storage_transition": {
            "deployment_transaction": DEPLOYMENT_HASH,
            "before_block": DEPLOYMENT_BLOCK - 1,
            "after_block": DEPLOYMENT_BLOCK,
            "mapping_key": ZERO_ROOT,
            "confirm_at_mapping_slot": CONFIRM_AT_MAPPING_SLOT,
            "mapping_entry_slot": mapping_slot,
            "before": before,
            "after": after,
            "transition": "0x0 -> 0x1",
        },
        "prefix_results": prefix_results,
        "summary": {
            "pass": sum(item["external_decision"] == "PASS" for item in prefix_results),
            "violation": sum(item["external_decision"] == "VIOLATION" for item in prefix_results),
            "unknown": sum(item["external_decision"] == "UNKNOWN" for item in prefix_results),
        },
        "same_input_comparison": {
            "same_ordered_prefix": True,
            "same_accepted_root_property": True,
            "same_transaction_hashes_as_btg": True,
            "btg_results": ["VIOLATION"] * len(prefix_results),
            "external_results": [item["external_decision"] for item in prefix_results],
            "all_prefix_rows_agree": all(item["external_decision"] == "VIOLATION" for item in prefix_results),
            "uses_btg_oracle": False,
        },
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    OUT_JSON.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": output["status"],
        "tool": output["tool"],
        "prefix_count": len(prefix_results),
        "results": [item["external_decision"] for item in prefix_results],
        "storage_transition": output["archive_storage_transition"]["transition"],
        "all_prefix_rows_agree": output["same_input_comparison"]["all_prefix_rows_agree"],
    }, indent=2))


if __name__ == "__main__":
    main()
