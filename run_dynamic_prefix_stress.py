"""Bounded dynamic-prefix stress study for route and property dependencies.

This runner is intentionally empirical.  It does not extend the finite
always-enabled theorem.  Instead, it compares an exhaustive oracle with a
conservative dependency-closure reduction on small event graphs containing
prerequisites, a failed first delivery, an unblock/retry path, deadlines, and
property-visible updates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "results" / "dynamic_prefix_stress.json"
DEFAULT_TABLE = ROOT / "results" / "dynamic_prefix_stress_table.tex"


@dataclass(frozen=True)
class Event:
    name: str
    kind: str
    prerequisites: tuple[str, ...] = ()
    reads: tuple[int, ...] = ()
    writes: tuple[tuple[int, int], ...] = ()
    route: str = "audit"
    deadline: int | None = None


@dataclass(frozen=True)
class State:
    slots: tuple[int, ...]
    done: frozenset[str]
    time: int


@dataclass(frozen=True)
class Outcome:
    terminal_slots: tuple[int, ...]
    pending: int
    retry_status: str
    bad_predicates: tuple[str, ...]


@dataclass(frozen=True)
class SearchResult:
    outcomes: frozenset[Outcome]
    paths: int
    mismatches: int = 0


@dataclass(frozen=True)
class Scenario:
    seed: int
    events: tuple[Event, ...]
    initial_slots: tuple[int, ...]
    retry_deadline: int
    initially_blocked: bool

    def event(self, name: str) -> Event:
        for item in self.events:
            if item.name == name:
                return item
        raise KeyError(name)

    def enabled(self, state: State) -> tuple[str, ...]:
        return tuple(item.name for item in self.events if _enabled(self, state, item))


def make_scenario(
    seed: int,
    audit_count: int | None = None,
    initially_blocked: bool | None = None,
    retry_deadline: int | None = None,
) -> Scenario:
    rng = random.Random(seed)
    if audit_count is None:
        audit_count = rng.randrange(4)
    if initially_blocked is None:
        initially_blocked = bool(rng.randrange(2))
    if retry_deadline is None:
        retry_deadline = rng.randrange(4, 8)
    policy_value = 1 + rng.randrange(2)

    events = [
        Event("dispatch", "dispatch", writes=((3, 1),), route="bridge"),
        Event("unblock", "unblock", writes=((0, 0),), route="bridge"),
        Event(
            "deliver_first",
            "deliver_first",
            prerequisites=("dispatch",),
            reads=(0, 3),
            writes=((1, 1), (4, 1)),
            route="bridge",
        ),
        Event(
            "retry_delivery",
            "retry_delivery",
            prerequisites=("dispatch", "deliver_first", "unblock"),
            reads=(0, 1, 3, 4),
            writes=((1, 1), (3, 0)),
            route="bridge",
            deadline=retry_deadline,
        ),
        Event(
            "policy_update",
            "policy_update",
            prerequisites=("dispatch",),
            reads=(3,),
            writes=((2, policy_value),),
            route="governance",
        ),
    ]
    for index in range(audit_count):
        events.append(Event(f"audit{index}", "audit", writes=((5 + index, 1),)))

    return Scenario(
        seed=seed,
        events=tuple(events),
        initial_slots=(1 if initially_blocked else 0, 0, 0, 0, 0) + (0,) * audit_count,
        retry_deadline=retry_deadline,
        initially_blocked=initially_blocked,
    )


def initial_state(scenario: Scenario) -> State:
    return State(scenario.initial_slots, frozenset(), 0)


def _enabled(scenario: Scenario, state: State, event: Event) -> bool:
    if event.name in state.done or not set(event.prerequisites).issubset(state.done):
        return False
    if event.deadline is not None and state.time > event.deadline:
        return False
    if event.kind == "deliver_first":
        return state.slots[3] == 1
    if event.kind == "retry_delivery":
        return state.slots[4] == 1 and state.slots[0] == 0 and state.slots[1] == 0 and state.slots[3] == 1
    return True


def step(scenario: Scenario, state: State, event_name: str) -> State:
    event = scenario.event(event_name)
    if not _enabled(scenario, state, event):
        raise ValueError(f"event {event_name} is not enabled at time {state.time}")
    slots = list(state.slots)
    if event.kind == "deliver_first":
        if slots[0] == 1:
            slots[4] = 1
        else:
            slots[1] = 1
            slots[3] = 0
            slots[4] = 0
    elif event.kind == "retry_delivery":
        slots[1] = 1
        slots[3] = 0
    else:
        for slot, value in event.writes:
            slots[slot] = value
    return State(tuple(slots), state.done | {event_name}, state.time + 1)


def _bad(state: State) -> frozenset[str]:
    return frozenset({"delivery_before_policy"} if state.slots[1] < state.slots[2] else set())


def terminal_outcome(scenario: Scenario, state: State, bad: frozenset[str]) -> Outcome:
    if state.slots[1] == 1:
        retry_status = "delivered"
    elif state.slots[4] == 1 and state.time > scenario.retry_deadline:
        retry_status = "expired"
    elif state.slots[4] == 1:
        retry_status = "pending"
    else:
        retry_status = "not_needed"
    return Outcome(tuple(state.slots), state.slots[3], retry_status, tuple(sorted(bad)))


def _storage_conflict(a: Event, b: Event) -> bool:
    aw = {slot for slot, _ in a.writes}
    bw = {slot for slot, _ in b.writes}
    return bool(aw & (set(b.reads) | bw) or bw & (set(a.reads) | aw))


def dependency(a: Event, b: Event, scenario: Scenario, mode: str = "route_property") -> bool:
    if _storage_conflict(a, b):
        return True
    if mode == "storage":
        return False
    if a.deadline is not None or b.deadline is not None:
        return True
    if set(a.prerequisites) & {b.name} or set(b.prerequisites) & {a.name}:
        return True
    predicate_slots = {1, 2}
    a_writes = {slot for slot, _ in a.writes}
    b_writes = {slot for slot, _ in b.writes}
    if a_writes & predicate_slots and b_writes & predicate_slots:
        return True
    if a.route == b.route and a.route != "audit":
        return True
    if a.deadline is not None and b.deadline is not None and a.route == b.route:
        return True
    return False


def _closure(scenario: Scenario, enabled: tuple[str, ...], mode: str) -> tuple[str, ...]:
    selected = {enabled[0]}
    changed = True
    while changed:
        changed = False
        for name in enabled:
            if name in selected:
                continue
            event = scenario.event(name)
            if any(dependency(event, scenario.event(other), scenario, mode) for other in selected):
                selected.add(name)
                changed = True
    return tuple(name for name in enabled if name in selected)


def _search(scenario: Scenario, mode: str | None) -> SearchResult:
    outcomes: set[Outcome] = set()
    paths = 0

    def visit(state: State, bad: frozenset[str]) -> None:
        nonlocal paths
        enabled = scenario.enabled(state)
        if not enabled:
            outcomes.add(terminal_outcome(scenario, state, bad))
            paths += 1
            return
        choices = enabled if mode is None else _closure(scenario, enabled, mode)
        for name in choices:
            next_state = step(scenario, state, name)
            visit(next_state, bad | _bad(next_state))

    visit(initial_state(scenario), _bad(initial_state(scenario)))
    return SearchResult(frozenset(outcomes), paths)


def exhaustive_outcomes(scenario: Scenario) -> SearchResult:
    return _search(scenario, None)


def reduced_outcomes(scenario: Scenario, mode: str = "route_property") -> SearchResult:
    return _search(scenario, mode)


def _scenario_record(scenario: Scenario, exhaustive: SearchResult, storage: SearchResult, route: SearchResult) -> dict:
    return {
        "seed": scenario.seed,
        "audit_count": len([event for event in scenario.events if event.kind == "audit"]),
        "initially_blocked": scenario.initially_blocked,
        "retry_deadline": scenario.retry_deadline,
        "exhaustive_paths": exhaustive.paths,
        "storage_paths": storage.paths,
        "route_property_paths": route.paths,
        "exhaustive_outcomes": len(exhaustive.outcomes),
        "storage_outcome_mismatches": len(storage.outcomes - exhaustive.outcomes),
        "route_property_outcome_mismatches": len(route.outcomes - exhaustive.outcomes),
        "storage_exact_match": storage.outcomes == exhaustive.outcomes,
        "route_property_exact_match": route.outcomes == exhaustive.outcomes,
        "retry_success_outcomes": sum(item.retry_status == "delivered" for item in exhaustive.outcomes),
        "expired_outcomes": sum(item.retry_status == "expired" for item in exhaustive.outcomes),
        "prefix_violation_outcomes": sum(bool(item.bad_predicates) for item in exhaustive.outcomes),
    }


def run_suite(seed: int = 20261105, count: int = 128) -> dict:
    records = []
    for offset in range(count):
        scenario = make_scenario(seed + offset)
        exhaustive = exhaustive_outcomes(scenario)
        storage = reduced_outcomes(scenario, mode="storage")
        route = reduced_outcomes(scenario, mode="route_property")
        records.append(_scenario_record(scenario, exhaustive, storage, route))
    return {
        "status": "complete",
        "scope": "bounded dynamic event graphs with prerequisites, retry, deadlines, and property-visible updates",
        "seed_start": seed,
        "scenario_count": count,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "summary": {
            "exhaustive_paths": sum(item["exhaustive_paths"] for item in records),
            "storage_paths": sum(item["storage_paths"] for item in records),
            "route_property_paths": sum(item["route_property_paths"] for item in records),
            "storage_mismatch_scenarios": sum(not item["storage_exact_match"] for item in records),
            "route_property_mismatch_scenarios": sum(not item["route_property_exact_match"] for item in records),
            "retry_success_outcomes": sum(item["retry_success_outcomes"] for item in records),
            "expired_outcomes": sum(item["expired_outcomes"] for item in records),
            "prefix_violation_outcomes": sum(item["prefix_violation_outcomes"] for item in records),
        },
        "scenarios": records,
    }


def write_table(data: dict, path: Path) -> None:
    summary = data["summary"]
    rows = [
        "% Generated by experiments/run_dynamic_prefix_stress.py.",
        r"\begin{table}[t]",
        r"\centering\scriptsize",
        r"\caption{Bounded Dynamic Prefix Stress Study. The route/property reducer is compared with exhaustive valid-prefix exploration; storage-only reduction is a negative control.}",
        r"\label{tab:dynamic-stress}",
        r"\begin{tabular}{@{}lr@{}}\toprule",
        r"Metric & Value \\ \midrule",
        f"Scenarios & {data['scenario_count']} " + chr(92) * 2,
        f"Exhaustive valid prefixes & {summary['exhaustive_paths']:,} " + chr(92) * 2,
        f"Storage-only retained prefixes & {summary['storage_paths']:,} " + chr(92) * 2,
        f"Route/property retained prefixes & {summary['route_property_paths']:,} " + chr(92) * 2,
        f"Storage-only mismatch scenarios & {summary['storage_mismatch_scenarios']} " + chr(92) * 2,
        f"Route/property mismatch scenarios & {summary['route_property_mismatch_scenarios']} " + chr(92) * 2,
        f"Retry-success terminal outcomes & {summary['retry_success_outcomes']:,} " + chr(92) * 2,
        f"Expired-retry terminal outcomes & {summary['expired_outcomes']:,} " + chr(92) * 2,
        f"Prefix-violation terminal outcomes & {summary['prefix_violation_outcomes']:,} " + chr(92) * 2,
        r"\bottomrule\end{tabular}",
        r"\end{table}",
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20261105)
    parser.add_argument("--count", type=int, default=128)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    data = run_suite(seed=args.seed, count=args.count)
    args.out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_table(data, args.table)
    print(json.dumps({"status": data["status"], "scenario_count": data["scenario_count"], "summary": data["summary"]}, indent=2))
    assert data["summary"]["route_property_mismatch_scenarios"] == 0


if __name__ == "__main__":
    main()
