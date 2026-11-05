"""Extract Nomad action effects and a transaction-level state sequence.

The adapter reads real calldata and receipts from the archive RPC, decodes
Process/Receive logs, and obtains pre/post storage changes from Geth's
prestateTracer diff. It does not use a hand-written overwrite fixture.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import time

from web3 import Web3

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results" / "real_replay"
RAW = RESULTS / "nomad_transaction_sequence_raw"
OUTPUT = RESULTS / "nomad_transaction_sequence.json"
RPC = "https://eth.drpc.org"
REPLICA = Web3.to_checksum_address("0x5D94309E5a0090b165FA4181519701637B6DAEBA")
ZERO_ROOT = "0x" + "0" * 64
CONFIRM_AT_SLOT = 153
MESSAGES_SLOT = 154
DEPLOYMENT = "0x99662dacfb4b963479b159fc43c2b4d048562104fe154a4d0c2519ada72e50bf"
UPGRADE = "0x7bccd64f4c4d5f6f545c2edf904857e6ddb460532fc0ac7eb5ac175cd21e56b1"
ATTACKS = [
    "0x61497a1a8a8659a06358e130ea590e1eed8956edbd99dbb2048cfb46850a8f17",
    "0x40163166dfeaab8ee80e7b0acc62768cef84b7047b42b09827b29a8d77f383a9",
    "0xb1fe26cc8892f58eb468f5208baaf38bac422b5752cca0b9c8a871855d63ae28",
]
PROCESS_TOPIC = "0x" + Web3.keccak(text="Process(bytes32,bool,bytes)").hex()
RECEIVE_TOPIC = "0x" + Web3.keccak(text="Receive(uint64,address,address,address,uint256)").hex()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request(w3: Web3, method: str, params: list, name: str) -> object:
    result = None
    for attempt in range(4):
        try:
            result = w3.provider.make_request(method, params)
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1.0 + attempt)
    assert result is not None
    (RAW / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if "error" in result:
        raise RuntimeError(f"{method}: {result['error']}")
    return result["result"]


def call(w3: Web3, signature: str, args: list, block: int, name: str) -> str:
    selector = Web3.keccak(text=signature)[:4]
    encoded = b"".join(bytes.fromhex(str(arg)[2:].zfill(64)) for arg in args)
    for attempt in range(4):
        try:
            result = w3.eth.call({"to": REPLICA, "data": "0x" + (selector + encoded).hex()}, block_identifier=block)
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1.0 + attempt)
    value = "0x" + result.hex()
    (RAW / f"{name}.json").write_text(json.dumps({"block": block, "value": value}) + "\n", encoding="utf-8")
    return value


def padded_int(raw: str | None) -> int | None:
    return int(raw, 16) if raw else None


def bool_word(raw: str | None) -> str | None:
    return "true" if raw and raw.lower().endswith("1") else ("false" if raw else None)


def mapping_slot(key: str, slot: int) -> str:
    return "0x" + Web3.keccak(bytes.fromhex(key[2:].zfill(64) + f"{slot:064x}")).hex()


def account(trace: dict, phase: str) -> dict:
    accounts = trace.get(phase, {})
    return accounts.get(REPLICA.lower(), accounts.get(REPLICA, {}))


def storage_value(acct: dict, slot: str, default: str = "0x" + "0" * 64) -> str:
    value = acct.get("storage", {}).get(slot.lower(), acct.get("storage", {}).get(slot))
    if isinstance(value, dict):
        value = value.get("*", {}).get("to") if value.get("*") else None
    return value or default


def logs_for(receipt: dict) -> tuple[list[dict], list[dict]]:
    process, receive = [], []
    for log in receipt.get("logs", []):
        topics = [str(x).lower() for x in log.get("topics", [])]
        if topics and topics[0] == PROCESS_TOPIC.lower():
            process.append({"address": log["address"], "message_hash": topics[1], "success": int(topics[2], 16) != 0})
        if topics and topics[0] == RECEIVE_TOPIC.lower():
            data = str(log.get("data", "0x"))[2:]
            receive.append({"address": log["address"], "token": "0x" + topics[2][-40:], "recipient": "0x" + topics[3][-40:], "amount": int(data[-64:], 16)})
    return process, receive


def trace_state(w3: Web3, tx_hash: str) -> dict:
    return request(w3, "debug_traceTransaction", [tx_hash, {"tracer": "prestateTracer", "tracerConfig": {"diffMode": True}}], f"{tx_hash[2:10]}_trace")


def common_state(w3: Web3, block: int, name: str) -> dict:
    committed = call(w3, "committedRoot()", [], block, f"{name}_committed_root")
    confirm = call(w3, "confirmAt(bytes32)", [ZERO_ROOT], block, f"{name}_confirm_at")
    acceptable = call(w3, "acceptableRoot(bytes32)", [ZERO_ROOT], block, f"{name}_acceptable_zero")
    mapping_key = mapping_slot(ZERO_ROOT, CONFIRM_AT_SLOT)
    mapping_raw = "0x" + w3.eth.get_storage_at(REPLICA, int(mapping_key, 16), block).hex()
    (RAW / f"{name}_mapping_storage.json").write_text(json.dumps({"block": block, "slot": mapping_key, "value": mapping_raw}) + "\n", encoding="utf-8")
    return {"committed_root": committed, "confirm_at_zero": padded_int(confirm), "acceptable_zero": bool_word(acceptable), "mapping_storage": mapping_raw, "block": block}


def normalize_tx(w3: Web3, tx_hash: str, index: int) -> dict:
    tx = request(w3, "eth_getTransactionByHash", [tx_hash], f"{index:02d}_{tx_hash[2:10]}_transaction")
    receipt = request(w3, "eth_getTransactionReceipt", [tx_hash], f"{index:02d}_{tx_hash[2:10]}_receipt")
    trace = trace_state(w3, tx_hash)
    block = int(receipt["blockNumber"], 16)
    process, receive = logs_for(receipt)
    message_hash = process[0]["message_hash"] if process else None
    message_slot = mapping_slot(message_hash, MESSAGES_SLOT) if message_hash else None
    pre_account, post_account = account(trace, "pre"), account(trace, "post")
    pre_block = block - 1
    # The deployment has no callable Replica code in its pre-state. Its
    # pre-state fields are therefore obtained from the trace account, while
    # all later transactions have archive calls on both sides of the tx.
    if tx_hash == DEPLOYMENT:
        pre_common = {"committed_root": None, "confirm_at_zero": None, "acceptable_zero": None,
                      "mapping_storage": "0x" + "0" * 64, "block": pre_block}
    else:
        pre_common = common_state(w3, pre_block, f"{index:02d}_{tx_hash[2:10]}_pre")
    post_common = common_state(w3, block, f"{index:02d}_{tx_hash[2:10]}_post")
    pre_message = storage_value(pre_account, message_slot) if message_slot else None
    post_message = storage_value(post_account, message_slot) if message_slot else None
    message_acceptable_pre = call(w3, "acceptableRoot(bytes32)", [pre_message], pre_block, f"{index:02d}_{tx_hash[2:10]}_acceptable_message_pre") if pre_message else None
    message_acceptable_post = call(w3, "acceptableRoot(bytes32)", [post_message], block, f"{index:02d}_{tx_hash[2:10]}_acceptable_message_post") if post_message else None
    changed = {}
    for slot in set(pre_account.get("storage", {})) | set(post_account.get("storage", {})):
        before = storage_value(pre_account, slot)
        after = storage_value(post_account, slot)
        if before != after:
            changed[slot] = {"before": before, "after": after}
    status = int(receipt.get("status", "0x0"), 16)
    pre_state = {**pre_common, "message_hash": message_hash,
        "message_status_pre": pre_message, "message_status_post": post_message,
        "acceptable_message_pre": bool_word(message_acceptable_pre), "acceptable_message_post": bool_word(message_acceptable_post)}
    post_state = {**post_common, "message_hash": message_hash,
        "message_status_pre": pre_message, "message_status_post": post_message,
        "acceptable_message_pre": bool_word(message_acceptable_pre), "acceptable_message_post": bool_word(message_acceptable_post)}
    # The deployment row is classified from its executable post-state; it does
    # not need a message hash because the invariant is about whether zero is an
    # accepted root once Replica code exists. Process rows additionally bind
    # the accepted-root observation to their pre-state message evidence.
    executable_zero_root = status == 1 and post_common["confirm_at_zero"] == 1 and post_common["acceptable_zero"] == "true" and int(post_common["mapping_storage"], 16) == 1
    message_context = not message_hash or (pre_message == ZERO_ROOT and bool_word(message_acceptable_pre) == "true")
    property_violation = executable_zero_root and message_context
    reads = ["accepted_root", "confirmAt[zero]", "acceptableRoot[zero]"] + (["messages[messageHash]", "acceptableRoot[messageStatus]"] if message_hash else [])
    writes = ["Replica.storage." + slot for slot in changed]
    if message_slot:
        writes.append("messages[" + message_hash + "]")
    event_effects = ["Process(messageHash)" for _ in process] + [f"Receive({item['amount']})" for item in receive]
    effects = {"calldata": tx.get("input"), "selector": tx.get("input", "0x")[:10], "receipt_status": status,
               "logs": {"process": process, "receive": receive}, "storage_diff": changed,
               "reads": reads, "writes": sorted(set(writes)), "event_effects": event_effects,
               "property_observations": ["accepted_root"] + (["processed_message"] if message_hash else [])}
    return {
        "tx_index": index, "transaction_hash": tx_hash, "block": block, "transaction_index": int(receipt["transactionIndex"], 16),
        "transaction": tx, "receipt": receipt, "trace": trace,
        "pre_state": {**pre_state, "message_status": pre_message, "acceptable_message": bool_word(message_acceptable_pre)},
        "post_state": {**post_state, "message_status": post_message, "acceptable_message": bool_word(message_acceptable_post)},
        "effects": effects, "btg_decision": "VIOLATION" if property_violation else "PASS",
        "complete_observation": bool(receipt and trace and post_common["committed_root"] and post_common["confirm_at_zero"] is not None and post_common["acceptable_zero"] is not None),
    }


def build_graph(rows: list[dict]) -> dict:
    graph = {str(row["tx_index"]): set() for row in rows}
    for left in rows:
        for right in rows:
            if left["tx_index"] >= right["tx_index"]:
                continue
            left_keys = set(left["effects"]["writes"]) | set(left["effects"]["property_observations"])
            right_keys = set(right["effects"]["writes"]) | set(right["effects"]["property_observations"])
            if left_keys & right_keys:
                graph[str(left["tx_index"])].add(right["tx_index"])
                graph[str(right["tx_index"])].add(left["tx_index"])
    return {key: sorted(value) for key, value in graph.items()}


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    w3 = Web3(Web3.HTTPProvider(RPC, request_kwargs={"timeout": 180}))
    if not w3.is_connected():
        raise RuntimeError("Nomad archive RPC unavailable")
    hashes = [DEPLOYMENT, UPGRADE, *ATTACKS]
    rows = [normalize_tx(w3, tx_hash, index) for index, tx_hash in enumerate(hashes, start=1)]
    for row in rows:
        if not row["complete_observation"]:
            raise AssertionError(f"incomplete observation {row['tx_index']}")
    state_input = [{"tx_index": row["tx_index"], "transaction_hash": row["transaction_hash"], "block": row["block"], "pre_state": row["pre_state"], "post_state": row["post_state"], "effects": row["effects"]} for row in rows]
    state_hash = sha(json.dumps(state_input, sort_keys=True, separators=(",", ":")).encode())
    final = rows[-1]["post_state"]
    terminal = "VIOLATION" if final["confirm_at_zero"] == 1 and final["acceptable_zero"] == "true" and int(final["mapping_storage"], 16) == 1 else "PASS"
    output = {"status": "complete", "adapter": "Nomad calldata/receipt/log/storage-diff adapter", "rpc": RPC,
              "target": REPLICA, "property": "once Replica is executable, the zero root must not satisfy the accepted-root predicate",
              "protocol_slots": {"confirmAt": CONFIRM_AT_SLOT, "messages": MESSAGES_SLOT},
              "transaction_hashes": hashes, "state_input_sha256": state_hash,
              "dependency_graph": build_graph(rows), "transactions": rows,
              "analysis": {"btg_results": [row["btg_decision"] for row in rows],
                           "terminal_result": terminal, "terminal_input_sha256": state_hash,
                           "all_complete": all(row["complete_observation"] for row in rows)},
              "generated_utc": datetime.now(timezone.utc).isoformat(),
              "source_sha256": sha(Path(__file__).read_bytes())}
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "transactions": len(rows), "btg": output["analysis"]["btg_results"], "terminal": terminal, "state_input_sha256": state_hash}, indent=2))


if __name__ == "__main__":
    main()
