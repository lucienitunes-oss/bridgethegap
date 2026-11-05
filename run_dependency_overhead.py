"""Measured graph construction and matched exploration on declared finite models.

Times exclude input generation, validation, hashing and output I/O. Memory is
Python allocation peak during a separate construction, not process RSS.
All repetitions and fixture definitions are retained for reproduction.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import gc
import hashlib
from itertools import combinations, permutations
import json
import math
from pathlib import Path
import platform
import random
import statistics
import time
import tracemalloc

from run_schedules import Action, build_dependency_graph, dependent, evaluate, reduced_orders

ROOT = Path(__file__).resolve().parent


def fixture(n, m, seed, conflicting=False):
    rng = random.Random(seed)
    actions = [Action(f'a{i}', 0 if conflicting else i, rng.randrange(3)) for i in range(n)]
    pairs = list(combinations(range(n), 2))
    predicates = rng.sample(pairs, m)
    return actions, predicates, [0] * n


def verify_graph(actions, predicates, graph):
    # Check every pair against the original on-demand relation, not graph code.
    for a, b in combinations(actions, 2):
        assert (b in graph[a]) == dependent(a, b, predicates, True)
        assert (b in graph[a]) == (a in graph[b])
    assert all(a not in graph[a] for a in actions)


def outcomes(orders, predicates, initial):
    joint = set()
    count = 0
    for order in orders:
        joint.add(evaluate(order, predicates, initial))
        count += 1
    return count, joint


def serialize(actions, predicates, initial):
    return {'actions': [asdict(a) for a in actions], 'predicates': predicates, 'initial': initial}


def main():
    construction = []
    exploration = []
    for n in (32, 128, 512):
        for family, m in [('invisible', 0), ('sparse', n), ('denser', 4*n), ('storage_clique', 0)]:
            for seed in (0, 1, 2):
                actions, predicates, initial = fixture(n, m, 20260914+seed, family == 'storage_clique')
                graph = build_dependency_graph(actions, predicates)
                verify_graph(actions, predicates, graph)
                edges = sum(map(len, graph.values())) // 2
                del graph
                samples = []
                for _ in range(7):
                    gc.collect()
                    start = time.perf_counter_ns()
                    graph = build_dependency_graph(actions, predicates)
                    samples.append((time.perf_counter_ns()-start)/1e6)
                    del graph
                gc.collect()
                tracemalloc.start()
                graph = build_dependency_graph(actions, predicates)
                retained, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                del graph
                construction.append({
                    'n': n, 'm': m, 'family': family, 'seed': seed,
                    'fixture': serialize(actions, predicates, initial),
                    'edges': edges, 'density': edges/math.comb(n, 2),
                    'build_ms': samples, 'median_build_ms': statistics.median(samples),
                    'python_retained_bytes': retained, 'python_peak_bytes': peak,
                    'all_pairs_match_original_relation': True,
                })
            print(f'Graph construction checked: n={n}, family={family}', flush=True)

    for n in (4, 6, 8):
        for m in (0, n//2, n, math.comb(n, 2)):
            for seed in (0, 1):
                actions, predicates, initial = fixture(n, m, 20260914+seed)
                graph = build_dependency_graph(actions, predicates)
                verify_graph(actions, predicates, graph)
                edges = sum(map(len, graph.values())) // 2
                reference_count, reference = outcomes(permutations(actions), predicates, initial)
                online_samples, cached_samples = [], []
                retained_count = None
                for repetition in range(3):
                    # Alternate execution order to reduce warm-up/order bias.
                    for cached in ([False, True] if repetition % 2 == 0 else [True, False]):
                        gc.collect()
                        start = time.perf_counter_ns()
                        adjacency = build_dependency_graph(actions, predicates) if cached else None
                        count, result = outcomes(
                            reduced_orders(actions, predicates, True, adjacency), predicates, initial)
                        elapsed = (time.perf_counter_ns()-start)/1e6
                        (cached_samples if cached else online_samples).append(elapsed)
                        assert result == reference, (n, m, seed, cached)
                        if retained_count is not None:
                            assert retained_count == count
                        retained_count = count
                exploration.append({
                    'n': n, 'm': m, 'seed': seed,
                    'fixture': serialize(actions, predicates, initial),
                    'edges': edges, 'density': edges/math.comb(n, 2),
                    'exhaustive_orders': reference_count, 'retained_orders': retained_count,
                    'joint_outcomes': len(reference), 'joint_outcome_match': True,
                    'online_ms': online_samples, 'cached_total_ms': cached_samples,
                    'median_online_ms': statistics.median(online_samples),
                    'median_cached_total_ms': statistics.median(cached_samples),
                })
            print(f'Exploration checked: n={n}, predicates={m}', flush=True)
    payload = {
        'status': 'complete', 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Constructed finite deterministic always-enabled overwrite models; declared pair predicates',
        'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                        'processor': platform.processor(), 'timer': 'perf_counter_ns'},
        'protocol': {'construction_repetitions': 7, 'exploration_repetitions': 3,
                     'construction_seeds': 3, 'exploration_seeds': 2,
                     'memory': 'Separate tracemalloc run; construction-only Python allocation peak; not RSS',
                     'cached_timing': 'Graph construction + DFS + identical prefix evaluator + joint-outcome aggregation',
                     'online_timing': 'Original on-demand predicate scans + DFS + identical evaluator + joint-outcome aggregation',
                     'exclusions': 'Input generation, checks, hashing, file I/O, external RPC and EVM execution'},
        'source_hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (Path(__file__), ROOT/'run_schedules.py')},
        'summary': {'construction_fixtures': len(construction), 'exploration_fixtures': len(exploration),
                    'graph_relation_mismatches': 0, 'joint_outcome_mismatches': 0,
                    'exhaustive_orders': sum(r['exhaustive_orders'] for r in exploration),
                    'retained_orders': sum(r['retained_orders'] for r in exploration)},
        'construction': construction, 'exploration': exploration,
    }
    output = ROOT/'results'/'dependency_overhead.json'
    output.write_text(json.dumps(payload, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(payload['summary'], indent=2))


if __name__ == '__main__':
    main()
