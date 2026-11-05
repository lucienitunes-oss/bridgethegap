"""Run the separate accepted-root Datalog rule on the trace-derived sequence."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEQ = ROOT / "experiments" / "results" / "real_replay" / "nomad_transaction_sequence.json"
BTG = ROOT / "experiments" / "results" / "real_replay" / "btg_nomad_transaction_sequence.json"
RULES = ROOT / "experiments" / "nomad_accepted_root.dl"
BASE = ROOT / "experiments" / "results" / "tool_comparison" / "souffle_nomad_transaction_sequence"
FACTS, OUTPUTS, RAW = BASE / "facts", BASE / "output", BASE / "raw"
REPORT = ROOT / "experiments" / "results" / "tool_comparison" / "souffle_nomad_transaction_sequence.json"
SOUFFLE = Path(r"E:\BridgeTheGapLab\souffle-clang\bin\souffle.exe")
MCPP = Path(r"E:\BridgeTheGapLab\mcpp-old\mcpp-2.7.2\bin\mcpp.exe")
LLVM_BIN = Path(r"E:\BridgeTheGapLab\llvm-mingw-portable\llvm-mingw-20260616-ucrt-x86_64\bin")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_facts(sequence: dict) -> None:
    FACTS.mkdir(parents=True, exist_ok=True)
    prefixes, boundaries, observations = [], [], []
    for row in sequence["transactions"]:
        index, tx = row["tx_index"], row["transaction_hash"]
        pre, post = row["pre_state"], row["post_state"]
        message_hash = pre["message_hash"]
        boundaries.append((index, "attack" if message_hash else "state"))
        prefixes.append((index, tx, row["block"], pre["block"]))
        # The property observes whether zero is accepted once Replica is
        # executable and, for Process, the message status before the call.
        for field, value in (("confirm_at_zero", post["confirm_at_zero"]),
                             ("acceptable_zero", post["acceptable_zero"]),
                             ("mapping_storage", post["mapping_storage"])):
            observations.append((index, tx, field, str(value).lower() if isinstance(value, bool) else str(value)))
        if message_hash:
            observations.extend([(index, tx, "message_status", pre["message_status"]),
                                 (index, tx, "acceptable_message", pre["acceptable_message"])])
    for filename, rows in (("prefix.facts", prefixes), ("boundary.facts", boundaries), ("observation.facts", observations)):
        with (FACTS / filename).open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle, delimiter="\t", lineterminator="\n").writerows(rows)


def read_csv(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


def main() -> None:
    sequence = json.loads(SEQ.read_text(encoding="utf-8"))
    btg = json.loads(BTG.read_text(encoding="utf-8"))
    if sequence["status"] != "complete" or not sequence["analysis"]["all_complete"]:
        raise AssertionError("trace-derived state sequence is incomplete")
    if not SOUFFLE.exists():
        raise FileNotFoundError(SOUFFLE)
    write_facts(sequence)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "rule_file.dl").write_bytes(RULES.read_bytes())
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(MCPP.parent), str(LLVM_BIN), env.get("PATH", "")])
    command = [str(SOUFFLE), "--preprocessor", str(MCPP).replace("\\", "/"), "-F", str(FACTS), "-D", str(OUTPUTS), str(RULES)]
    (RAW / "invocation.txt").write_text(" ".join(f'\"{x}\"' for x in command) + "\n", encoding="utf-8")
    version = subprocess.run([str(SOUFFLE), "--version"], env=env, capture_output=True, text=True, check=False)
    (RAW / "version.txt").write_text(version.stdout + version.stderr, encoding="utf-8")
    run = subprocess.run(command, cwd=BASE, env=env, capture_output=True, text=True, timeout=120)
    (RAW / "stdout.txt").write_text(run.stdout, encoding="utf-8")
    (RAW / "stderr.txt").write_text(run.stderr, encoding="utf-8")
    if run.returncode:
        raise RuntimeError(run.stderr[-2000:])
    decisions = [{"prefix_index": int(row[0]), "external_decision": row[1]} for row in read_csv(OUTPUTS / "Decision.csv")]
    decisions.sort(key=lambda item: item["prefix_index"])
    expected = [row["decision"] for row in btg["decisions"]]
    actual = [row["external_decision"] for row in decisions]
    if len(actual) != len(expected):
        raise AssertionError((actual, expected))
    facts = [{"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(path.read_bytes())} for path in sorted(FACTS.glob("*.facts"))]
    outputs = [{"relation": path.stem, "path": str(path.relative_to(ROOT)).replace("\\", "/"), "rows": len(read_csv(path)), "sha256": digest(path.read_bytes())} for path in sorted(OUTPUTS.glob("*.csv"))]
    input_hash = digest(RULES.read_bytes() + b"".join((FACTS / name).read_bytes() for name in ("boundary.facts", "observation.facts", "prefix.facts")))
    report = {"status": "complete", "tool": "Souffle separate Datalog implementation", "rules": str(RULES.relative_to(ROOT)).replace("\\", "/"),
              "rule_sha256": digest(RULES.read_bytes()), "input_sha256": input_hash, "state_input_sha256": sequence["state_input_sha256"],
              "facts": facts, "output_manifest": outputs, "decisions": decisions,
              "summary": {status.lower(): actual.count(status) for status in ("PASS", "VIOLATION", "UNKNOWN")},
              "same_input": {"transaction_hashes": sequence["transaction_hashes"], "same_prefix_order": True,
                             "same_state_input": True, "btg_results": expected, "souffle_results": actual,
                             "terminal_result": sequence["analysis"]["terminal_result"], "terminal_input_sha256": sequence["analysis"]["terminal_input_sha256"],
                             "agrees_with_btg": actual == expected, "uses_btg_oracle": False},
              "tool_version": (version.stdout + version.stderr).strip()}
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "decisions": actual, "terminal": report["same_input"]["terminal_result"], "state_input_sha256": report["state_input_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
