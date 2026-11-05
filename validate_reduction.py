"""Independent bounded enumeration of multiple-predicate schedule outcomes.

Exhausts 0..4 labeled actions, three binary slots, and all eight initial states.
The reference monitor is independent of run_schedules.evaluate.
"""
import hashlib
from itertools import permutations, product
import json
from pathlib import Path

from run_schedules import Action, reduced_orders


def observe(order, initial):
    state=list(initial)
    bad=0
    # Independently written monitor; includes the empty prefix.
    if state[0]<state[1]: bad |= 1
    if state[1]<state[2]: bad |= 2
    for action in order:
        state[action.slot]=action.value
        if state[0]<state[1]: bad |= 1
        if state[1]<state[2]: bad |= 2
    return tuple(state),bad


def main():
    output=Path(__file__).resolve().parent/'results'/'crosscheck.json'
    predicates=((0,1),(1,2))
    choices=tuple(product(range(3),range(2)))
    rows=[]
    for n in range(5):
        row={'actions':n,'models':0,'unsafe_models':0,'reference_orders':0,
             'reduced_orders':0,'property_mismatches':0,'storage_mismatches':0}
        for initial in product(range(2),repeat=3):
            for template in product(choices,repeat=n):
                actions=tuple(Action(f'a{i}',slot,value) for i,(slot,value) in enumerate(template))
                reference=set()
                for order in permutations(actions):
                    reference.add(observe(order,initial));row['reference_orders']+=1
                reduced=set()
                for order in reduced_orders(actions,predicates,True):
                    reduced.add(observe(order,initial));row['reduced_orders']+=1
                storage={observe(order,initial) for order in reduced_orders(actions,predicates,False)}
                row['models']+=1
                row['unsafe_models']+=any(bad for _,bad in reference)
                row['property_mismatches']+=reference!=reduced
                row['storage_mismatches']+=reference!=storage
        rows.append(row)
    summary={key:sum(row[key] for row in rows) for key in rows[0] if key!='actions'}
    assert summary['models']==12440
    assert summary['property_mismatches']==0,rows
    assert summary['storage_mismatches']>0, 'Negative control did not distinguish the relations'
    data={'scope':'complete bounded enumeration; 0-4 labeled binary overwrites of three slots; all binary initial states; predicates x>=y and y>=z',
          'comparison':'set of (terminal state, violated-predicate bitmask) outcomes',
          'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'schedule_runner_sha256':hashlib.sha256(Path(__file__).with_name('run_schedules.py').read_bytes()).hexdigest(),
          'summary':summary,'by_action_count':rows}
    output.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(data,indent=2))


if __name__=='__main__':main()
