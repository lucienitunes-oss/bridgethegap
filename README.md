# Reproducing the evidence

## Scope

These are constructed Solidity regressions, finite overwrite models, a provenance-indexed public governance-metadata crawl, bounded replays of Uniswap proposals 94, 69, 29, and 43, a transaction-level replay of the Audius governance takeover, and a replay of the disclosed Nomad Bridge exploit. The local EVM runner executes bytecode on genuine Cancun EVM instances through Py-EVM; the historical replays read public receipts and committed states and send no transactions.

## Existing E-drive environment

- Python environment: E:\BridgeTheGapLab\venv (Python 3.10.8; base interpreter already existed).
- Compiler: E:\BridgeTheGapLab\solc\solc-v0.8.26\solc.exe.
- Compiler SHA-256: 537fd8d8d4a0433a971bf456fc06f7b021cdcee27b252f74da49e0d8559aeb67.
- Compiler settings: Cancun, optimizer enabled, 200 runs.
- Direct dependencies: web3 7.13.0, eth-tester 0.13.0b1, py-evm 0.12.1b1, py-solc-x 2.0.4, matplotlib 3.10.6, slither-analyzer 0.11.3.
- requirements-lock.txt contains actual installed versions, including transitive dependencies.
- Temporary files and package cache were directed to E:\BridgeTheGapLab\temp and E:\BridgeTheGapLab\pip-cache. Plot configuration uses E:\BridgeTheGapLab\matplotlib.

For a fresh environment, use a preinstalled Python 3.10 interpreter to create an E-drive venv, then install requirements-lock.txt with pip's --cache-dir pointing to the E-drive cache. The original attempt using eth-tester[py-evm] hit an optional safe-pysha3/MSVC build requirement; plain eth-tester with explicitly pinned py-evm works in this environment. No MSVC installation was required.

The compiler was downloaded using py-solc-x from the official ethereum/solc-bin GitHub mirror after the default host failed TLS verification. TLS verification was not disabled. To reproduce that download:

~~~powershell
$env:TEMP='E:\BridgeTheGapLab\temp'
$env:TMP='E:\BridgeTheGapLab\temp'
& E:\BridgeTheGapLab\venv\Scripts\python.exe -c "import solcx; solcx.install.BINARY_DOWNLOAD_BASE='https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/{}-amd64/{}'; solcx.install_solc('0.8.26',solcx_binary_path='E:/BridgeTheGapLab/solc')"
Get-FileHash E:\BridgeTheGapLab\solc\solc-v0.8.26\solc.exe -Algorithm SHA256
~~~

Verify the compiler hash above before running the tests. This records the versioned environment used for the empirical study.

## Run from the package root

~~~powershell
$env:TEMP='E:\BridgeTheGapLab\temp'
$env:TMP='E:\BridgeTheGapLab\temp'
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_schedules.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/validate_reduction.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_evm.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/fetch_public_governance.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/replay_oracle.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/replay_real_proposal.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_final_state_check.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_independent_prefix_checker.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_independent_proposal29_checker.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_proposal29_isolated_call.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_foundry_same_history.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/replay_audius_incident.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/replay_additional_crosschain.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_uniswap_protocol_adapter.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_nomad_transaction_sequence.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_btg_nomad_transaction_sequence.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_souffle_nomad_transaction_sequence.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_foundry_nomad_transaction_sequence.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_por_evidence_comparison.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_btg_real_history.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_mythril_sequence_baseline.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_echidna_proposal29.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_scale_ablation.py
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/run_dynamic_prefix_stress.py --seed 20261105 --count 128
& E:\BridgeTheGapLab\venv\Scripts\python.exe experiments/build_evidence.py
~~~

Check each process exit code before proceeding. Assertions are part of the experiments; do not use Python's -O mode. The EVM runner writes partial case records during execution and a manifest only after completion. The evidence builder checks record counts and runner hashes to reject common stale/partial-output errors.

To keep existing outputs when rerunning, run_schedules.py and run_evm.py accept --out with a new explicit directory. validate_reduction.py currently rewrites its own derived crosscheck.json. Back up reference results first if exact historic timings and hashes are needed. No deletion is needed.

## Static baseline

The reference baseline was run as follows:

~~~powershell
& E:\BridgeTheGapLab\venv\Scripts\slither.exe experiments/Fixtures.sol --solc E:\BridgeTheGapLab\solc\solc-v0.8.26\solc.exe --solc-args '--evm-version cancun --optimize --optimize-runs 200' --json experiments/results/slither.json
~~~

For a rerun, choose a new --json filename: Slither refuses to overwrite an existing result. A findings-related exit code of 1 is expected here; inspect the JSON success field to distinguish findings from an analysis failure. The saved reference JSON has success=true, 14 findings in nine categories, including reentrancy-no-eth and reentrancy-benign.

The fixture intentionally contains unrestricted operations, assembly, a deadline check, and an ignored nested low-level return. Vulnerable and corrected vault branches occur in the same source contract, allowing the source-level findings to be aligned with BTG's property-aware execution evidence. The saved reference JSON has success=true and records 14 findings in nine categories, including reentrancy-no-eth and reentrancy-benign.

The external sequence-analysis baseline is Mythril 0.24.8 in `E:\BridgeTheGapLab\mythril-venv`. `run_mythril_sequence_baseline.py` compiles the `Effects` fixture with the pinned solc binary and invokes bounded symbolic analysis with a two-transaction limit. The saved report has `status=completed` and contains a delegatecall finding. A legacy `pyethash` import-only shim is placed in `E:\BridgeTheGapLab\mythril-shims`; proof-of-work validation is outside this local fixture run. This baseline supplies a complementary bytecode-level view alongside BTG's history- and property-aware analysis.

`run_souffle_nomad_oracle_tests.py` exercises the independent rule's four-way
partition: complete violating input, missing input, complete valid-but-safe
input, and complete input with an out-of-domain attribute. Each case asserts
that exactly one of PASS, VIOLATION, or UNKNOWN is emitted.

The external Proposal 29 sequence/property baseline is Echidna 2.3.3 at `E:\BridgeTheGapLab\echidna-2.3.3\echidna.exe`, from the open-source Crytic repository. `run_echidna_proposal29.py` invokes Echidna's property engine on `Proposal29EchidnaReplay.sol` with the real V3Factory address and archived runtime code fetched at block 48,972,826. The harness fixes the exact target, alias caller, `setOwner(address)` calldata, and `V3Factory.owner()`/slot-3 attribute, then injects the saved pre- and post-repair slot values. Echidna reports the pre-repair property as falsified and the post-repair property as passing; exit code 1 is the expected counterexample finding. Raw text and normalized JSON are retained under `results/tool_comparison/echidna_proposal29/`.

## External cross-chain analyzer

XChainWatcher is run independently from its published repository and released Nomad facts. Souffle evaluates the repository's original Datalog rules in the isolated E-drive installation at `E:\BridgeTheGapLab\souffle-clang\bin\souffle.exe`; the older C preprocessor is at `E:\BridgeTheGapLab\mcpp-old\mcpp-2.7.2\bin\mcpp.exe`. `experiments/run_xchainwatcher_nomad.py` preserves all 30 generated CSV relations, the rule/fact/output manifests, and raw Blockscout transaction/log responses for the three selected attack hashes. `experiments/run_btg_nomad_attack.py` recomputes BTG decisions from the saved official root witness and those receipts/logs; the XChainWatcher rows are retained only for comparison. `experiments/run_nomad_full_prefix_comparison.py` adds the real production upgrade transaction, preserves its complete receipt/log/calldata response, and binds it with the three attack transactions into one ordered four-transaction prefix. XChainWatcher has no upgrade-specific relation, but independently flags all three later attack rows. `experiments/run_foundry_nomad_accepted_root.py` is retained as a legacy four-transaction control. The current `experiments/run_foundry_nomad_transaction_sequence.py` invokes the external Foundry `cast` client against the archive RPC at `https://eth.drpc.org` for all five rows of the exact Nomad transaction manifest. It independently reads each row's post-state `committedRoot`, `confirmAt`, `acceptableRoot`, and raw mapping storage; on the three Process rows it also reads the pre-state `messages(messageHash)` and `acceptableRoot` attributes. The deployment boundary is represented by an explicit code-absent pre-state. It compares every returned field against the adapter bundle, records the shared state-input hash, and applies the accepted-root predicate without importing the BTG oracle. The normalized report contains five independent VIOLATION decisions and retains stdout, stderr, and raw call manifests under `results/tool_comparison/foundry_nomad_transaction_sequence/`. XChainWatcher is an independent cross-chain anomaly analyzer, and Foundry cast is an independent accepted-root state checker; neither imports the BTG oracle.

The Nomad cast run is intentionally described as an archive-state validation
control: it independently retrieves the state attributes and applies the
declared accepted-root rule, but does not claim complete automatic vulnerability
discovery. The separate `nomad_accepted_root.dl` program is the independent
rule implementation. It consumes the same facts, emits PASS/VIOLATION/UNKNOWN
and intermediate relations, and records rule/input hashes and complete output.

## Expected outputs

### Dependency-graph overhead (2026-09-14)

Run `E:\BridgeTheGapLab\venv\Scripts\python.exe experiments\run_dependency_overhead.py`
from the package root, then run `experiments\build_evidence.py` with the same
Python environment. No new dependencies or public-network writes are needed.

The experiment saves `results/dependency_overhead.json` with 36 construction
fixtures (32/128/512 actions, three seeds, seven timings per seed) and 24
matched exploration fixtures (4/6/8 actions, two seeds, three timings per
method). The original on-demand relation and materialized adjacency use the
same DFS and monitor. Every graph edge is checked against the original
relation; joint outcomes are checked against all 328,512 reference orders.
Reduced enumeration retains 82,630 orders with zero mismatches in this run.
These totals concern this new density-controlled model corpus, separately
from the existing 128- and 192-model studies.

Construction timing excludes fixture generation, validation, and I/O.
Memory is the Python allocation peak during a separate `tracemalloc`
construction, not process RSS. Cached end-to-end timing includes graph
construction, DFS, monitoring, and outcome aggregation. The graph generator
uses declared overwrite effects and pair predicates, not inferred EVM effects.
`results/dependency_overhead_table.tex` reports medians; raw repetitions and
the platform, Python version, and source hashes remain in the JSON report.

The main Nomad table now has separate BTG, Souffle, and terminal-projection
columns. `run_nomad_transaction_sequence.py` obtains the real deployment,
upgrade, and attack transactions from the archive RPC; it saves raw calldata,
receipts, logs, `debug_traceTransaction` pre/post state diffs, and derives
action effects and property dependencies from those observations. The three
same-block attack transactions have independent message-slot transitions
0 -> 2 from trace diffs. `run_souffle_nomad_transaction_sequence.py`,
`run_btg_nomad_transaction_sequence.py`, and `run_nomad_terminal_check.py`
consume the same five-transaction state-input hash. The BTG, Souffle, and
terminal decisions are separate consumers of one saved state bundle.
The Souffle rule reuses trace-derived facts but does not import BTG code.
`run_souffle_nomad_oracle_tests.py` checks that complete violations, missing
observations, and complete wrong attributes emit exactly one mutually
exclusive decision. The older four-row archive report remains as provenance;
the five-row trace sequence is the current main input.

| Suite | Reference | Meaning |
|---|---:|---|
| Named EVM cases | 12 x 3 = 36 passes | Repeatability checks across named cases |
| EVM transactions | 150 | Includes deployments and expected failures |
| Diagnostic models | 128 | 120 intentionally unsafe; 8 safe boundaries |
| Exhaustive diagnostic orders | 27,840 | Every permutation for 3-6 actions |
| Property-aware diagnostic orders | 4,472 | 0 predicate-set and terminal-set mismatches |
| Persistent-set POR cross-check | 4,472 / 35,874 | 0 mismatches on the 128- and 192-model studies; independent traversal implementation |
| Storage-only diagnostic misses | 45 / 120 | Missed unsafe constructed models |
| Complete small-model configurations | 12,440 | 0-4 binary overwrites, 3 slots, 8 initial states |
| Cross-check reference orders | 259,832 | Independent monitor; two predicates |
| Cross-check reduced orders | 177,592 | 0 joint-outcome-set mismatches |
| Cross-check storage mismatches | 2,836 | Joint-outcome differences, not necessarily safe/unsafe misclassification |
| Public Snapshot proposals | 191 | Uniswap governance metadata, created from 2021-01-01 onward |
| Public keyword candidates | 129 | Provenance-indexed records for evidence binding |
| Proposal 94 replayed destinations | 3 | OP Mainnet, Base, Arbitrum; two successful target transactions per domain |
| Proposal 94 transaction-prefix violations | 3 | Attribute-driven case-study V2/V3 configuration property |
| Proposal 94 final-only misses | 1 | Negative control: final state only |
| Audius incident transactions | 5 | Successful public historical transactions |
| Audius proposal paths | 82/83, 84, 85 | Target-rejection, no-quorum, and successful-transfer paths |
| Audius initializer prefix | 1 | Unauthorized successful initialize call |
| Audius treasury outflow | 18,564,497.82 AUDIO | ERC-20 log and block-balance witness |
| BTG real-history decisions | 6 cases / 27 steps | Receipts and saved state attributes only |
| Proposal 69 | 3 PASS | Normal asynchronous Base delivery |
| Proposal 29 | 1 VIOLATION / 3 PASS | Cross-transaction owner repair followed by later Proposal 94 governance use |
| Proposal 43 | 5 PASS | Official Optics-to-Wormhole Celo bridge-authority migration with OwnerChanged and owner-state witnesses |
| Foundry cast same-history replay | 3 VIOLATION / 3 PASS | External archive receipt/transaction/state replay on the exact Proposal 94 input and prefix order |
| Foundry Anvil + cast Proposal 29 | REVERT before / PASS after | Same calldata, target, and alias caller executed on real pre/post archive forks with code/storage and full local receipts |
| Independent Proposal 29 analyzer | 1 VIOLATION / 3 PASS | Same four boundaries, property, and saved owner/use witnesses; no BTG oracle import |
| Echidna Proposal 29 | VIOLATION / PASS | Echidna 2.3.3 property engine on the same target/caller/calldata, slot 3, and archived code witness; raw output retained |
| Scale and matched ablation | 192 models / 1,479,360 orders | Property-aware POR retains 35,874 orders with 0 mismatches; final-only/fixed-order/storage-only miss 106/192/52 |
| Proposal 29 isolated call replay | REVERT before / PASS after | Same historical Proposal 94 calldata and alias caller on deployed Arbitrum V3 factory with saved owner states in read-only state overrides |
| Nomad Bridge exploit prefix | 4 VIOLATION | Complete production-upgrade-to-exploit prefix; three successful 100-WBTC Process/Receive transactions |
| XChainWatcher/Souffle Nomad run | 3 attack matches; upgrade boundary not applicable | Same four-transaction prefix manifest; complete raw output retained |
| Legacy Foundry cast Nomad control | 4 VIOLATION | Earlier four-transaction prefix and accepted-root property; archive `confirmAt[0x00...00]` storage changes `0x0 -> 0x1` |
| Souffle/Datalog Nomad accepted-root replay | 4 VIOLATION | Separate rule file; same prefix/property facts; rule hash, input hash, intermediate relations, and complete output retained |
| Souffle tri-state regression | VIOLATION / UNKNOWN / PASS | Complete, missing, and complete-but-wrong attributes; exactly one decision per case |
| Nomad trace-derived adapter | 5 VIOLATION | Real calldata, receipts, logs, per-transaction pre/post storage diffs, effects, dependencies, and shared state-input hash |
| Souffle Nomad trace-sequence replay | 5 VIOLATION | Same five-transaction state-input hash; separate rule implementation; complete relations and raw output |
| Foundry cast Nomad same-history replay | 5 VIOLATION | Same five transaction hashes and state-input hash; every adapter state field agrees; raw calls retained |
| Uniswap protocol adapter | 3 cases | Extracted calldata, receipt/log effects, archived state observations, and property dependencies for proposals 69, 29, and 43 |
| BTG/Persistent-set evidence comparison | 0.657s / 0.397s | Same 192-model corpus; BTG validates 5/5 Nomad rows from 57 archive reads, while POR uses abstract metadata only |

| Mythril fixture baseline | completed | Bounded symbolic transaction analysis; local fixture only |

results/evm contains compiled contracts, observed outcomes, transaction records, and a manifest. results/schedules contains fixture definitions, per-model per-method counts, and summary. results/scale_ablation.json and scale_ablation_table.tex contain the larger 3--8 action study and matched ablations. results/por_evidence_comparison.json and por_evidence_comparison_table.tex contain the role-separated BTG/Persistent-set timing, graph, state-read, and evidence-completeness comparison. results/crosscheck.json contains full scope, runner hashes, aggregate and per-size counts. results/slither.json contains raw warnings. results/public_governance contains the raw Snapshot response, normalized proposal metadata, keyword candidates, summary, query digest, and yearly table. results/real_replay contains the proposal page, normalized receipts, full calldata and receipt logs for the six Uniswap 94 transactions and five Audius transactions, archived Base witnesses for proposal 69, the Proposal 29 L1/L2 repair and later-use evidence, the Proposal 43 Ethereum/Celo bridge-authority migration receipts and owner witnesses, Audius permission-state differences, the BTG decisions, and evidence-scope metadata. It also contains proposal29_isolated_call.json and proposal29_archive_fork.json, which record complementary state-override and real archive-fork executions of the same calldata. results/tool_comparison contains the completed terminal-only check, the completed independent same-history prefix checkers for proposals 94 and 29, the raw Foundry cast receipt/transaction/archive-call outputs for every Proposal 94 prefix and the Nomad accepted-root replay, the Nomad deployment storage transition witness, the completed Mythril fixture report, and raw diagnostic output. The Uniswap proposal-94 policy is explicitly labeled a case-study policy.
results/dynamic_prefix_stress.json and dynamic_prefix_stress_table.tex contain the bounded dynamic event-graph stress study. It uses 128 recorded seeds, prerequisites, failed first deliveries, unblock/retry paths, deadlines, and property-visible policy updates. The exhaustive oracle enumerates 63,233 valid terminal prefixes; the route/property reducer retains 1,940 with zero outcome mismatches, while storage-only reduction mismatches 77 scenarios. The runner is a stress test of conservative handling, not an extension of the finite always-enabled theorem.

The current Nomad same-history artifact is `results/tool_comparison/foundry_nomad_transaction_sequence.json` plus its raw cast manifest. It records all five transaction hashes, the shared state-input hash, every independently queried pre/post field, retry diagnostics, and the equality check against the adapter bundle. The deployment row's code-absent pre-state is explicit. The earlier four-row cast report remains a legacy control.

The Uniswap adapter artifact is `results/real_replay/uniswap_adapter.json`. It consumes the saved Proposal 69, 29, and 43 calldata, receipts, raw logs, and archived state witnesses, then independently derives action effects and property dependencies; it does not import the BTG oracle.

The Echidna artifact is `results/tool_comparison/echidna_proposal29.json` plus the raw `echidna_output.txt` and `Proposal29EchidnaReplay.sol` harness. It records the exact target, caller, calldata, owner attribute, archived code hash, slot-3 witnesses, normalized BTG results, and the tool's original output.

build_evidence.py creates facts.tex, schedule_table.tex, and the two verified_*.pdf figures from saved records only. It also freezes installed package versions and hashes evidence-producing sources and outputs. checksums.json excludes the legacy semantic_sanity.json result. A checksum identifies an artifact; it does not independently establish scientific truth.

Timestamps, transaction hashes, wall times, and PDF metadata can change on rerun. Expected reproducibility is semantic agreement and the reported order counts. The cross-check does not import the original monitor: it independently computes the joint set of terminal states and violated-predicate bitmasks, including initially unsafe and zero-action configurations.

## Evidence scope

The public crawl supplies a provenance-indexed sampling frame, while the proposal and incident replays bind transaction receipts, calldata, event logs, and committed state witnesses. All public-network analysis is read-only historical observation; no transfer or exploit attempt is sent to a public network. The Audius replay follows an already disclosed incident and preserves the on-chain evidence chain. The decimal test normalizes host integers and stores the result on the EVM. The relay model uses a constructed contract, and the harness coordinates separate EVM stores while preserving the cross-domain ordering boundary.

The legacy semantic_sanity.py, original generate_figures.py, old figure files, and original bibliography remain for provenance. The current empirical claims are produced by the versioned runners and evidence builder described above. Mythril is an external local symbolic-analysis baseline that complements the archive and EVM analyses.
