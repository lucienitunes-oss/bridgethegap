"""Regression-test mutually exclusive Souffle PASS/VIOLATION/UNKNOWN."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "experiments" / "nomad_accepted_root.dl"
BASE = ROOT / "experiments" / "results" / "tool_comparison" / "souffle_nomad_oracle_tests"
SOUFFLE = Path(r"E:\BridgeTheGapLab\souffle-clang\bin\souffle.exe")
MCPP = Path(r"E:\BridgeTheGapLab\mcpp-old\mcpp-2.7.2\bin\mcpp.exe")
LLVM_BIN = Path(r"E:\BridgeTheGapLab\llvm-mingw-portable\llvm-mingw-20260616-ucrt-x86_64\bin")
ZERO = "0x" + "0" * 64


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


CASES = {
    "complete_violation": {
        "boundary": "state",
        "observation": [("confirm_at_zero", "1"), ("acceptable_zero", "true"), ("mapping_storage", "0x1")],
        "expected": "VIOLATION",
    },
    "missing_observation": {
        "boundary": "state",
        "observation": [("confirm_at_zero", "1")],
        "expected": "UNKNOWN",
    },
    "complete_wrong_attribute": {
        "boundary": "state",
        "observation": [("confirm_at_zero", "1"), ("acceptable_zero", "false"), ("mapping_storage", "0x1")],
        "expected": "PASS",
    },
    "complete_invalid_attribute": {
        "boundary": "state",
        "observation": [("confirm_at_zero", "1"), ("acceptable_zero", "maybe"), ("mapping_storage", "0x1")],
        "expected": "UNKNOWN",
    },
}


def run_case(name: str, spec: dict) -> dict:
    case = BASE / name
    facts = case / "facts"
    output = case / "output"
    raw = case / "raw"
    facts.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    files = {
        "prefix.facts": [["1", "0x" + "1" * 64, "1", "1"]],
        "boundary.facts": [["1", spec["boundary"]]],
        "observation.facts": [["1", "0x" + "1" * 64, field, value] for field, value in spec["observation"]],
    }
    for filename, rows in files.items():
        path = facts / filename
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle, delimiter="\t", lineterminator="\n").writerows(rows)
    (raw / "rule_file.dl").write_bytes(RULES.read_bytes())
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(MCPP.parent), str(LLVM_BIN), env.get("PATH", "")])
    command = [str(SOUFFLE), "--preprocessor", str(MCPP).replace("\\", "/"), "-F", str(facts), "-D", str(output), str(RULES)]
    (raw / "invocation.txt").write_text(" ".join(f'\"{x}\"' for x in command) + "\n", encoding="utf-8")
    proc = subprocess.run(command, cwd=case, env=env, capture_output=True, text=True, timeout=120)
    (raw / "stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (raw / "stderr.txt").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode:
        raise RuntimeError(f"Souffle failed for {name}: {proc.stderr[-1000:]}")
    rows = []
    with (output / "Decision.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    decisions = [result for _, result in rows]
    if decisions != [spec["expected"]]:
        raise AssertionError((name, decisions, spec["expected"]))
    all_outputs = {path.name: digest(path.read_bytes()) for path in sorted(output.glob("*.csv"))}
    return {
        "expected": spec["expected"], "decision_rows": rows, "mutually_exclusive": len(decisions) == 1,
        "fact_hashes": {name: digest((facts / name).read_bytes()) for name in files},
        "output_hashes": all_outputs,
        "rule_sha256": digest(RULES.read_bytes()), "input_sha256": digest(RULES.read_bytes() + b"".join((facts / name).read_bytes() for name in files)),
    }


def main() -> None:
    if not SOUFFLE.exists():
        raise FileNotFoundError(SOUFFLE)
    results = {name: run_case(name, spec) for name, spec in CASES.items()}
    output = {"status": "complete", "tool": "Souffle", "rule": str(RULES.relative_to(ROOT)).replace("\\", "/"),
              "rule_sha256": digest(RULES.read_bytes()), "cases": results,
              "all_cases_mutually_exclusive": all(item["mutually_exclusive"] for item in results.values()),
              "expected_partition": {name: spec["expected"] for name, spec in CASES.items()}}
    path = ROOT / "experiments" / "results" / "tool_comparison" / "souffle_nomad_oracle_tests.json"
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "expected_partition": output["expected_partition"], "mutually_exclusive": output["all_cases_mutually_exclusive"]}, indent=2))


if __name__ == "__main__":
    main()
