"""Extract action effects and property dependencies from saved Uniswap evidence."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "experiments" / "results" / "real_replay" / "additional_crosschain_cases.json"
OUT = ROOT / "experiments" / "results" / "real_replay" / "uniswap_adapter.json"
OWNER_CHANGED_TOPIC = "b532073b38c83145e3e5135377a08bf9aab55bc0fd7c1179cd4fb995d2a5159c"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def topic(log: dict) -> str:
    return str(log.get("topics", [""])[0]).removeprefix("0x").lower()


def short(value: object) -> str:
    return str(value).lower()


def receipt_effect(execution: dict) -> dict:
    effects = []
    for log in execution.get("logs", []):
        if topic(log) == OWNER_CHANGED_TOPIC:
            topics = log.get("topics", [])
            effects.append({"kind": "OwnerChanged", "address": log.get("address"),
                            "old_owner": "0x" + str(topics[1])[-40:] if len(topics) > 1 else None,
                            "new_owner": "0x" + str(topics[2])[-40:] if len(topics) > 2 else None,
                            "log_index": log.get("log_index")})
        else:
            effects.append({"kind": "event", "address": log.get("address"), "topic0": topic(log),
                            "log_index": log.get("log_index")})
    return {"transaction_hash": execution.get("transaction_hash"), "block": execution.get("block"),
            "calldata": execution.get("input_hex"), "selector": execution.get("input_selector"),
            "receipt_status": execution.get("status"), "log_count": execution.get("log_count"),
            "event_effects": effects}


def state_effects(case: dict) -> tuple[list[dict], list[str], list[str]]:
    writes, reads, observations = [], [], []
    for step in case.get("steps", []):
        evidence = step.get("evidence", {})
        for item in evidence.get("fee_tiers", []):
            location = f"BaseV3Factory.feeAmountTickSpacing[{item['fee']}]"
            reads.append(location)
            observations.append(f"{location}={item.get('spacing')}")
            if item.get("spacing") != 0:
                writes.append(location)
        if evidence.get("property") == "arbitrum_factory.owner":
            location = "ArbitrumV3Factory.owner"
            reads.append(location)
            if evidence.get("before") != evidence.get("after"):
                writes.append(location)
                observations.append(f"{location}:{evidence.get('before')}->{evidence.get('after')}")
        if "owner_before" in evidence and "owner_after" in evidence:
            location = "ArbitrumV3Factory.owner"
            reads.append(location)
            if evidence["owner_before"].get("value") != evidence["owner_after"].get("value"):
                writes.append(location)
                observations.append(f"{location}:{evidence['owner_before'].get('value')}->{evidence['owner_after'].get('value')}")
        if "owner_before" in evidence and "owner_after" in evidence and "expected_old" in evidence:
            location = "CeloV3Factory.owner"
            reads.append(location)
            before = evidence["owner_before"].get("value")
            after = evidence["owner_after"].get("value")
            if before != after:
                writes.append(location)
                observations.append(f"{location}:{before}->{after}")
        if evidence.get("retired_optics_authorization") is not None:
            reads.append("CeloV3Factory.authorization[OpticsReceiver]")
            observations.append(f"CeloV3Factory.authorization[OpticsReceiver]={evidence['retired_optics_authorization'].get('status')}")
        if evidence.get("wormhole_authorization") is not None:
            reads.append("CeloV3Factory.authorization[WormholeReceiver]")
            observations.append(f"CeloV3Factory.authorization[WormholeReceiver]={evidence['wormhole_authorization'].get('status')}")
    return sorted(set(writes)), sorted(set(reads)), sorted(set(observations))


def adapt(case: dict) -> dict:
    execution = case["execution"]
    writes, reads, observations = state_effects(case)
    property_dependencies = sorted(set(reads) | set(writes))
    return {"proposal_id": case["proposal_id"], "kind": case["kind"], "property": case["property"],
            "source": {"path": str(SOURCE.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(SOURCE.read_bytes())},
            "action": receipt_effect(execution), "state_observations": observations,
            "reads": reads, "writes": writes, "property_dependencies": property_dependencies,
            "btg_result": case.get("btg_result"),
            "boundary_results": [{"step": step.get("step"), "status": step.get("status")} for step in case.get("steps", [])]}


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if source.get("status") != "complete":
        raise AssertionError("saved Uniswap evidence is incomplete")
    cases = [adapt(case) for case in source["cases"]]
    if len(cases) < 3 or any(not item["action"]["calldata"] or not item["action"]["event_effects"] for item in cases):
        raise AssertionError("adapter did not extract calldata and receipt effects for every case")
    normalized = {"adapter": "Uniswap cross-chain calldata/receipt/log/state adapter", "source_sha256": digest(SOURCE.read_bytes()), "cases": cases}
    normalized["input_sha256"] = digest(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode())
    output = {"status": "complete", "protocol": "Uniswap cross-chain governance", "runner_sha256": digest(Path(__file__).read_bytes()),
              "source": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
              "source_sha256": digest(SOURCE.read_bytes()), "input_sha256": normalized["input_sha256"], "cases": cases,
              "summary": {"cases": len(cases), "calldata_cases": sum(bool(item["action"]["calldata"]) for item in cases),
                          "receipt_log_cases": sum(bool(item["action"]["event_effects"]) for item in cases),
                          "dependency_cases": sum(bool(item["property_dependencies"]) for item in cases)},
              "generated_utc": datetime.now(timezone.utc).isoformat()}
    OUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "cases": output["summary"]["cases"],
                      "calldata_cases": output["summary"]["calldata_cases"], "dependency_cases": output["summary"]["dependency_cases"],
                      "input_sha256": output["input_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
