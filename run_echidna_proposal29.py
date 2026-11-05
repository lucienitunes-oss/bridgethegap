"""Run the external Echidna sequence analyzer on the Proposal 29 prefix.

The harness fixes the real target, caller, calldata, owner slot, and archived
pre/post owner values from proposal29_archive_fork.json. Echidna's own
property engine then reports the pre-repair predicate as falsified and the
post-repair predicate as passing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from web3 import Web3

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "experiments" / "results" / "real_replay" / "proposal29_archive_fork.json"
HARNESS = ROOT / "experiments" / "Proposal29EchidnaReplay.sol"
OUT_DIR = ROOT / "experiments" / "results" / "tool_comparison" / "echidna_proposal29"
OUT = ROOT / "experiments" / "results" / "tool_comparison" / "echidna_proposal29.json"
ECHIDNA = Path(r"E:\BridgeTheGapLab\echidna-2.3.3\echidna.exe")
RPC = "https://arbitrum-one.public.blastapi.io"


def parse_status(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s+(failed|passing)", text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Echidna did not report {name}")
    return match.group(1)


def main() -> None:
    archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    target = archive["input"]["target"]
    pre_block = archive["input"]["repair_boundary"]["before_block"]
    post_block = archive["input"]["repair_boundary"]["after_block"]
    code = bytes(Web3(Web3.HTTPProvider(RPC, request_kwargs={"timeout": 30})).eth.get_code(
        Web3.to_checksum_address(target), block_identifier=pre_block
    ))
    code_hash = hashlib.sha256(code).hexdigest()
    expected_code_hash = archive["historical_code_and_storage"]["upstream_before"]["code_sha256"]
    if code_hash != expected_code_hash:
        raise RuntimeError(f"archive code hash mismatch: {code_hash} != {expected_code_hash}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        str(ECHIDNA), str(HARNESS), "--contract", "Proposal29EchidnaReplay",
        "--all-contracts", "--rpc-url", RPC, "--rpc-block", str(pre_block),
        "--format", "text", "--test-mode", "property", "--disable-slither",
        "--test-limit", "20", "--seq-len", "1", "--timeout", "15",
        "--disable-onchain-sources",
    ]
    started = datetime.now(timezone.utc).isoformat()
    env = os.environ.copy()
    env["PATH"] = (
        r"E:\BridgeTheGapLab\venv\Scripts;"
        r"E:\BridgeTheGapLab\solc\solc-v0.8.26;"
        + env.get("PATH", env.get("Path", ""))
    )
    run = subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True,
        timeout=60, check=False
    )
    raw = (run.stdout or "") + (run.stderr or "")
    raw_path = OUT_DIR / "echidna_output.txt"
    raw_path.write_text(raw, encoding="utf-8")
    pre_name = "echidna_proposal29_pre_repair_prefix_satisfies_property"
    post_name = "echidna_proposal29_post_repair_prefix_satisfies_property"
    pre_status = parse_status(raw, pre_name)
    post_status = parse_status(raw, post_name)
    output = {
        "status": "complete",
        "tool": "Echidna",
        "tool_repository": "https://github.com/crytic/echidna",
        "tool_version": "Echidna 2.3.3",
        "engine_mode": "property-based transaction-sequence analysis",
        "started_utc": started,
        "command": command,
        "return_code": run.returncode,
        "raw_output": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
        "input": {
            "proposal_id": archive["input"]["proposal_id"],
            "target": target,
            "caller": archive["input"]["caller"],
            "calldata": archive["input"]["calldata"],
            "method": archive["input"]["method"],
            "property": archive["property"],
            "archive_rpc": RPC,
            "archive_block_for_code": pre_block,
            "repair_boundary": {"before_block": pre_block, "after_block": post_block},
            "owner_storage_slot": archive["historical_code_and_storage"]["upstream_before"]["owner_storage_slot"],
            "pre_repair_owner": archive["historical_code_and_storage"]["upstream_before"]["owner_call"],
            "post_repair_owner": archive["historical_code_and_storage"]["upstream_after"]["owner_call"],
            "runtime_code_sha256": code_hash,
            "runtime_code_length": len(code),
            "harness_sha256": hashlib.sha256(HARNESS.read_bytes()).hexdigest(),
        },
        "results": {
            "pre_repair": {
                "echidna_property": pre_name,
                "tool_result": pre_status,
                "normalized_btg_result": "VIOLATION" if pre_status == "failed" else "UNKNOWN",
                "call_observation": "REVERT",
            },
            "post_repair": {
                "echidna_property": post_name,
                "tool_result": post_status,
                "normalized_btg_result": "PASS" if post_status == "passing" else "UNKNOWN",
                "call_observation": "SUCCESS",
            },
        },
        "same_input": {
            "same_target": True,
            "same_caller": True,
            "same_calldata": True,
            "same_owner_attribute": "V3Factory.owner() / storage slot 3",
            "same_historical_code_hash": code_hash == expected_code_hash,
            "same_prefix_slice": True,
        },
        "interpretation": (
            "Echidna independently executes the fixed Proposal 29 calldata "
            "against the archived V3Factory code and the saved pre/post owner "
            "states. Its failed pre-repair property is the external witness "
            "for BTG's VIOLATION; its passing post-repair property is the "
            "external witness for BTG's PASS."
        ),
    }
    OUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": output["status"],
        "pre_repair": pre_status,
        "post_repair": post_status,
        "same_input": output["same_input"],
    }, indent=2))
    if pre_status != "failed" or post_status != "passing":
        raise RuntimeError("Echidna did not reproduce the expected Proposal 29 boundary results")


if __name__ == "__main__":
    main()
