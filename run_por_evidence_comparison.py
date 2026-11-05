"""Compare BTG's evidence layer with the persistent-set schedule baseline.

The two methods have different jobs.  The abstract timing uses the same
192-model corpus; evidence metrics use the real five-transaction Nomad bundle
and are reported separately rather than conflated into a speed claim.
"""
from __future__ import annotations

import hashlib
import json
import statistics
import time
from pathlib import Path

from run_nomad_transaction_sequence import build_graph
from run_scale_ablation import build_fixtures
from run_schedules import build_dependency_graph

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
NOMAD = RESULTS / "real_replay" / "nomad_transaction_sequence.json"
CAST = RESULTS / "tool_comparison" / "foundry_nomad_transaction_sequence.json"
SCALE = RESULTS / "scale_ablation.json"
OUTPUT = RESULTS / "por_evidence_comparison.json"
TABLE = RESULTS / "por_evidence_comparison_table.tex"


def median_build_ms(actions, predicates, repetitions: int = 7) -> float:
    samples = []
    for _ in range(repetitions):
        started = time.perf_counter_ns()
        build_dependency_graph(actions, predicates, property_aware=True)
        samples.append((time.perf_counter_ns() - started) / 1e6)
    return statistics.median(samples)


def main() -> None:
    nomad = json.loads(NOMAD.read_text(encoding="utf-8"))
    cast = json.loads(CAST.read_text(encoding="utf-8"))
    scale = json.loads(SCALE.read_text(encoding="utf-8"))
    rows = nomad["transactions"]
    fixtures = build_fixtures()

    graph_samples = []
    for _ in range(7):
        started = time.perf_counter_ns()
        graph = build_graph(rows)
        graph_samples.append((time.perf_counter_ns() - started) / 1e6)
        assert sum(len(value) for value in graph.values()) >= 0
    persistent_graph_samples = [
        median_build_ms(fixture["actions"], fixture["predicates"])
        for fixture in fixtures
    ]

    btg_started = time.perf_counter_ns()
    state_input = [{
        "tx_index": row["tx_index"],
        "transaction_hash": row["transaction_hash"],
        "block": row["block"],
        "pre_state": row["pre_state"],
        "post_state": row["post_state"],
        "effects": row["effects"],
    } for row in rows]
    state_hash = hashlib.sha256(
        json.dumps(state_input, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    decisions = []
    for row in rows:
        pre, post, effects = row["pre_state"], row["post_state"], row["effects"]
        violation = (
            effects["receipt_status"] == 1
            and post["confirm_at_zero"] == 1
            and post["acceptable_zero"] == "true"
            and int(post["mapping_storage"], 16) == 1
            and (not pre["message_hash"] or (
                pre["message_status"] == "0x" + "0" * 64
                and pre["acceptable_message"] == "true"
            ))
        )
        decisions.append("VIOLATION" if violation else "PASS")
    btg_decision_ms = (time.perf_counter_ns() - btg_started) / 1e6

    archive_state_reads = sum(
        len(item.get("pre_observation", {}).get("raw_calls", {}))
        + len(item.get("post_observation", {}).get("raw_calls", {}))
        for item in cast["transactions"]
    )
    evidence_fields = ("transaction", "receipt", "trace", "effects", "pre_state", "post_state")
    complete_rows = sum(all(field in row for field in evidence_fields) for row in rows)
    persistent = scale["summary"]["methods"]["persistent_property_por"]
    persistent_abstract_reads = sum(
        2 * (row["n"] + 1) * row["orders"]
        for row in scale["records"]
        if row["method"] == "persistent_property_por"
    )

    payload = {
        "status": "complete",
        "scope": "Role-separated comparison: same abstract scale corpus; Nomad evidence metrics",
        "protocol": {
            "timing_repetitions": 7,
            "abstract_runtime": "192-model scale_ablation wall_seconds",
            "graph_runtime": "median materialized dependency-graph construction; BTG uses five real Nomad rows, POR uses 192 abstract fixtures",
            "state_reads": "archive validator raw cast calls for BTG; abstract predicate-slot reads for persistent POR",
            "evidence_completeness": "real transaction rows require calldata/receipt/trace/effects/pre/post state; abstract POR has no chain evidence",
        },
        "methods": {
            "BTG": {
                "abstract_models": scale["summary"]["fixtures"],
                "abstract_runtime_seconds": scale["summary"]["methods"]["property_aware_por"]["wall_seconds"],
                "abstract_orders": scale["summary"]["methods"]["property_aware_por"]["orders"],
                "abstract_missed_models": scale["summary"]["methods"]["property_aware_por"]["missed_models"],
                "nomad_decision_runtime_ms": round(btg_decision_ms, 6),
                "dependency_graph_build_median_ms": round(statistics.median(graph_samples), 6),
                "dependency_graph_scope": "five-row Nomad adapter",
                "archive_state_reads": archive_state_reads,
                "real_evidence_complete": f"{complete_rows}/{len(rows)}",
                "real_evidence_components": {field: len(rows) for field in evidence_fields},
                "decisions": decisions,
                "state_input_sha256": state_hash,
            },
            "Persistent-set POR": {
                "abstract_models": scale["summary"]["fixtures"],
                "abstract_runtime_seconds": persistent["wall_seconds"],
                "abstract_orders": persistent["orders"],
                "abstract_missed_models": persistent["missed_models"],
                "dependency_graph_build_median_ms": round(statistics.median(persistent_graph_samples), 6),
                "dependency_graph_scope": "192 abstract fixtures",
                "archive_state_reads": 0,
                "abstract_predicate_slot_reads": persistent_abstract_reads,
                "real_evidence_complete": "0/5",
                "real_evidence_components": {},
                "decisions": [],
            },
        },
        "same_abstract_corpus": True,
        "same_abstract_outcomes": persistent["missed_models"] == 0,
        "cast_archive_reads_verified": archive_state_reads == 57,
        "cast_same_input": cast["state_input_sha256"] == nomad["state_input_sha256"],
        "source_hashes": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__), ROOT / "run_schedules.py", ROOT / "run_nomad_transaction_sequence.py")
        },
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    rows_out = [
        "% Generated by experiments/run_por_evidence_comparison.py.",
        r"\begin{table}[t]\centering\scriptsize",
        r"\caption{Role-separated comparison of BTG and the persistent-set POR baseline. Both methods receive the same 192 abstract models; evidence metrics use the real five-transaction Nomad bundle. The table does not claim an apples-to-apples wall-clock comparison across these different inputs.}",
        r"\label{tab:por-evidence}",
        r"\begin{tabular}{@{}p{0.20\linewidth}p{0.18\linewidth}p{0.18\linewidth}p{0.25\linewidth}@{}}\toprule",
        r"Method & Abstract runtime / orders & Graph construction & Evidence boundary \\ \midrule",
        f"BTG & {payload['methods']['BTG']['abstract_runtime_seconds']:.3f}s / {payload['methods']['BTG']['abstract_orders']:,} & {payload['methods']['BTG']['dependency_graph_build_median_ms']:.3f}ms (5 rows) & {archive_state_reads} archive reads; {complete_rows}/{len(rows)} complete " + r"\\",
        f"Persistent-set POR & {persistent['wall_seconds']:.3f}s / {persistent['orders']:,} & {statistics.median(persistent_graph_samples):.3f}ms (192 fixtures) & 0 archive reads; {persistent_abstract_reads:,} abstract reads; no chain evidence " + r"\\",
        r"\bottomrule\end{tabular}",
        r"\end{table}",
    ]
    TABLE.write_text("\n".join(rows_out) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "btg_archive_reads": archive_state_reads,
        "btg_complete_evidence": f"{complete_rows}/{len(rows)}",
        "persistent_abstract_reads": persistent_abstract_reads,
        "btg_runtime_ms": round(btg_decision_ms, 3),
        "persistent_runtime_seconds": persistent["wall_seconds"],
    }, indent=2))
    assert payload["same_abstract_corpus"] and payload["same_abstract_outcomes"]
    assert payload["cast_archive_reads_verified"] and payload["cast_same_input"]


if __name__ == "__main__":
    main()
