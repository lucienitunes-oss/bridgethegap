"""Small, explicit tri-state oracle used by the historical replay.

The oracle never treats a missing field as a safe value. Its two policies are
deliberately separate: local fee-pair completeness and optional global
all-domains coherence.
"""
from __future__ import annotations

import json
from pathlib import Path

PASS = "PASS"
VIOLATION = "VIOLATION"
UNKNOWN = "UNKNOWN"


def local_pair_status(observation: dict, expected: dict) -> dict:
    required = ("tx_status", "block", "transaction_hash", "v3_owner", "v2_fee_to")
    missing = [key for key in required if observation.get(key) in (None, "")]
    if missing:
        return {"status": UNKNOWN, "reason": "missing evidence: " + ", ".join(missing)}
    if observation["tx_status"] != 1:
        return {"status": UNKNOWN, "reason": "destination transaction did not succeed"}
    mismatches = {
        key: {"observed": observation[key], "expected": expected[key]}
        for key in ("v3_owner", "v2_fee_to")
        if observation[key].lower() != expected[key].lower()
    }
    if mismatches:
        return {"status": VIOLATION, "reason": "state does not match proposal", "mismatches": mismatches}
    return {"status": PASS, "reason": "both target fields match"}


def global_coherence_status(active_domains: list[str], expected_domains: list[str]) -> dict:
    if not active_domains or not expected_domains:
        return {"status": UNKNOWN, "reason": "empty domain evidence"}
    if any(domain not in expected_domains for domain in active_domains):
        return {"status": UNKNOWN, "reason": "active domain is outside declared input"}
    if len(active_domains) == len(expected_domains):
        return {"status": PASS, "reason": "all declared domains active"}
    return {
        "status": VIOLATION,
        "reason": "partial activation under the explicit all-domains policy",
        "active": len(active_domains),
        "expected": len(expected_domains),
    }


def normal_async_status(local_results: dict[str, dict], expected_domains: list[str]) -> dict:
    """Policy where pending domains are allowed during a staged rollout."""
    if set(local_results) - set(expected_domains):
        return {"status": UNKNOWN, "reason": "unexpected domain in async evidence"}
    if any(result["status"] == UNKNOWN for result in local_results.values()):
        return {"status": UNKNOWN, "reason": "an observed domain lacks complete evidence"}
    if any(result["status"] == VIOLATION for result in local_results.values()):
        return {"status": VIOLATION, "reason": "an observed local pair violates the property"}
    return {"status": PASS, "reason": "completed domains pass; unobserved domains remain pending"}


def final_only_status(local_results: dict[str, dict], expected_domains: list[str]) -> dict:
    if set(local_results) != set(expected_domains):
        return {"status": UNKNOWN, "reason": "final state is missing one or more domains"}
    if any(result["status"] == UNKNOWN for result in local_results.values()):
        return {"status": UNKNOWN, "reason": "final state contains incomplete local evidence"}
    if any(result["status"] == VIOLATION for result in local_results.values()):
        return {"status": VIOLATION, "reason": "at least one final local pair violates the property"}
    return {"status": PASS, "reason": "all final local pairs pass"}


def self_check() -> list[dict]:
    expected = {"v3_owner": "0xnew", "v2_fee_to": "0xjar"}
    base = {"tx_status": 1, "block": 1, "transaction_hash": "0xtx", **expected}
    cases = []
    result = local_pair_status(base, expected)
    assert result["status"] == PASS
    cases.append({"name": "complete_local_pair", "expected": PASS, "observed": result})
    async_results = {"op": {"status": PASS}}
    result = normal_async_status(async_results, ["op", "base", "arbitrum"])
    assert result["status"] == PASS
    cases.append({"name": "normal_async_pending_allowed", "expected": PASS, "observed": result})
    result = global_coherence_status(["op"], ["op", "base", "arbitrum"])
    assert result["status"] == VIOLATION
    cases.append({"name": "partial_global_policy_violation", "expected": VIOLATION, "observed": result})
    missing = dict(base)
    missing.pop("v2_fee_to")
    result = local_pair_status(missing, expected)
    assert result["status"] == UNKNOWN
    cases.append({"name": "missing_attribute_is_unknown", "expected": UNKNOWN, "observed": result})
    result = final_only_status({"op": {"status": PASS}}, ["op", "base"])
    assert result["status"] == UNKNOWN
    cases.append({"name": "missing_final_domain_is_unknown", "expected": UNKNOWN, "observed": result})
    return cases


if __name__ == "__main__":
    regression_cases = self_check()
    result_path = Path(__file__).resolve().parent / "results" / "real_replay" / "oracle_tests.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps({"status": "PASS", "cases": regression_cases}, indent=2) + "\n", encoding="utf-8")
    print("replay_oracle self-check passed")
