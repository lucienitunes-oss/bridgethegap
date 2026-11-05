"""Run Governance Seatbelt on the same Uniswap proposal input when configured.

The wrapper records a blocked/failed run as evidence. It never substitutes an
empty report for a tool result and never stores credential values.
"""
from __future__ import annotations

import json
import hashlib
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "experiments" / "results" / "tool_comparison"
SEATBELT = Path(r"E:\BridgeTheGapLab\governance-seatbelt")
BUN = Path(r"E:\BridgeTheGapLab\bun\node_modules\bun\bin\bun.exe")
ARCHIVE_UPSTREAM = "https://mainnet.gateway.tenderly.co"


class ChunkedArchiveHandler(BaseHTTPRequestHandler):
    upstream = ARCHIVE_UPSTREAM
    # Tenderly's public gateway accepts the historical range used by Seatbelt.
    # Keep the proxy's splitting logic available for narrower providers, but do
    # not turn one indexed archive query into thousands of serially slow calls.
    chunk_size = 100_000_000
    requests_forwarded = 0

    def log_message(self, *_args):
        return

    @classmethod
    def rpc(cls, payload):
        request = Request(
            cls.upstream,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "BTG-archive-gateway/1.0"},
            method="POST",
        )
        with urlopen(request, timeout=45) as response:
            cls.requests_forwarded += 1
            return json.loads(response.read().decode("utf-8"))

    @classmethod
    def handle_payload(cls, payload):
        if isinstance(payload, list):
            return [cls.handle_payload(item) for item in payload]
        if payload.get("method") != "eth_getLogs":
            return cls.rpc(payload)
        filt = dict(payload.get("params", [{}])[0])
        start = int(filt.get("fromBlock", "0x0"), 16)
        end = int(filt.get("toBlock", "0x0"), 16)
        if end - start <= cls.chunk_size:
            return cls.rpc(payload)
        ranges = [(left, min(left + cls.chunk_size, end)) for left in range(start, end + 1, cls.chunk_size + 1)]

        def fetch(bounds):
            left, right = bounds
            chunk = dict(filt, fromBlock=hex(left), toBlock=hex(right))
            return cls.rpc({"jsonrpc": payload["jsonrpc"], "id": payload["id"], "method": "eth_getLogs", "params": [chunk]})

        with ThreadPoolExecutor(max_workers=12) as pool:
            responses = list(pool.map(fetch, ranges))
        logs = []
        for response in responses:
            if "error" in response:
                return {"jsonrpc": payload["jsonrpc"], "id": payload["id"], "error": response["error"]}
            logs.extend(response.get("result", []))
        logs.sort(key=lambda log: (int(log.get("blockNumber", "0x0"), 16), int(log.get("transactionIndex", "0x0"), 16), int(log.get("logIndex", "0x0"), 16)))
        return {"jsonrpc": payload["jsonrpc"], "id": payload["id"], "result": logs}

    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(size).decode("utf-8"))
        try:
            response = self.handle_payload(payload)
            encoded = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except Exception as exc:
            encoded = json.dumps({"jsonrpc": "2.0", "id": payload.get("id"), "error": {"code": -32000, "message": str(exc)[:500]}}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "DAO_NAME": "Uniswap",
            "GOVERNOR_ADDRESS": "0x408ED6354d4973f66138C91495F2f2FCbd8724C3",
            "MAINNET_RPC_URL": "https://eth.drpc.org",
            "ARBITRUM_RPC_URL": "https://arb1.arbitrum.io/rpc",
            "OPTIMISM_RPC_URL": "https://mainnet.optimism.io",
            "BASE_RPC_URL": "https://mainnet.base.org",
        }
    )
    command = [str(BUN), "run-checks.ts", "94"]
    result = {
        "tool": "@uniswap/governance-seatbelt",
        "input": {"dao": "Uniswap", "governor": env["GOVERNOR_ADDRESS"], "proposal_id": 94},
        "repository": str(SEATBELT),
        "command": "bun run-checks.ts 94",
        "rpc_mode": "archive_gateway_with_chunking_fallback",
        "archive_upstream": ARCHIVE_UPSTREAM,
        "archive_chunk_size": ChunkedArchiveHandler.chunk_size,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "configured_environment": {
            "mainnet_rpc": True,
            "arbitrum_rpc": True,
            "optimism_rpc": True,
            "base_rpc": True,
            "tenderly_credentials_present": all(
                bool(env.get(k))
                for k in ("TENDERLY_ACCESS_TOKEN", "TENDERLY_USER", "TENDERLY_PROJECT_SLUG")
            ),
            "etherscan_api_key_present": bool(env.get("ETHERSCAN_API_KEY")),
        },
    }
    if SEATBELT.exists():
        try:
            result["repository_commit"] = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=SEATBELT, text=True, timeout=30
            ).strip()
        except Exception as exc:
            result["repository_commit_error"] = str(exc)[:240]
        package_json = SEATBELT / "package.json"
        if package_json.exists():
            result["package_json_sha256"] = hashlib.sha256(package_json.read_bytes()).hexdigest()
    if not BUN.exists() or not SEATBELT.exists():
        result.update({"status": "unavailable", "reason": "Seatbelt checkout or Bun executable is missing"})
    else:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ChunkedArchiveHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        env["MAINNET_RPC_URL"] = f"http://127.0.0.1:{server.server_port}"
        try:
            proc = subprocess.run(
                command,
                cwd=SEATBELT,
                env=env,
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
            result.update(
                {
                    "status": "completed" if proc.returncode == 0 else "failed",
                    "return_code": proc.returncode,
                    "stdout": proc.stdout[-50000:],
                    "stderr": proc.stderr[-50000:],
                }
            )
        except subprocess.TimeoutExpired as exc:
            result.update(
                {
                    "status": "timeout",
                    "stdout": (exc.stdout or "")[-50000:] if isinstance(exc.stdout, str) else "",
                    "stderr": (exc.stderr or "")[-50000:] if isinstance(exc.stderr, str) else "",
                }
            )
        finally:
            # shutdown() waits for serve_forever() to observe the wake-up pipe;
            # invoke it off the parent thread so the wrapper cannot deadlock
            # after Seatbelt exits.
            stop_thread = threading.Thread(target=server.shutdown, daemon=True)
            stop_thread.start()
            stop_thread.join(timeout=5)
            server.server_close()
            result["archive_forwarded_requests"] = ChunkedArchiveHandler.requests_forwarded
    (OUT / "seatbelt_proposal94.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in result if k not in {"stdout", "stderr"}}, indent=2))


if __name__ == "__main__":
    main()
