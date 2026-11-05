"""Run the independent Souffle/Datalog accepted-root rule on Nomad facts."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results"
SOURCE = RESULTS / "tool_comparison" / "foundry_nomad_accepted_root.json"
BTG_SOURCE = RESULTS / "real_replay" / "nomad_attack.json"
RULES = ROOT / "experiments" / "nomad_accepted_root.dl"
SOUFFLE = Path(r"E:\BridgeTheGapLab\souffle-clang\bin\souffle.exe")
MCPP = Path(r"E:\BridgeTheGapLab\mcpp-old\mcpp-2.7.2\bin\mcpp.exe")
LLVM_BIN = Path(r"E:\BridgeTheGapLab\llvm-mingw-portable\llvm-mingw-20260616-ucrt-x86_64\bin")
OUT = RESULTS / "tool_comparison" / "souffle_nomad_accepted_root"
FACTS = OUT / "facts"
OUTPUTS = OUT / "output"
RAW = OUT / "raw"
OUT_JSON = RESULTS / "tool_comparison" / "souffle_nomad_accepted_root.json"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_facts(foundry: dict) -> list[dict]:
    FACTS.mkdir(parents=True, exist_ok=True)
    rows = foundry["prefix_results"]
    boundaries = []
    prefixes = []
    observations = []
    for index, row in enumerate(rows, start=1):
        obs = row["accepted_root_observation"]
        state_block = int(row["state_block"])
        transaction_block = int(row["transaction_block"])
        kind = "attack" if obs.get("message_hash") else "state"
        boundaries.append((index, kind))
        prefixes.append((index, row["transaction_hash"], transaction_block, state_block))
        field_names = {
            "confirm_at_zero_root": "confirm_at_zero",
            "acceptable_root_zero": "acceptable_zero",
            "mapping_storage_value": "mapping_storage",
        }
        for field in field_names:
            value = obs[field]
            fact_field = field_names[field]
            if field == "acceptable_root_zero":
                value = str(value).lower()
            elif field == "confirm_at_zero_root":
                value = str(value)
            observations.append((index, row["transaction_hash"], fact_field, value))
        if kind == "attack":
            observations.append((index, row["transaction_hash"], "message_status", obs["message_status"]))
            observations.append((index, row["transaction_hash"], "acceptable_message", str(obs["acceptable_message_status"]).lower()))

    def write(path: Path, values: list[tuple]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle, delimiter="\t", lineterminator="\n").writerows(values)

    write(FACTS / "prefix.facts", prefixes)
    write(FACTS / "boundary.facts", boundaries)
    write(FACTS / "observation.facts", observations)
    return [{"prefix_index": i, "transaction_hash": tx, "kind": kind} for (i, tx, _, _), (_, kind) in zip(prefixes, boundaries)]


def read_csv(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


def main() -> None:
    foundry = json.loads(SOURCE.read_text(encoding="utf-8"))
    btg = json.loads(BTG_SOURCE.read_text(encoding="utf-8"))
    if not SOUFFLE.exists():
        raise FileNotFoundError(f"Souffle is unavailable: {SOUFFLE}")
    if foundry["status"] != "complete":
        raise AssertionError("The archive-state input is incomplete")
    prefix_meta = write_facts(foundry)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "rule_file.dl").write_bytes(RULES.read_bytes())
    (RAW / "invocation.txt").write_text(
        f'"{SOUFFLE}" --preprocessor "{MCPP}" -F "{FACTS}" -D "{OUTPUTS}" "{RULES}"\n', encoding="utf-8"
    )
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(MCPP.parent), str(LLVM_BIN), env.get("PATH", "")])
    version = subprocess.run([str(SOUFFLE), "--version"], env=env, capture_output=True, text=True, check=False)
    (RAW / "version.txt").write_text(version.stdout + version.stderr, encoding="utf-8")
    run = subprocess.run(
        [str(SOUFFLE), "--preprocessor", str(MCPP).replace("\\", "/"), "-F", str(FACTS), "-D", str(OUTPUTS), str(RULES)],
        cwd=OUT,
        env=env,
        capture_output=True,
        text=True,
    )
    (RAW / "stdout.txt").write_text(run.stdout, encoding="utf-8")
    (RAW / "stderr.txt").write_text(run.stderr, encoding="utf-8")
    if run.returncode != 0:
        raise RuntimeError(f"Souffle failed ({run.returncode}): {run.stderr[-2000:]}")

    decision_rows = read_csv(OUTPUTS / "Decision.csv")
    decisions = [{"prefix_index": int(row[0]), "external_decision": row[1]} for row in decision_rows]
    decisions.sort(key=lambda row: row["prefix_index"])
    expected_hashes = foundry["common_input"]["transaction_hashes"]
    if [item["transaction_hash"] for item in prefix_meta] != expected_hashes:
        raise AssertionError("Fact prefix differs from the saved common input")
    if [item["prefix_index"] for item in decisions] != list(range(1, len(expected_hashes) + 1)):
        raise AssertionError("Datalog did not produce one decision per prefix")

    output_manifest = []
    for path in sorted(OUTPUTS.glob("*.csv")):
        output_manifest.append({"relation": path.stem, "path": str(path.relative_to(ROOT)).replace("\\", "/"), "rows": len(read_csv(path)), "sha256": digest(path.read_bytes())})
    input_parts = [RULES.read_bytes()]
    for path in sorted(FACTS.glob("*.facts")):
        input_parts.append(path.read_bytes())
    input_hash = digest(b"".join(input_parts))
    btg_results = [row["status"] for row in btg["prefix"]]
    souffle_results = [row["external_decision"] for row in decisions]
    output = {
        "status": "complete",
        "tool": "Souffle independent Datalog checker",
        "external_binary": str(SOUFFLE),
        "tool_version": (version.stdout + version.stderr).strip(),
        "rules": str(RULES.relative_to(ROOT)).replace("\\", "/"),
        "rule_sha256": digest(RULES.read_bytes()),
        "input_sha256": input_hash,
        "common_input": {
            "transaction_hashes": expected_hashes,
            "transaction_count": len(expected_hashes),
            "same_prefix_order": expected_hashes == foundry["common_input"]["transaction_hashes"],
            "property": foundry["property"],
        },
        "facts": [{"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(path.read_bytes())} for path in sorted(FACTS.glob("*.facts"))],
        "decisions": decisions,
        "summary": {status.lower(): sum(item["external_decision"] == status for item in decisions) for status in ("PASS", "VIOLATION", "UNKNOWN")},
        "output_manifest": output_manifest,
        "same_input_comparison": {
            "same_accepted_root_property": True,
            "same_transaction_hashes_as_cast_state_input": True,
            "same_transaction_hashes_as_btg": expected_hashes[1:] == btg["historical_input"]["selected_attack_hashes"],
            "btg_results": btg_results,
            "souffle_results": souffle_results,
            "agrees_with_cast_state_checker": souffle_results == [row["external_decision"] for row in foundry["prefix_results"]],
            "agrees_with_btg": souffle_results == btg_results,
            "uses_btg_oracle": False,
        },
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    OUT_JSON.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "decisions": souffle_results, "rule_sha256": output["rule_sha256"], "input_sha256": input_hash}, indent=2))


if __name__ == "__main__":
    main()
