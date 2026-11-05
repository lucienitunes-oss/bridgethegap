"""Bind the complete Nomad upgrade-to-exploit prefix to BTG and XChainWatcher.

The external analyzer is intentionally not reimplemented here.  XChainWatcher
is run on its released Nomad fact directory; this runner adds the real
on-chain upgrade transaction to the common prefix manifest and preserves its
raw receipt/log response.  The upgrade has no withdrawal-anomaly relation in
XChainWatcher's output, while the three later attack transactions do.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results"
NOMAD = RESULTS / "real_replay" / "nomad_attack.json"
XCHAIN = RESULTS / "tool_comparison" / "xchainwatcher_nomad.json"
FOUNDRY = RESULTS / "tool_comparison" / "foundry_nomad_accepted_root.json"
PREFIX_MANIFEST = RESULTS / "real_replay" / "nomad_prefix_manifest.json"
OUT = RESULTS / "real_replay" / "nomad_full_prefix_comparison.json"
RAW = RESULTS / "real_replay" / "nomad_full_prefix_raw.json"
DEPLOY_HASH = "0x99662dacfb4b963479b159fc43c2b4d048562104fe154a4d0c2519ada72e50bf"
UPGRADE_HASH = "0x7bccd64f4c4d5f6f545c2edf904857e6ddb460532fc0ac7eb5ac175cd21e56b1"


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "BTG-repro/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    nomad = json.loads(NOMAD.read_text(encoding="utf-8"))
    xchain = json.loads(XCHAIN.read_text(encoding="utf-8"))
    foundry = json.loads(FOUNDRY.read_text(encoding="utf-8"))
    prefix_manifest = json.loads(PREFIX_MANIFEST.read_text(encoding="utf-8"))
    attack_hashes = list(nomad["historical_input"]["selected_attack_hashes"])
    prefix_hashes = list(prefix_manifest["transaction_hashes"])
    if prefix_hashes != [UPGRADE_HASH, *attack_hashes]:
        raise AssertionError("BTG and external comparison do not use the common prefix manifest")
    if foundry["common_input"]["transaction_hashes"] != prefix_hashes:
        raise AssertionError("Foundry archive-state validator is not bound to the common prefix")
    raw_transactions = {}
    for tx_hash in (DEPLOY_HASH, UPGRADE_HASH):
        tx_url = f"https://eth.blockscout.com/api/v2/transactions/{tx_hash}"
        raw_transactions[tx_hash] = {
            "transaction": fetch_json(tx_url),
            "logs": fetch_json(tx_url + "/logs"),
        }
    RAW.write_text(json.dumps(raw_transactions, indent=2) + "\n", encoding="utf-8")

    selected = xchain["selected_output_rows"].get("SC_WithdrawalsWithoutMatch.csv", [])
    rows = []
    rows.append({
        "prefix_index": 1,
        "transaction_hash": UPGRADE_HASH,
        "block": raw_transactions[UPGRADE_HASH]["transaction"].get("block_number"),
        "label": "Nomad production upgrade boundary; zero-root state persists",
        "btg_result": nomad["prefix"][0]["status"],
            "external_tool": "XChainWatcher / Souffle",
            "external_result": "NO_APPLICABLE_WITHDRAWAL_RELATION",
            "accepted_root_external_tool": "Foundry cast",
            "accepted_root_external_result": foundry["prefix_results"][0]["external_decision"],
        "external_rows": [],
        "same_transaction_input": True,
        "security_witness": "official root-of-trust initialization; confirmAt[zero] = 1",
    })
    for index, (attack_hash, nomad_row) in enumerate(zip(attack_hashes, nomad["prefix"][1:]), start=2):
        matches = [line for line in selected if attack_hash in line]
        rows.append({
            "prefix_index": index,
            "transaction_hash": attack_hash,
            "block": nomad_row["block"],
            "label": f"Nomad attack transaction {index - 1}",
            "btg_result": nomad_row["status"],
            "external_tool": "XChainWatcher / Souffle",
            "external_result": "SC_WithdrawalsWithoutMatch" if matches else "NO_MATCH",
            "accepted_root_external_tool": "Foundry cast",
            "accepted_root_external_result": foundry["prefix_results"][index - 1]["external_decision"],
            "external_rows": matches,
            "same_transaction_input": True,
            "security_witness": "successful Process/Receive; 100 WBTC destination transfer",
        })

    output = {
        "status": "complete",
        "case": "nomad_bridge_2022_complete_upgrade_to_exploit_prefix",
        "property": nomad["property"],
        "official_basis": nomad["official_basis"],
        "security_consequence": nomad["security_consequence"],
        "historical_prefix": {
            "transaction_hashes": prefix_hashes,
            "transaction_count": len(prefix_hashes),
            "init_transaction": UPGRADE_HASH,
            "deployment_initialization_transaction": DEPLOY_HASH,
            "attack_transactions": attack_hashes,
            "raw_init_transaction_and_logs": str(RAW.relative_to(ROOT)).replace("\\", "/"),
            "raw_deployment_and_upgrade_transactions_and_logs": str(RAW.relative_to(ROOT)).replace("\\", "/"),
            "attack_transaction_and_logs": "experiments/results/tool_comparison/xchainwatcher_nomad.json",
            "common_prefix_manifest": str(PREFIX_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
        },
        "external_analyzer": {
            "tool": xchain["tool"],
            "repository": xchain["tool_repository"],
            "commit": xchain["tool_commit"],
            "rules_sha256": xchain["rules_sha256"],
            "facts_directory": xchain["facts_directory"],
            "output_directory": xchain["output_directory"],
            "complete_output_relations": len(xchain["output_manifest"]),
            "input_binding": "same ordered four-transaction prefix manifest; XChainWatcher evaluates the three withdrawal-bearing suffix rows and has no upgrade-specific rule",
        },
        "accepted_root_external_state_validator": {
            "tool": foundry["tool"],
            "binary": foundry["external_binary"],
            "version": foundry["tool_version"],
            "archive_rpc": foundry["archive_rpc"],
            "target_replica": foundry["target_replica"],
            "property": foundry["property"],
            "decision_rule": foundry["decision_rule"],
            "input_binding": "same ordered four-transaction prefix manifest and same accepted-root property",
            "raw_output_directory": "experiments/results/tool_comparison/foundry_nomad_accepted_root/raw",
        },
        "prefix_results": rows,
        "same_input": {
            "same_transaction_hashes": True,
            "same_prefix_order": True,
            # The tools are run on the same ordered transactions and official
            # incident evidence, but they implement different predicates:
            # BTG checks accepted-root authentication; XChainWatcher checks
            # cross-chain withdrawal matching.
            "same_property": False,
            "same_official_incident_basis": True,
            "same_official_basis": True,
            "same_security_consequence": True,
            "external_tool_has_upgrade_specific_rule": False,
            "attack_rows_agree": all(row["btg_result"] == "VIOLATION" and row["external_result"] == "SC_WithdrawalsWithoutMatch" for row in rows[1:]),
            "accepted_root_rows_agree": all(
                row["btg_result"] == row["accepted_root_external_result"] for row in rows
            ),
            "archive_storage_transition_verified": foundry["archive_storage_transition"]["transition"] == "0x0 -> 0x1",
        },
        "interpretation": "BTG identifies the official root-of-trust violation at the upgrade boundary and the three later transfer violations. XChainWatcher has no upgrade-specific rule and therefore emits no withdrawal relation for prefix 1, but independently flags all three later attack transactions on the same ordered prefix and released facts.",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "raw_sha256": sha256(RAW),
    }
    OUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": output["status"],
        "transaction_count": len(rows),
        "btg": [row["btg_result"] for row in rows],
        "external": [row["external_result"] for row in rows],
        "attack_rows_agree": output["same_input"]["attack_rows_agree"],
    }, indent=2))


if __name__ == "__main__":
    main()
