"""Execute the same Proposal 29 follow-on calldata on two archive forks.

The two forks start at the committed Arbitrum blocks immediately before and
after the Proposal 29 owner repair.  Foundry's Anvil and cast are used as an
external sequence-execution control: the caller, target, calldata, gas
settings, deployed bytecode, and storage slot are recorded for both runs.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

from web3 import Web3

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "experiments" / "results" / "real_replay" / "proposal29_archive_fork.json"
UPSTREAM_RPC = "https://arbitrum-one.public.blastapi.io"
ANVIL = Path(r"E:\BridgeTheGapLab\foundry\anvil.exe")
CAST = Path(r"E:\BridgeTheGapLab\foundry\cast.exe")
FACTORY = Web3.to_checksum_address("0x1F98431c8aD98523631AE4a59f267346ea31F984")
CALLER = Web3.to_checksum_address("0x2BAD8182C09F50c8318d769245beA52C32Be46CD")
CALLDATA = "0x13af4035000000000000000000000000ff7ad5da31fecdc678796c88b05926db896b0699"
OWNER_SELECTOR = "0x8da5cb5b"
OWNER_SLOT = 3
PRE_BLOCK = 48_972_826
POST_BLOCK = 48_972_827
GAS_PRICE = 100_000_000
GAS_LIMIT = 100_000


def rpc(w3: Web3, method: str, params: list) -> object:
    return w3.manager.request_blocking(method, params)


def hex_value(value: int) -> str:
    return hex(value)


def normalize_log(log: dict) -> dict:
    return {
        "address": log["address"],
        "topics": [topic.hex() for topic in log["topics"]],
        "data": log["data"].hex(),
        "blockNumber": log.get("blockNumber"),
        "transactionHash": log.get("transactionHash").hex() if log.get("transactionHash") else None,
        "transactionIndex": log.get("transactionIndex"),
        "logIndex": log.get("logIndex"),
    }


def local_tx(w3: Web3, tx_hash: str) -> dict:
    tx = w3.eth.get_transaction(tx_hash)
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    return {
        "transaction": {
            "hash": tx["hash"].hex(),
            "nonce": tx["nonce"],
            "from": tx["from"],
            "to": tx["to"],
            "value": tx["value"],
            "input": tx["input"].hex(),
            "gas": tx["gas"],
            "gasPrice": tx.get("gasPrice"),
            "type": tx.get("type"),
        },
        "receipt": {
            "transactionHash": receipt["transactionHash"].hex(),
            "transactionIndex": receipt["transactionIndex"],
            "blockHash": receipt["blockHash"].hex(),
            "blockNumber": receipt["blockNumber"],
            "from": receipt["from"],
            "to": receipt["to"],
            "gasUsed": receipt["gasUsed"],
            "cumulativeGasUsed": receipt["cumulativeGasUsed"],
            "effectiveGasPrice": receipt.get("effectiveGasPrice"),
            "status": receipt["status"],
            "logsBloom": receipt["logsBloom"].hex(),
            "logs": [normalize_log(log) for log in receipt["logs"]],
        },
    }


def owner(w3: Web3, block: int | str = "latest") -> str:
    raw = w3.eth.call({"to": FACTORY, "data": OWNER_SELECTOR}, block_identifier=block)
    return Web3.to_checksum_address("0x" + raw.hex()[-40:])


def code_witness(w3: Web3, block: int) -> dict:
    code = bytes(w3.eth.get_code(FACTORY, block_identifier=block))
    storage = w3.eth.get_storage_at(FACTORY, OWNER_SLOT, block_identifier=block)
    return {
        "block": block,
        "address": FACTORY,
        "code_sha256": hashlib.sha256(code).hexdigest(),
        "code_length": len(code),
        "owner_storage_slot": OWNER_SLOT,
        "owner_storage_value": storage.hex(),
        "owner_call": owner(w3, block),
    }


def run_version(binary: Path) -> str:
    result = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=30)
    return (result.stdout or result.stderr).strip()


def start_fork(block: int, port: int) -> tuple[subprocess.Popen, Web3]:
    command = [
        str(ANVIL), "--fork-url", UPSTREAM_RPC, "--fork-block-number", str(block),
        "--port", str(port), "--silent",
    ]
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{port}", request_kwargs={"timeout": 10}))
    deadline = time.time() + 45
    while time.time() < deadline:
        if w3.is_connected():
            return process, w3
        if process.poll() is not None:
            raise RuntimeError(f"Anvil exited with code {process.returncode}")
        time.sleep(0.5)
    process.terminate()
    raise TimeoutError(f"Anvil did not start for block {block}")


def execute_on_fork(block: int, port: int, upstream: Web3) -> dict:
    process, w3 = start_fork(block, port)
    try:
        initial = code_witness(w3, block)
        rpc(w3, "anvil_impersonateAccount", [CALLER])
        rpc(w3, "anvil_setBalance", [CALLER, hex_value(10**20)])
        rpc_url = f"http://127.0.0.1:{port}"
        command = [
            str(CAST), "send", FACTORY, "--data", CALLDATA, "--from", CALLER,
            "--unlocked", "--legacy", "--gas-price", str(GAS_PRICE),
            "--gas-limit", str(GAS_LIMIT), "--rpc-url", rpc_url, "--json",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        combined = (result.stdout or "") + (result.stderr or "")
        json_match = re.search(r"\{.*\}", result.stdout or "", re.DOTALL)
        cast_json = json.loads(json_match.group(0)) if json_match else None
        tx_hash = cast_json.get("transactionHash") if cast_json else None
        execution = local_tx(w3, tx_hash) if tx_hash else None
        latest_block = w3.eth.block_number
        final_owner = owner(w3, "latest")
        return {
            "fork_block": block,
            "fork_rpc": rpc_url,
            "initial_state": initial,
            "request": {
                "from": CALLER,
                "to": FACTORY,
                "data": CALLDATA,
                "gas": GAS_LIMIT,
                "gasPrice": GAS_PRICE,
            },
            "cast_command": command,
            "cast_returncode": result.returncode,
            "cast_json": cast_json,
            "cast_output": combined[-4000:],
            "execution": execution,
            "latest_block": latest_block,
            "final_owner": final_owner,
            "status": execution["receipt"]["status"] if execution else 0,
        }
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def main() -> None:
    if not ANVIL.exists() or not CAST.exists():
        raise FileNotFoundError("Foundry Anvil/cast installation is unavailable")
    upstream = Web3(Web3.HTTPProvider(UPSTREAM_RPC, request_kwargs={"timeout": 30}))
    if not upstream.is_connected():
        raise RuntimeError("Arbitrum archive RPC unavailable")
    pre_upstream = code_witness(upstream, PRE_BLOCK)
    post_upstream = code_witness(upstream, POST_BLOCK)
    pre = execute_on_fork(PRE_BLOCK, 18546, upstream)
    post = execute_on_fork(POST_BLOCK, 18547, upstream)
    output = {
        "status": "complete",
        "tool": "Foundry Anvil + cast external archive-fork sequence execution control",
        "tool_version": {"anvil": run_version(ANVIL), "cast": run_version(CAST)},
        "read_only_public_chain": True,
        "upstream_archive_rpc": UPSTREAM_RPC,
        "case": "uniswap_proposal_29_same_calldata_before_after_repair",
        "property": "the repaired aliased owner must be able to execute the same governance calldata",
        "input": {
            "proposal_id": 29,
            "target": FACTORY,
            "caller": CALLER,
            "calldata": CALLDATA,
            "method": "V3Factory.setOwner(address)",
            "repair_boundary": {"before_block": PRE_BLOCK, "after_block": POST_BLOCK},
            "same_target": True,
            "same_caller": True,
            "same_calldata": True,
        },
        "historical_code_and_storage": {
            "upstream_before": pre_upstream,
            "upstream_after": post_upstream,
            "code_hash_same": pre_upstream["code_sha256"] == post_upstream["code_sha256"],
            "owner_changed": pre_upstream["owner_call"].lower() != post_upstream["owner_call"].lower(),
        },
        "runs": {"before_repair": pre, "after_repair": post},
        "conclusion": {
            "before_repair_reverts": pre["status"] == 0,
            "after_repair_succeeds": post["status"] == 1,
            "same_calldata": pre["request"]["data"].lower() == post["request"]["data"].lower(),
            "same_caller": pre["request"]["from"].lower() == post["request"]["from"].lower(),
            "same_target": pre["request"]["to"].lower() == post["request"]["to"].lower(),
            "archive_fork_replay_passed": pre["status"] == 0 and post["status"] == 1,
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["conclusion"], indent=2))
    assert output["conclusion"]["archive_fork_replay_passed"]


if __name__ == "__main__":
    main()
