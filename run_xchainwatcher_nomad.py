"""Run the external XChainWatcher/Souffle analyzer on the saved Nomad data.

The run is deliberately kept outside the BTG implementation: XChainWatcher
supplies its own Datalog rules and Souffle evaluates them over the included
Nomad facts.  The script retains the complete generated output and the raw
transaction/log responses for the attack prefix used by BTG.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "experiments" / "results" / "tool_comparison"
COPIED = OUT / "xchainwatcher_nomad_results"
EXTERNAL_REPO = Path(r"E:\BridgeTheGapLab\XChainWatcher")
EXTERNAL_RUN = EXTERNAL_REPO / "runs" / "btg_nomad_20260912"
SOUFFLE = Path(r"E:\BridgeTheGapLab\souffle-clang\bin\souffle.exe")
MCPP = Path(r"E:\BridgeTheGapLab\mcpp-old\mcpp-2.7.2\bin\mcpp.exe")
LLVM_BIN = Path(r"E:\BridgeTheGapLab\llvm-mingw-portable\llvm-mingw-20260616-ucrt-x86_64\bin")
FACTS = EXTERNAL_REPO / "cross-chain-rules-validator" / "datalog" / "nomad-bridge" / "facts"
RULES = EXTERNAL_REPO / "cross-chain-rules-validator" / "datalog" / "acceptance-rules.dl"
HASHES = [
    "0x61497a1a8a8659a06358e130ea590e1eed8956edbd99dbb2048cfb46850a8f17",
    "0x40163166dfeaab8ee80e7b0acc62768cef84b7047b42b09827b29a8d77f383a9",
    "0xb1fe26cc8892f58eb468f5208baaf38bac422b5752cca0b9c8a871855d63ae28",
]
PREFIX_MANIFEST = ROOT / "experiments" / "results" / "real_replay" / "nomad_prefix_manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "BTG-repro/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def main() -> None:
    prefix_manifest = json.loads(PREFIX_MANIFEST.read_text(encoding="utf-8"))
    if prefix_manifest["transaction_hashes"][1:] != HASHES:
        raise AssertionError("XChainWatcher input is not the common Nomad prefix suffix")
    required = [SOUFFLE, MCPP, RULES, FACTS]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("missing external analyzer input: " + ", ".join(missing))

    EXTERNAL_RUN.mkdir(parents=True, exist_ok=True)
    result_dir = EXTERNAL_RUN / "results"
    result_dir.mkdir(parents=True, exist_ok=True)
    log_path = EXTERNAL_RUN / "datalog-logs.console"
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(MCPP.parent), str(LLVM_BIN), env.get("PATH", "")])
    command = [
        str(SOUFFLE),
        "--preprocessor",
        str(MCPP).replace("\\", "/"),
        "-p",
        str(log_path),
        "-F",
        str(FACTS),
        "-D",
        str(result_dir),
        str(RULES),
    ]
    # The command was executed successfully in the isolated shell before this
    # collector was run.  Reuse that output if it is already present; this
    # avoids a second multi-million-row write while preserving the exact run.
    reused_existing_run = any(result_dir.glob("*.csv"))
    if not reused_existing_run:
        completed = subprocess.run(command, cwd=EXTERNAL_REPO, env=env, capture_output=True, text=True)
        if completed.returncode != 0:
            raise RuntimeError(f"Souffle failed ({completed.returncode}): {completed.stderr[-2000:]}")

    COPIED.mkdir(parents=True, exist_ok=True)
    for source in sorted(result_dir.glob("*.csv")):
        shutil.copy2(source, COPIED / source.name)
    if log_path.exists():
        shutil.copy2(log_path, COPIED / log_path.name)

    repo_commit = subprocess.check_output(["git", "-C", str(EXTERNAL_REPO), "rev-parse", "HEAD"], text=True).strip()
    fact_manifest = [
        {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(FACTS.glob("*.facts"))
    ]
    output_manifest = [
        {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(COPIED.glob("*.csv"))
    ]
    selected = {}
    for path in sorted(COPIED.glob("*.csv")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        matches = [line for line in lines if any(tx in line for tx in HASHES)]
        if matches:
            selected[path.name] = matches

    raw_transactions = {}
    for tx_hash in HASHES:
        base = f"https://eth.blockscout.com/api/v2/transactions/{tx_hash}"
        raw_transactions[tx_hash] = {
            "transaction": fetch_json(base),
            "logs": fetch_json(base + "/logs"),
        }

    metadata = {
        "status": "complete",
        "tool": "XChainWatcher",
        "tool_repository": "https://github.com/AndreAugusto11/XChainWatcher",
        "tool_commit": repo_commit,
        "engine": "Souffle 2.5 built from source for the isolated Windows environment",
        "engine_binary": str(SOUFFLE),
        "command": command,
        "execution_status": "complete",
        "reused_existing_run_after_external_execution": reused_existing_run,
        "working_directory": str(EXTERNAL_REPO),
        "facts_directory": str(FACTS),
        "rules_file": str(RULES),
        "rules_sha256": sha256(RULES),
        "fact_manifest": fact_manifest,
        "output_directory": str(COPIED),
        "output_manifest": output_manifest,
        "selected_attack_hashes": HASHES,
        "common_prefix_manifest": str(PREFIX_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
        "common_prefix_transaction_count": len(prefix_manifest["transaction_hashes"]),
        "selected_output_rows": selected,
        "raw_attack_transactions_and_logs": raw_transactions,
        "official_incident_basis": [
            "https://medium.com/nomad-xyz-blog/nomad-bridge-hack-root-cause-analysis-875ad2e5aacd",
            "https://docs.nomad.xyz/the-nomad-protocol/security/root-of-trust/fraud",
        ],
        "data_provenance": [
            "https://github.com/nomad-xyz/hack-data",
            "https://eth.blockscout.com/",
        ],
        "interpretation": {
            "property": "a processed cross-chain message must be backed by a non-zero accepted root",
            "attack_prefix": "zero-root initialization followed by three successful process/Receive transactions",
            "security_consequence": "the three receipts transfer 100 WBTC each from the Nomad bridge path to attacker-controlled recipients",
            "btg_comparison_input": "the same ordered four-transaction prefix manifest; XChainWatcher evaluates the three withdrawal-bearing suffix transactions",
        },
    }
    (OUT / "xchainwatcher_nomad.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "outputs": len(output_manifest), "selected_files": sorted(selected)}, indent=2))


if __name__ == "__main__":
    main()
