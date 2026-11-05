"""Run a larger deterministic schedule study and matched ablations.

The corpus extends the existing overwrite model from 3--6 to 3--8 actions.
Every method receives the same generated models; only observation granularity
and dependency information change.  Results are written as raw JSON and a
compact LaTeX table for the manuscript.
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from itertools import permutations
from pathlib import Path

from run_schedules import Action, evaluate, persistent_property_orders, reduced_orders


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "scale_ablation.json"
TABLE = ROOT / "results" / "scale_ablation_table.tex"


def build_fixtures() -> list[dict]:
    fixtures = []
    for n in range(3, 9):
        for seed in range(32):
            rng = random.Random(20260919 + 100 * n + seed)
            actions = [Action("a0", 0, 1), Action("a1", 1, 1)]
            actions.extend(Action(f"a{i}", rng.randrange(4), rng.randrange(3)) for i in range(2, n))
            fixtures.append({
                "id": f"n{n}-seed{seed}",
                "n": n,
                "initial": [0, 0, 0, 0],
                "predicates": [(0, 1)],
                "actions": actions,
            })
    return fixtures


def run_method(fixture: dict, method: str) -> dict:
    actions = fixture["actions"]
    predicates = fixture["predicates"]
    initial = fixture["initial"]
    if method == "exhaustive_prefix":
        orders, final_only = permutations(actions), False
    elif method == "exhaustive_final":
        orders, final_only = permutations(actions), True
    elif method == "fixed_order_prefix":
        orders, final_only = [tuple(actions)], False
    elif method == "storage_only_por":
        orders, final_only = reduced_orders(actions, predicates, False), False
    elif method == "persistent_property_por":
        orders, final_only = persistent_property_orders(actions, predicates), False
    else:
        orders, final_only = reduced_orders(actions, predicates, True), False

    started = time.perf_counter()
    bad = set()
    finals = set()
    count = 0
    for order in orders:
        found, final = evaluate(order, predicates, initial, final_only)
        bad.update(found)
        finals.add(final)
        count += 1
    return {
        "orders": count,
        "violated_predicates": len(bad),
        "final_states": len(finals),
        "wall_seconds": round(time.perf_counter() - started, 6),
    }


def main() -> None:
    fixtures = build_fixtures()
    methods = [
        "exhaustive_prefix",
        "exhaustive_final",
        "fixed_order_prefix",
        "storage_only_por",
        "property_aware_por",
        "persistent_property_por",
    ]
    records = []
    started = time.perf_counter()
    for fixture in fixtures:
        reference = run_method(fixture, "exhaustive_prefix")
        for method in methods:
            result = run_method(fixture, method)
            records.append({
                "fixture": fixture["id"],
                "n": fixture["n"],
                "method": method,
                **result,
                "matches_reference": (
                    result["violated_predicates"] == reference["violated_predicates"]
                    and result["final_states"] == reference["final_states"]
                ),
            })

    summary = {"methods": {}, "by_action_count": {}, "fixtures": len(fixtures)}
    for method in methods:
        group = [row for row in records if row["method"] == method]
        summary["methods"][method] = {
            "orders": sum(row["orders"] for row in group),
            "missed_models": sum(not row["matches_reference"] for row in group),
            "violation_models": sum(row["violated_predicates"] > 0 for row in group),
            "wall_seconds": round(sum(row["wall_seconds"] for row in group), 6),
        }
    for n in range(3, 9):
        group = [row for row in records if row["n"] == n]
        ref_rows = [row for row in group if row["method"] == "exhaustive_prefix"]
        por_rows = [row for row in group if row["method"] == "property_aware_por"]
        reference_orders = sum(row["orders"] for row in ref_rows)
        property_aware_orders = sum(row["orders"] for row in por_rows)
        summary["by_action_count"][str(n)] = {
            "fixtures": len([f for f in fixtures if f["n"] == n]),
            "reference_orders": reference_orders,
            "property_aware_orders": property_aware_orders,
            "reduction_percent": round(100 * (1 - property_aware_orders / reference_orders), 2),
            "property_aware_missed_models": sum(not row["matches_reference"] for row in por_rows),
        }

    output = {
        "status": "complete",
        "scope": "192 deterministic overwrite models with 3--8 labeled actions",
        "seed": 20260919,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "summary": summary,
        "records": records,
    }
    OUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    rows = [
        "% Generated by experiments/run_scale_ablation.py.",
        r"\begin{table}[t]\centering\scriptsize",
        r"\caption{Scale and matched ablation study on 192 deterministic models. All methods receive the same models; misses are disagreements with exhaustive prefix checking.}",
        r"\label{tab:scale-ablation}",
        r"\begin{tabular}{@{}lrrrr@{}}\toprule",
        r"Actions & Models & Ref. orders & BTG orders & BTG reduction \\ \midrule",
    ]
    for n, item in summary["by_action_count"].items():
        rows.append(f"{n} & {item['fixtures']} & {item['reference_orders']:,} & {item['property_aware_orders']:,} & {item['reduction_percent']:.2f}\\% \\\\")
    rows += [r"\midrule", r"\multicolumn{5}{@{}l}{Ablations over all 192 models:}", r"\\"]
    for method, label in [
        ("exhaustive_final", "Final-only"),
        ("fixed_order_prefix", "Fixed order"),
        ("storage_only_por", "Storage-only POR"),
        ("property_aware_por", "Property-aware POR"),
        ("persistent_property_por", "Persistent-set POR"),
    ]:
        item = summary["methods"][method]
        rows.append(f"{label} & -- & {item['orders']:,} & {item['violation_models']} viol. & {item['missed_models']} misses \\\\")
    rows += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    TABLE.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "fixtures": output["summary"]["fixtures"], "methods": summary["methods"]}, indent=2))
    assert summary["methods"]["property_aware_por"]["missed_models"] == 0


if __name__ == "__main__":
    main()
