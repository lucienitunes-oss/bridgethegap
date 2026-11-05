"""Execute constructed Solidity regressions on Py-EVM (no public-chain RPC)."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
from pathlib import Path

import solcx
from eth_tester import EthereumTester, PyEVMBackend
from eth.vm.forks.cancun import CancunVM
from web3 import Web3, EthereumTesterProvider

ROOT = Path(__file__).resolve().parent


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def chain():
    tester = EthereumTester(PyEVMBackend(vm_configuration=((0, CancunVM),)))
    w = Web3(EthereumTesterProvider(tester))
    w.eth.default_account = w.eth.accounts[0]
    return w, tester


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--solc", default="E:/BridgeTheGapLab/solc/solc-v0.8.26/solc.exe")
    p.add_argument("--repetitions", type=int, default=3)
    p.add_argument("--out", type=Path, default=ROOT / "results" / "evm")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    source = (ROOT / "Fixtures.sol").read_text(encoding="utf-8")
    compiled = solcx.compile_standard({
        "language": "Solidity", "sources": {"Fixtures.sol": {"content": source}},
        "settings": {"evmVersion": "cancun", "optimizer": {"enabled": True, "runs": 200},
                     "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}}}
    }, solc_binary=args.solc)
    dump(args.out / "compiled.json", compiled)
    artifacts = compiled["contracts"]["Fixtures.sol"]
    rows, transactions = [], []

    def tx(w, fn, *, sender=None, **extra):
        receipt = w.eth.wait_for_transaction_receipt(fn.transact({
            "from": sender or w.eth.default_account, "gas": 2_000_000, **extra}))
        record = w.eth.get_transaction(receipt.transactionHash)
        transactions.append({"case": current[0], "repetition": current[1],
                             "tx_hash": receipt.transactionHash.hex(),
                             "to": record["to"], "input": record["input"].hex(),
                             "status": receipt.status, "gas_used": receipt.gasUsed,
                             "block": receipt.blockNumber,
                             "timestamp": w.eth.get_block(receipt.blockNumber).timestamp})
        return receipt

    def deploy(w, name, *values):
        a = artifacts[name]
        factory = w.eth.contract(abi=a["abi"], bytecode=a["evm"]["bytecode"]["object"])
        receipt = tx(w, factory.constructor(*values))
        assert receipt.status == 1
        return w.eth.contract(address=receipt.contractAddress, abi=a["abi"])

    current = ["", 0]
    for repetition in range(args.repetitions):
        for case in ["access_list", "dynamic_slot", "delegatecall", "transient_storage",
                     "revert_rollback", "relay_authentication", "relay_retry", "duplicate",
                     "expiration", "decimal_units", "callback_reentrancy", "prefix_order"]:
            current[:] = [case, repetition]
            started = time.perf_counter()
            w, tester = chain()
            target = deploy(w, "Effects")
            detail = {}
            if case == "access_list":
                assert tx(w, target.functions.set(42)).status == 1
                gas = []
                for access in [[], [{"address": target.address, "storageKeys": ["0x" + "00"*32]}]]:
                    opts = {"accessList": access, "gasPrice": 2_000_000_000, "type": 1}
                    receipt = tx(w, target.functions.value(), **opts)
                    assert receipt.status == 1
                    assert target.functions.value().call({"gas": 100_000, **opts}) == 42
                    gas.append(receipt.gasUsed)
                detail = {"empty_list_gas": gas[0], "populated_list_gas": gas[1],
                          "both_returned": 42, "gas_limit": 2_000_000}
            elif case == "dynamic_slot":
                key = 123456789 + repetition
                slot = int.from_bytes(Web3.keccak(key.to_bytes(32,"big") + (1).to_bytes(32,"big")),"big")
                before = w.eth.get_storage_at(target.address, slot).hex()
                assert tx(w, target.functions.setDynamic(key, 77)).status == 1
                assert int.from_bytes(w.eth.get_storage_at(target.address,slot),"big") == 77
                assert int.from_bytes(w.eth.get_storage_at(target.address,0),"big") == 0
                detail = {"key":key, "derived_slot":hex(slot), "before":before,
                          "after":w.eth.get_storage_at(target.address,slot).hex()}
            elif case == "delegatecall":
                library = deploy(w,"Effects")
                data = library.functions.set(91)._encode_transaction_data()
                assert tx(w,target.functions.delegate(library.address,data)).status == 1
                assert target.functions.value().call() == 91 and library.functions.value().call() == 0
                detail = {"caller_storage":91,"implementation_storage":0}
            elif case == "transient_storage":
                assert target.functions.transientRoundTrip(19).call() == 19
                assert tx(w,target.functions.transientRoundTrip(19)).status == 1
                assert target.functions.transientRead().call() == 0
                detail = {"within_call":19,"following_transaction":0}
            elif case == "revert_rollback":
                receipt=tx(w,target.functions.setThenRevert(500))
                assert receipt.status == 0 and target.functions.value().call() == 0
                detail={"status":0,"post_value":0}
            elif case in {"relay_authentication","relay_retry","duplicate","expiration"}:
                relay=deploy(w,"Relay")
                msg_id=Web3.keccak(text=case)
                deadline=w.eth.get_block("latest").timestamp + 100
                data=target.functions.set(8)._encode_transaction_data()
                fn=relay.functions.deliver(msg_id,target.address,data,deadline)
                if case=="relay_authentication":
                    failed=tx(w,fn,sender=w.eth.accounts[1])
                    assert failed.status==0 and not relay.functions.executed(msg_id).call()
                    passed=tx(w,fn)
                    assert passed.status==1 and target.functions.value().call()==8
                    detail={"unauthorized_status":0,"authorized_status":1}
                elif case=="relay_retry":
                    assert tx(w,target.functions.blockCalls(True)).status==1
                    failed=tx(w,fn)
                    pending=not relay.functions.executed(msg_id).call()
                    assert failed.status==0 and pending and target.functions.value().call()==0
                    assert tx(w,target.functions.blockCalls(False)).status==1
                    passed=tx(w,fn)
                    assert passed.status==1 and relay.functions.executed(msg_id).call()
                    detail={"failed_delivery_status":0,"pending_after_failure":pending,"retry_status":1}
                elif case=="duplicate":
                    assert tx(w,fn).status==1 and tx(w,fn).status==0
                    assert target.functions.value().call()==8
                    detail={"first_status":1,"duplicate_status":0}
                else:
                    tester.time_travel(deadline+1)
                    assert tx(w,fn).status==0 and target.functions.value().call()==0
                    detail={"deadline":deadline,"delivery_time":w.eth.get_block("latest").timestamp,"status":0}
            elif case=="decimal_units":
                scaled=750_000_000_000_000_000 // 10**12
                assert scaled==750_000
                assert tx(w,target.functions.set(scaled)).status==1
                assert target.functions.value().call()==750_000
                assert 7_500_000_000_000_000 // 10**12==7_500
                detail={"correct_18_decimal_value":750_000_000_000_000_000,
                        "correct_6_decimal_value":750_000,"legacy_example_normalizes_to":7500}
            elif case=="callback_reentrancy":
                paid=[]
                for fixed in (False, True):
                    vault=deploy(w,"CallbackVault",fixed)
                    client=deploy(w,"CallbackClient",vault.address)
                    assert tx(w,vault.functions.seed(client.address)).status==1
                    assert tx(w,client.functions.start()).status==1
                    paid.append(vault.functions.totalPaid().call())
                assert paid==[2,1]
                detail={"vulnerable_payout_units":paid[0],"fixed_payout_units":paid[1]}
            else:
                # Two independent EVM state stores; the monitor reads their joint state.
                traces=[]
                for order in ((0,1),(1,0)):
                    wx,_=chain(); wy,_=chain()
                    x=deploy(wx,"Effects"); y=deploy(wy,"Effects")
                    prefix=[]
                    for index in order:
                        wc,tc=[(wx,x),(wy,y)][index]
                        assert tx(wc,tc.functions.set(1)).status==1
                        state=[x.functions.value().call(),y.functions.value().call()]
                        prefix.append({"state":state,"safe":state[0]>=state[1]})
                    traces.append({"order":list(order),"prefixes":prefix})
                assert all(v["safe"] for v in traces[0]["prefixes"])
                assert not traces[1]["prefixes"][0]["safe"]
                assert traces[0]["prefixes"][-1]["state"]==traces[1]["prefixes"][-1]["state"]
                detail={"traces":traces,"final_state_only_misses_violation":True}
            rows.append({"case":case,"repetition":repetition,"passed":True,"observed":detail,
                         "wall_seconds":time.perf_counter()-started})
            dump(args.out/"runs.json",rows)
            dump(args.out/"transactions.json",transactions)
            print(case,repetition,"PASS",flush=True)
    manifest={"execution":"local in-process EVM; constructed fixtures; no OS guest or public chain",
              "vm":"CancunVM", "python":platform.python_version(),"platform":platform.platform(),
              "compiler":"0.8.26", "evm_version":"cancun", "optimizer_runs":200,
              "repetitions":args.repetitions,"cases":len(rows)//args.repetitions,
              "passed":sum(row["passed"] for row in rows),"transactions":len(transactions),
              "fixture_sha256":hashlib.sha256(source.encode()).hexdigest(),
              "runner_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "compiler_sha256":hashlib.sha256(Path(args.solc).read_bytes()).hexdigest(),
              "packages":{name:importlib.metadata.version(name) for name in ("web3","eth-tester","py-evm","py-solc-x")}}
    dump(args.out/"manifest.json",manifest)


if __name__=="__main__":
    main()
