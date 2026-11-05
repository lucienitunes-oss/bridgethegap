"""Finite, constructed models: exhaustive reference vs sleep-set reductions.

Effects and property reads are declared fixture metadata, not inferred EVM effects.
There are no loops/retries here; each labelled action runs once and is always enabled.
"""
import argparse
import csv
from collections import defaultdict
from dataclasses import asdict, dataclass
import hashlib
from itertools import combinations, permutations
import json
from pathlib import Path
import random
import time

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Action:
    name: str
    slot: int
    value: int


def dependent(a, b, predicates, property_aware):
    if a.slot == b.slot:
        return True
    return property_aware and any(a.slot in p and b.slot in p for p in predicates)


def build_dependency_graph(actions, predicates, property_aware=True):
    """Materialize the declared overwrite-model relation; no EVM effect inference."""
    by_slot = defaultdict(set)
    graph = {a: set() for a in actions}
    for a in actions:
        by_slot[a.slot].add(a)
    groups = list(by_slot.values())
    if property_aware:
        groups.extend(set().union(*(by_slot[s] for s in p)) for p in predicates)
    for group in groups:
        for a, b in combinations(group, 2):
            graph[a].add(b)
            graph[b].add(a)
    return graph


def reduced_orders(actions, predicates, property_aware, dependency_graph=None):
    # Sleep-set DFS on a finite, acyclic, always-enabled action system.
    def walk(prefix, remaining, asleep):
        if not remaining:
            yield prefix
            return
        local_sleep=set(asleep)
        for a in remaining:
            if a not in local_sleep:
                next_sleep={b for b in local_sleep if not (
                    b in dependency_graph[a] if dependency_graph is not None
                    else dependent(a,b,predicates,property_aware))}
                yield from walk(prefix+(a,),tuple(b for b in remaining if b!=a),next_sleep)
                local_sleep.add(a)
    return walk((),tuple(actions),set())


def persistent_property_orders(actions, predicates):
    """Property-aware persistent-set baseline for the always-enabled model."""
    actions = tuple(actions)
    graph = build_dependency_graph(actions, predicates, property_aware=True)

    def walk(prefix, remaining):
        if not remaining:
            yield prefix
            return
        selected = {remaining[0]}
        changed = True
        while changed:
            changed = False
            for action in remaining:
                if action not in selected and any(action in graph[item] for item in selected):
                    selected.add(action)
                    changed = True
        for action in remaining:
            if action in selected:
                yield from walk(prefix + (action,), tuple(item for item in remaining if item != action))

    return walk((), actions)


def evaluate(order, predicates, initial, final_only=False):
    state=list(initial)
    witnesses=[] if final_only else [i for i,(x,y) in enumerate(predicates) if state[x]<state[y]]
    for a in order:
        state[a.slot]=a.value
        if not final_only:
            witnesses.extend(i for i,(x,y) in enumerate(predicates) if state[x]<state[y])
    if final_only:
        witnesses=[i for i,(x,y) in enumerate(predicates) if state[x]<state[y]]
    return frozenset(witnesses),tuple(state)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=ROOT/'results'/'schedules')
    args=parser.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    fixtures=[]
    for n in (3,4,5,6):
        for seed in range(30):
            rng=random.Random(20260907+100*n+seed)
            # The first two actions force a prefix-order counterexample; remaining writes are random.
            actions=[Action('a0',0,1),Action('a1',1,1)]
            actions.extend(Action('a'+str(i),rng.randrange(4),rng.randrange(3)) for i in range(2,n))
            fixtures.append({'id':f'n{n}-seed{seed}','seed':20260907+100*n+seed,
                             'initial':[0,0,0,0],'predicates':[(0,1)],'actions':actions})
    # Explicit boundaries: independent invisible updates and all-conflicting writes.
    for n in (3,4,5,6):
        fixtures.append({'id':f'independent-{n}','seed':None,'initial':[0]*(n+2),
                         'predicates':[(n,n+1)],'actions':[Action('a'+str(i),i,1) for i in range(n)]})
        fixtures.append({'id':f'conflicting-{n}','seed':None,'initial':[0,0],
                         'predicates':[(0,1)],'actions':[Action('a'+str(i),0,i) for i in range(n)]})
    rows=[]; mismatches=[]
    for f in fixtures:
        methods={
            'exhaustive_prefix':(permutations(f['actions']),False),
            'exhaustive_final':(permutations(f['actions']),True),
            'fixed_order_prefix':([tuple(f['actions'])],False),
            'storage_only_por':(reduced_orders(f['actions'],f['predicates'],False),False),
            'property_aware_por':(reduced_orders(f['actions'],f['predicates'],True),False),
            'persistent_property_por':(persistent_property_orders(f['actions'],f['predicates']),False)}
        ref_bad=None; ref_finals=None
        for method,(orders,final_only) in methods.items():
            start=time.perf_counter(); bad=set(); finals=set(); count=0
            for order in orders:
                found,final=evaluate(order,f['predicates'],f['initial'],final_only)
                bad.update(found); finals.add(final); count+=1
            if method=='exhaustive_prefix': ref_bad=bad; ref_finals=finals
            matches=bad==ref_bad
            if method in ('property_aware_por', 'persistent_property_por') and (not matches or finals!=ref_finals):
                mismatches.append(f['id'])
            rows.append({'fixture':f['id'],'n':len(f['actions']),'method':method,'orders':count,
                         'violated_predicates':len(bad),'matches_reference':matches,
                         'final_states':len(finals),'wall_seconds':time.perf_counter()-start})
    assert not mismatches, mismatches
    with (args.out/'runs.csv').open('w',newline='',encoding='utf-8') as out:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    serial=[{**f,'actions':[asdict(a) for a in f['actions']]} for f in fixtures]
    (args.out/'fixtures.json').write_text(json.dumps(serial,indent=2)+'\n',encoding='utf-8')
    summary={'scope':'constructed finite always-enabled overwrite models, 3-6 actions',
             'fixtures':len(fixtures),'randomized_fixtures':120,'boundary_fixtures':8,
             'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'methods':{}}
    for method in methods:
        group=[r for r in rows if r['method']==method]
        summary['methods'][method]={'orders':sum(r['orders'] for r in group),
                                   'missed_models':sum(not r['matches_reference'] for r in group),
                                   'violation_models':sum(r['violated_predicates']>0 for r in group)}
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
