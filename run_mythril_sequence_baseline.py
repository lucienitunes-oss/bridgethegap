"""Run Mythril's bounded symbolic transaction analysis on the local fixture.

This is an external, runnable sanity baseline.  It is deliberately not used
as a same-history comparison: Mythril receives compiled fixture bytecode, not
cross-domain receipts or archived chain states.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "experiments" / "Fixtures.sol"
OUT = ROOT / "experiments" / "results" / "tool_comparison" / "mythril_sequence_fixture.json"
SOLC = Path(r"E:\BridgeTheGapLab\solc\solc-v0.8.26\solc.exe")
MYTHRIL_PY = Path(r"E:\BridgeTheGapLab\mythril-venv\Scripts\python.exe")
SHIMS = Path(r"E:\BridgeTheGapLab\mythril-shims")


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    result = {
        "tool": "Mythril",
        "tool_version_command": [str(MYTHRIL_PY), "-m", "mythril", "version"],
        "input": {
            "source": "experiments/Fixtures.sol",
            "contract": "Effects",
            "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            "scope": "compiled local fixture only; no public-chain state",
        },
        "started_utc": started,
        "status": "inconclusive",
    }
    if not SOLC.exists() or not MYTHRIL_PY.exists():
        result["reason"] = "configured solc or Mythril Python executable is missing"
        OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return

    compile_proc = subprocess.run(
        [str(SOLC), "--combined-json", "bin-runtime", "--optimize", str(SOURCE)],
        cwd=ROOT, capture_output=True, text=True, timeout=120, check=False,
    )
    result["compile"] = {
        "command": "solc --combined-json bin-runtime --optimize experiments/Fixtures.sol",
        "return_code": compile_proc.returncode,
        "stderr": compile_proc.stderr[-20000:],
    }
    if compile_proc.returncode != 0:
        result["reason"] = "fixture compilation failed"
        result["compile"]["stdout"] = compile_proc.stdout[-20000:]
        OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return

    compiled = json.loads(compile_proc.stdout)
    key = "experiments/Fixtures.sol:Effects"
    bytecode = compiled["contracts"][key]["bin-runtime"]
    result["input"]["runtime_bytecode_sha256"] = hashlib.sha256(bytecode.encode()).hexdigest()
    command = [
        str(MYTHRIL_PY), "-m", "mythril", "analyze", "-c", bytecode,
        "--bin-runtime", "-o", "json", "--execution-timeout", "60",
        "--no-onchain-data", "--transaction-count", "2",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SHIMS) + os.pathsep + env.get("PYTHONPATH", "")
    analysis = subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True,
        timeout=180, check=False,
    )
    result["command"] = "python -m mythril analyze -c <Effects runtime bytecode> --bin-runtime -o json --execution-timeout 60 --no-onchain-data --transaction-count 2"
    result["return_code"] = analysis.returncode
    result["stdout"] = analysis.stdout[-50000:]
    result["stderr"] = analysis.stderr[-20000:]
    try:
        result["report"] = json.loads(analysis.stdout)
        # Mythril uses a non-zero process code when it reports a finding.  A
        # structured report with success=true is therefore a completed run,
        # not a failed invocation.
        result["status"] = "completed" if result["report"].get("success") is True else "failed"
        result["finding_count"] = len(result["report"].get("issues", []))
    except json.JSONDecodeError:
        result["reason"] = "Mythril did not emit JSON"
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in result if k not in {"stdout", "stderr", "report"}}, indent=2))


if __name__ == "__main__":
    main()
