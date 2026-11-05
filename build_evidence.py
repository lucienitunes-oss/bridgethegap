"""Create manuscript tables/figures exclusively from saved experimental outputs."""
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
from statistics import median

os.environ.setdefault('MPLCONFIGDIR','E:/BridgeTheGapLab/matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent.parent
RESULTS=ROOT/'experiments'/'results'


def main():
    evm=json.loads((RESULTS/'evm'/'manifest.json').read_text())
    runs=json.loads((RESULTS/'evm'/'runs.json').read_text())
    sched=json.loads((RESULTS/'schedules'/'summary.json').read_text())
    cross=json.loads((RESULTS/'crosscheck.json').read_text())
    baseline=json.loads((RESULTS/'slither.json').read_text())
    public_meta=json.loads((RESULTS/'public_governance'/'metadata.json').read_text())
    public_summary=json.loads((RESULTS/'public_governance'/'summary.json').read_text())
    replay=json.loads((RESULTS/'real_replay'/'proposal94_replay.json').read_text())
    oracle_tests=json.loads((RESULTS/'real_replay'/'oracle_tests.json').read_text())
    terminal=json.loads((RESULTS/'tool_comparison'/'final_state_check_proposal94.json').read_text())
    independent_prefix=json.loads((RESULTS/'tool_comparison'/'independent_prefix_checker_proposal94.json').read_text())
    audius=json.loads((RESULTS/'real_replay'/'audius_incident.json').read_text())
    additional=json.loads((RESULTS/'real_replay'/'additional_crosschain_cases.json').read_text())
    nomad=json.loads((RESULTS/'real_replay'/'nomad_attack.json').read_text())
    nomad_full=json.loads((RESULTS/'real_replay'/'nomad_full_prefix_comparison.json').read_text())
    xchain=json.loads((RESULTS/'tool_comparison'/'xchainwatcher_nomad.json').read_text())
    nomad_cast=json.loads((RESULTS/'tool_comparison'/'foundry_nomad_accepted_root.json').read_text())
    nomad_souffle=json.loads((RESULTS/'tool_comparison'/'souffle_nomad_accepted_root.json').read_text())
    nomad_sequence=json.loads((RESULTS/'real_replay'/'nomad_transaction_sequence.json').read_text())
    nomad_sequence_btg=json.loads((RESULTS/'real_replay'/'btg_nomad_transaction_sequence.json').read_text())
    nomad_sequence_souffle=json.loads((RESULTS/'tool_comparison'/'souffle_nomad_transaction_sequence.json').read_text())
    nomad_terminal=json.loads((RESULTS/'tool_comparison'/'nomad_terminal_check.json').read_text())
    nomad_cast_sequence=json.loads((RESULTS/'tool_comparison'/'foundry_nomad_transaction_sequence.json').read_text())
    souffle_oracle_tests=json.loads((RESULTS/'tool_comparison'/'souffle_nomad_oracle_tests.json').read_text())
    uniswap_adapter=json.loads((RESULTS/'real_replay'/'uniswap_adapter.json').read_text())
    btg=json.loads((RESULTS/'real_replay'/'btg_real_history.json').read_text())
    mythril=json.loads((RESULTS/'tool_comparison'/'mythril_sequence_fixture.json').read_text())
    foundry=json.loads((RESULTS/'tool_comparison'/'foundry_cast_proposal94'/'foundry_cast_proposal94.json').read_text())
    independent29=json.loads((RESULTS/'tool_comparison'/'independent_proposal29_checker.json').read_text())
    echidna29=json.loads((RESULTS/'tool_comparison'/'echidna_proposal29.json').read_text())
    scale=json.loads((RESULTS/'scale_ablation.json').read_text())
    dependency=json.loads((RESULTS/'dependency_overhead.json').read_text())
    por_evidence=json.loads((RESULTS/'por_evidence_comparison.json').read_text())
    assert dependency['status'] == 'complete'
    assert dependency['summary']['graph_relation_mismatches'] == 0
    assert dependency['summary']['joint_outcome_mismatches'] == 0
    assert por_evidence['status'] == 'complete'
    assert por_evidence['same_abstract_corpus']
    assert por_evidence['same_abstract_outcomes']
    assert por_evidence['cast_archive_reads_verified']
    assert por_evidence['cast_same_input']
    assert por_evidence['methods']['BTG']['real_evidence_complete'] == '5/5'
    assert por_evidence['methods']['Persistent-set POR']['real_evidence_complete'] == '0/5'
    for name, expected in dependency['source_hashes'].items():
        assert hashlib.sha256((ROOT/'experiments'/name).read_bytes()).hexdigest() == expected, name
    isolated29=json.loads((RESULTS/'real_replay'/'proposal29_isolated_call.json').read_text())
    archive29=json.loads((RESULTS/'real_replay'/'proposal29_archive_fork.json').read_text())
    proposal29_terminal=json.loads((RESULTS/'tool_comparison'/'proposal29_terminal_prefix_check.json').read_text())
    assert baseline['success'], 'Static baseline did not complete'
    assert evm['passed']==len(runs)==evm['cases']*evm['repetitions']==36
    assert all(r['passed'] for r in runs)
    assert len(json.loads((RESULTS/'evm'/'transactions.json').read_text()))==evm['transactions']==150
    assert cross['summary']['models']==12440 and cross['summary']['property_mismatches']==0
    assert public_meta['proposal_count']==public_summary['proposal_count']>0
    assert public_meta['keyword_candidate_count']==public_summary['keyword_candidate_count']>0
    assert replay['status']=='complete'
    assert replay['policy']['prefix_violation_found']
    assert replay['policy']['final_only_misses_prefix']
    assert replay['policy']['local_pair_result']
    assert replay['policy']['normal_async_result']
    assert oracle_tests['status']=='PASS' and len(oracle_tests['cases']) >= 5
    assert terminal['status']=='PASS'
    assert terminal['input']['proposal_id']==94
    assert terminal['input']['property']==replay['policy']['name']
    assert terminal['input']['transaction_hashes']==[row['transaction_hash'] for row in replay['cross_domain_prefix']]
    assert terminal['input']['proposal_page_sha256']==replay['proposal_page_sha256']
    assert independent_prefix['status']=='complete'
    assert independent_prefix['input']['proposal_page_sha256']==replay['proposal_page_sha256']
    assert independent_prefix['input']['transaction_hashes']==[row['transaction_hash'] for row in replay['cross_domain_prefix']]
    assert independent_prefix['summary']['pass']==3
    assert independent_prefix['summary']['violation']==3
    assert independent_prefix['summary']['unknown']==0
    assert independent_prefix['summary']['terminal_status']=='PASS'
    additional_by_id={case['proposal_id']:case for case in additional['cases']}
    assert additional_by_id[29]['kind']=='cross_transaction_owner_repair_and_use'
    assert additional_by_id[29]['cross_transaction_witness']['ordered']
    assert additional_by_id[29]['cross_transaction_witness']['later_governance_use']
    assert additional_by_id[43]['kind']=='normative_bridge_authority_migration'
    assert additional_by_id[43]['official_basis']['url']=='https://vote.uniswapfoundation.org/proposals/43'
    assert additional_by_id[43]['btg_result']=='PASS'
    assert uniswap_adapter['status'] == 'complete'
    assert uniswap_adapter['summary']['cases'] == len(additional['cases']) == 3
    assert uniswap_adapter['summary']['calldata_cases'] == 3
    assert uniswap_adapter['summary']['receipt_log_cases'] == 3
    assert uniswap_adapter['summary']['dependency_cases'] == 3
    assert hashlib.sha256((ROOT/uniswap_adapter['source']).read_bytes()).hexdigest() == uniswap_adapter['source_sha256']
    assert hashlib.sha256((ROOT/'experiments'/'run_uniswap_protocol_adapter.py').read_bytes()).hexdigest() == uniswap_adapter['runner_sha256']
    assert audius['status']=='complete'
    assert audius['derived_checks']['transaction_count'] >= 5
    assert audius['derived_checks']['initializer_prefix_violation']
    assert audius['derived_checks']['treasury_transfer_count'] >= 1
    assert audius['normative_property']['not_researcher_defined']
    assert audius['derived_checks']['proposal_ids_replayed'] == [82, 83, 84, 85]
    assert audius['derived_checks']['proposal_82_83_state_events'] == 2
    assert audius['derived_checks']['proposal_84_defeated_state_events'] == 1
    assert audius['derived_checks']['proposal_84_vote_events'] == 0
    assert audius['derived_checks']['proposal_85_vote_events'] == 1
    assert audius['derived_checks']['proposal_85_execution_events'] == 1
    assert audius['derived_checks']['permission_state_changed_after_initializer']
    assert audius['derived_checks']['permission_changed_field_count'] >= 3
    assert audius['derived_checks']['proxy_admin_slot_unchanged']
    assert audius['prefix_results'] == {
        'initialization_then_target_rejection': 'VIOLATION',
        'proposal_84_no_quorum': 'PASS',
        'proposal_85_funds_transfer': 'VIOLATION',
    }
    assert btg['status']=='complete' and btg['oracle']=='BTG'
    assert btg['tri_state']==['PASS','VIOLATION','UNKNOWN']
    assert len(btg['cases']) == 6
    btg_by_case={case.get('proposal_id',case['case']):case for case in btg['cases']}
    assert btg_by_case['uniswap_proposal_94']['summary']['violation'] == 3
    assert btg_by_case['audius_governance_takeover']['summary']['violation'] == 3
    assert btg_by_case[69]['summary']['pass'] == 3
    assert btg_by_case[29]['summary']['violation'] == 1
    assert btg_by_case[29]['summary']['pass'] == 3
    assert btg_by_case[29]['summary']['unknown'] == 0
    assert btg_by_case[43]['summary'] == {'pass': 5, 'violation': 0, 'unknown': 0}
    assert nomad['status'] == 'complete'
    assert nomad['summary'] == {'pass': 0, 'violation': 4, 'unknown': 0}
    assert nomad['independent_comparison']['same_historical_fact_directory']
    assert nomad['independent_comparison']['same_selected_transaction_hashes']
    assert nomad['independent_comparison']['same_attack_prefix_signal']
    assert xchain['status'] == 'complete'
    assert xchain['execution_status'] == 'complete'
    assert len(xchain['output_manifest']) == 30
    assert set(xchain['selected_attack_hashes']) == set(nomad['historical_input']['selected_attack_hashes'])
    assert len(xchain['selected_output_rows']['SC_WithdrawalsWithoutMatch.csv']) == 3
    assert btg_by_case['nomad_bridge_2022_zero_root_exploit']['summary'] == nomad['summary']
    assert nomad_full['status'] == 'complete'
    assert nomad_full['historical_prefix']['transaction_count'] == 4
    assert nomad_full['historical_prefix']['transaction_hashes'][0] == '0x7bccd64f4c4d5f6f545c2edf904857e6ddb460532fc0ac7eb5ac175cd21e56b1'
    assert nomad_full['same_input']['same_transaction_hashes']
    assert nomad_full['same_input']['same_prefix_order']
    assert nomad_full['same_input']['same_official_basis']
    assert nomad_full['same_input']['same_official_incident_basis']
    assert nomad_full['same_input']['same_security_consequence']
    assert nomad_full['same_input']['attack_rows_agree']
    assert nomad_full['same_input']['accepted_root_rows_agree']
    assert nomad_full['same_input']['archive_storage_transition_verified']
    assert len(nomad_full['prefix_results']) == 4
    assert nomad_full['prefix_results'][0]['external_result'] == 'NO_APPLICABLE_WITHDRAWAL_RELATION'
    assert all(row['external_result'] == 'SC_WithdrawalsWithoutMatch' for row in nomad_full['prefix_results'][1:])
    assert nomad_cast['status'] == 'complete'
    assert nomad_cast['common_input']['transaction_hashes'] == nomad_full['historical_prefix']['transaction_hashes']
    assert nomad_cast['common_input']['same_prefix_order']
    assert nomad_cast['same_input_comparison']['same_accepted_root_property']
    assert nomad_cast['same_input_comparison']['same_transaction_hashes_as_btg']
    assert nomad_cast['same_input_comparison']['uses_btg_oracle'] is False
    assert nomad_cast['same_input_comparison']['all_prefix_rows_agree']
    assert nomad_cast['archive_storage_transition']['transition'] == '0x0 -> 0x1'
    assert nomad_cast['archive_storage_transition']['before']['mapping_storage_value'].endswith('0')
    assert nomad_cast['archive_storage_transition']['after']['mapping_storage_value'].endswith('1')
    assert nomad_cast_sequence['status'] == 'complete'
    assert nomad_cast_sequence['transaction_count'] == 5
    assert nomad_cast_sequence['transaction_hashes'] == nomad_sequence['transaction_hashes']
    assert nomad_cast_sequence['state_input_sha256'] == nomad_sequence['state_input_sha256']
    assert nomad_cast_sequence['same_input']['same_state_fields']
    assert nomad_cast_sequence['same_input']['agrees_with_btg']
    assert nomad_cast_sequence['summary'] == {'pass': 0, 'violation': 5, 'unknown': 0}
    assert hashlib.sha256((ROOT/'experiments'/'run_foundry_nomad_transaction_sequence.py').read_bytes()).hexdigest() == nomad_cast_sequence['runner_sha256']
    for item in nomad_cast_sequence['raw_manifest']:
        assert hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest() == item['sha256'], item['path']
    assert nomad_souffle['status'] == 'complete'
    assert nomad_souffle['common_input']['transaction_hashes'] == nomad_cast['common_input']['transaction_hashes']
    assert nomad_souffle['common_input']['property'] == nomad_cast['property']
    assert nomad_souffle['same_input_comparison']['same_accepted_root_property']
    assert nomad_souffle['same_input_comparison']['same_transaction_hashes_as_btg']
    assert nomad_souffle['same_input_comparison']['uses_btg_oracle'] is False
    assert nomad_souffle['same_input_comparison']['agrees_with_cast_state_checker']
    assert nomad_souffle['same_input_comparison']['agrees_with_btg']
    assert nomad_souffle['summary'] == {'pass': 0, 'violation': 4, 'unknown': 0}
    assert souffle_oracle_tests['status'] == 'complete'
    assert souffle_oracle_tests['all_cases_mutually_exclusive']
    assert souffle_oracle_tests['expected_partition'] == {
        'complete_violation': 'VIOLATION', 'missing_observation': 'UNKNOWN',
        'complete_wrong_attribute': 'PASS', 'complete_invalid_attribute': 'UNKNOWN'}
    assert nomad_sequence['status'] == 'complete'
    assert nomad_sequence['analysis']['all_complete']
    assert len(nomad_sequence['transactions']) == 5
    assert nomad_sequence['analysis']['btg_results'] == ['VIOLATION'] * 5
    assert nomad_sequence['analysis']['terminal_result'] == 'VIOLATION'
    assert hashlib.sha256((ROOT/'experiments'/'run_nomad_transaction_sequence.py').read_bytes()).hexdigest() == nomad_sequence['source_sha256']
    assert nomad_sequence_btg['status'] == 'complete' and nomad_sequence_btg['same_input']
    assert nomad_sequence_btg['state_input_sha256'] == nomad_sequence['state_input_sha256']
    assert nomad_sequence_btg['summary'] == {'pass': 0, 'violation': 5, 'unknown': 0}
    assert nomad_terminal['status'] == 'complete' and nomad_terminal['same_input']
    assert nomad_terminal['state_input_sha256'] == nomad_sequence['state_input_sha256']
    assert nomad_terminal['decision'] == 'VIOLATION'
    for row in nomad_sequence['transactions'][2:]:
        assert row['effects']['logs']['process'] and row['effects']['logs']['receive']
        assert row['pre_state']['message_status'].endswith('0')
        assert row['post_state']['message_status'].endswith('2')
    assert nomad_sequence_souffle['status'] == 'complete'
    assert nomad_sequence_souffle['state_input_sha256'] == nomad_sequence['state_input_sha256']
    assert nomad_sequence_souffle['same_input']['same_state_input']
    assert nomad_sequence_souffle['same_input']['agrees_with_btg']
    assert nomad_sequence_souffle['summary'] == {'pass': 0, 'violation': 5, 'unknown': 0}
    # Bind the displayed rule decisions to the actual facts and external output,
    # rather than trusting the comparison report's boolean agreement flags.
    assert hashlib.sha256((ROOT/nomad_souffle['rules']).read_bytes()).hexdigest() == nomad_souffle['rule_sha256']
    for item in nomad_souffle['facts'] + nomad_souffle['output_manifest']:
        assert hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest() == item['sha256'], item['path']
    souffle_dir = RESULTS/'tool_comparison'/'souffle_nomad_accepted_root'
    bundle = (ROOT/nomad_souffle['rules']).read_bytes() + b''.join(
        p.read_bytes() for p in sorted((souffle_dir/'facts').glob('*.facts')))
    assert hashlib.sha256(bundle).hexdigest() == nomad_souffle['input_sha256']
    with (souffle_dir/'facts'/'prefix.facts').open(newline='') as handle:
        souffle_prefixes = list(csv.reader(handle, delimiter='\t'))
    with (souffle_dir/'output'/'Decision.csv').open(newline='') as handle:
        decision_rows = list(csv.reader(handle))
    souffle_decisions = {int(index): decision for index, decision in decision_rows}
    assert len(decision_rows) == len(souffle_decisions)
    assert len(souffle_decisions) == len(souffle_prefixes) == 4
    assert souffle_decisions == {row['prefix_index']: row['external_decision'] for row in nomad_souffle['decisions']}
    for fact, archive, row in zip(souffle_prefixes, nomad_cast['prefix_results'], nomad_full['prefix_results']):
        assert int(fact[0]) == row['prefix_index']
        assert fact[1] == row['transaction_hash'] == archive['transaction_hash']
        assert int(fact[2]) == int(archive['transaction_block']) == int(row['block'])
        assert int(fact[3]) == int(archive['state_block'])
    btg94 = [row['status'] for row in btg_by_case['uniswap_proposal_94']['transactions']]
    independent94 = [row['status'] for row in independent_prefix['prefix_decisions']]
    assert btg94 == independent94
    assert mythril['status'] == 'completed'
    assert mythril['input']['source'] == 'experiments/Fixtures.sol'
    assert foundry['status'] == 'complete'
    assert foundry['input']['proposal_id'] == 94
    assert foundry['input']['proposal_page_sha256'] == replay['proposal_page_sha256']
    assert foundry['input']['property'] == replay['policy']['name']
    assert foundry['input']['transaction_hashes'] == [row['transaction_hash'] for row in replay['cross_domain_prefix']]
    assert foundry['summary'] == {'pass': 3, 'violation': 3, 'unknown': 0}
    assert foundry['comparison']['same_decisions']
    assert independent29['status'] == 'complete'
    assert independent29['input']['proposal_id'] == 29
    assert independent29['summary'] == {'pass': 3, 'violation': 1, 'unknown': 0}
    assert independent29['comparison']['same_decisions']
    assert isolated29['status'] == 'complete'
    assert isolated29['conclusion']['same_calldata']
    assert isolated29['conclusion']['same_caller']
    assert isolated29['conclusion']['before_repair_reverts']
    assert isolated29['conclusion']['after_repair_succeeds']
    assert isolated29['conclusion']['isolated_replay_passed']
    assert archive29['status'] == 'complete'
    assert archive29['conclusion']['same_calldata']
    assert archive29['conclusion']['same_caller']
    assert archive29['conclusion']['same_target']
    assert archive29['conclusion']['before_repair_reverts']
    assert archive29['conclusion']['after_repair_succeeds']
    assert archive29['conclusion']['archive_fork_replay_passed']
    assert proposal29_terminal['status'] == 'complete'
    assert proposal29_terminal['comparison']['same_history']
    assert proposal29_terminal['comparison']['same_property']
    assert proposal29_terminal['comparison']['terminal_misses_prefix_violation']
    assert proposal29_terminal['btg_prefix_decisions'] == ['PASS', 'VIOLATION', 'PASS']
    assert proposal29_terminal['terminal_check']['decision'] == 'PASS'
    assert hashlib.sha256((ROOT/'experiments'/'run_proposal29_terminal_prefix_check.py').read_bytes()).hexdigest() == proposal29_terminal['runner_sha256']
    assert echidna29['status'] == 'complete'
    assert echidna29['input']['proposal_id'] == 29
    assert echidna29['same_input']['same_target']
    assert echidna29['same_input']['same_caller']
    assert echidna29['same_input']['same_calldata']
    assert echidna29['same_input']['same_owner_attribute'] == 'V3Factory.owner() / storage slot 3'
    assert echidna29['same_input']['same_historical_code_hash']
    assert echidna29['results']['pre_repair']['normalized_btg_result'] == 'VIOLATION'
    assert echidna29['results']['post_repair']['normalized_btg_result'] == 'PASS'
    assert scale['status'] == 'complete'
    assert scale['summary']['fixtures'] == 192
    assert scale['summary']['methods']['exhaustive_prefix']['orders'] == 1479360
    assert scale['summary']['methods']['property_aware_por']['orders'] == 35874
    assert scale['summary']['methods']['property_aware_por']['missed_models'] == 0
    for data,key,filename in [(evm,'runner_sha256','run_evm.py'),
                              (sched,'runner_sha256','run_schedules.py'),
                              (cross,'runner_sha256','validate_reduction.py'),
                              (cross,'schedule_runner_sha256','run_schedules.py')]:
        assert data[key]==hashlib.sha256((ROOT/'experiments'/filename).read_bytes()).hexdigest(), 'Stale runner results: '+filename
    methods=sched['methods']
    names=['exhaustive_prefix','exhaustive_final','fixed_order_prefix','storage_only_por','property_aware_por','persistent_property_por']
    labels=['Exhaustive prefixes','Exhaustive final state','Fixed order','Storage-only POR','Property-aware POR','Persistent-set POR']
    text=['% Generated from raw results by experiments/build_evidence.py.',
          r'\begin{table}[t]\centering\small',
          r'\caption{Constructed schedule models. Misses count models with a violation found by exhaustive prefix checking but absent from the indicated method.}',
          r'\label{tab:schedule}',r'\begin{tabular}{@{}lrr@{}}\toprule',
          r'Method & Orders & Misses / 120 \\ \midrule']
    for method,label in zip(names,labels):
        d=methods[method];text.append(f"{label} & {d['orders']:,} & {d['missed_models']} \\\\")
    text += [r'\bottomrule\end{tabular}\end{table}']
    (RESULTS/'schedule_table.tex').write_text('\n'.join(text)+'\n',encoding='utf-8')
    access=next(r['observed'] for r in runs if r['case']=='access_list')
    facts={'EvmCases':evm['cases'],'EvmPasses':evm['passed'],'EvmTransactions':evm['transactions'],
           'ScheduleFixtures':sched['fixtures'],'EmptyListGas':access['empty_list_gas'],
           'PopulatedListGas':access['populated_list_gas'],
           'PublicProposals':public_summary['proposal_count'],
           'PublicCandidates':public_summary['keyword_candidate_count'],
           'ReplayChains':len(replay['chains']),
           'ReplaySourceBlock':replay['source_execution']['block'],
           'ReplayPrefixViolations':int(replay['policy']['prefix_violation_found']),
           'ReplayFinalOnlyMisses':int(replay['policy']['final_only_misses_prefix']),
           'ReplayOracleCases':len(oracle_tests['cases']),
           'AudiusTransactions':audius['derived_checks']['transaction_count'],
           'AudiusInitializerViolation':int(audius['derived_checks']['initializer_prefix_violation']),
           'AudiusPermissionChanges':audius['derived_checks']['permission_changed_field_count'],
           'AudiusTreasuryOutflow':f"{audius['derived_checks']['treasury_audio_outflow']:.2f}",
           'BTGRealCases':len(btg['cases']),
           'BTGRealTransactions':sum(len(case['transactions']) for case in btg['cases']),
           'BTGUnknowns':sum(case['summary']['unknown'] for case in btg['cases']),
           'AdditionalCrossChainCases':len(additional['cases']),
           'ProposalTwentyNineArchiveFork':int(archive29['conclusion']['archive_fork_replay_passed']),
           'ProposalFortyThreePasses':btg_by_case[43]['summary']['pass']}
    facts.update({
           'NomadAttackTransactions': len(nomad['historical_input']['selected_attack_hashes']),
           'NomadAttackViolations': nomad['summary']['violation'],
           'NomadExternalOutputs': len(xchain['output_manifest']),
           'NomadExternalMatches': len(xchain['selected_output_rows']['SC_WithdrawalsWithoutMatch.csv']),
           'NomadSameSignal': int(nomad['independent_comparison']['same_attack_prefix_signal'])})
    facts.update({
           'NomadCompletePrefixTransactions': nomad_full['historical_prefix']['transaction_count'],
           'NomadCompletePrefixAttackAgreement': int(nomad_full['same_input']['attack_rows_agree']),
           'NomadAcceptedRootExternalAgreement': int(nomad_cast['same_input_comparison']['all_prefix_rows_agree']),
           'NomadStorageTransitionVerified': int(nomad_cast['archive_storage_transition']['transition'] == '0x0 -> 0x1'),
           'NomadSouffleAgreement': int(nomad_souffle['same_input_comparison']['agrees_with_btg'])})
    facts.update({
           'NomadTransactionSequenceTransactions': len(nomad_sequence['transactions']),
           'NomadTransactionSequenceViolations': nomad_sequence['analysis']['btg_results'].count('VIOLATION'),
           'NomadTransactionSequenceStateHash': nomad_sequence['state_input_sha256'][:12],
           'SouffleOracleMutualExclusion': int(souffle_oracle_tests['all_cases_mutually_exclusive'])})
    facts.update({
           'IndependentProposalTwentyNinePass': independent29['summary']['pass'],
           'IndependentProposalTwentyNineViolations': independent29['summary']['violation'],
           'ProposalTwentyNineIsolatedReplay': int(isolated29['conclusion']['isolated_replay_passed']),
           'ProposalTwentyNineEchidnaViolation': int(echidna29['results']['pre_repair']['normalized_btg_result']=='VIOLATION'),
           'ProposalTwentyNineEchidnaPass': int(echidna29['results']['post_repair']['normalized_btg_result']=='PASS'),
           'ScaleFixtures': scale['summary']['fixtures'],
           'ScaleReferenceOrders': scale['summary']['methods']['exhaustive_prefix']['orders'],
           'ScaleBTGOrders': scale['summary']['methods']['property_aware_por']['orders'],
           'ScaleBTGMissed': scale['summary']['methods']['property_aware_por']['missed_models'],
           'ScaleFinalMissed': scale['summary']['methods']['exhaustive_final']['missed_models'],
           'ScaleStorageMissed': scale['summary']['methods']['storage_only_por']['missed_models']})
    facts.update({
            'ScalePersistentOrders': scale['summary']['methods']['persistent_property_por']['orders'],
            'ScalePersistentMissed': scale['summary']['methods']['persistent_property_por']['missed_models'],
            'UniswapAdapterCases': uniswap_adapter['summary']['cases'],
            'NomadFiveTxCastAgreement': int(nomad_cast_sequence['same_input']['agrees_with_btg'])})
    graph_sparse = [r for r in dependency['construction'] if r['n']==512 and r['family']=='denser']
    graph_dense = [r for r in dependency['construction'] if r['n']==512 and r['family']=='storage_clique']
    facts.update({
        'DependencyConstructionFixtures': dependency['summary']['construction_fixtures'],
        'DependencyExplorationFixtures': dependency['summary']['exploration_fixtures'],
        'DependencySparseMS': f"{median(r['median_build_ms'] for r in graph_sparse):.2f}",
        'DependencySparseMiB': f"{median(r['python_peak_bytes'] for r in graph_sparse)/2**20:.2f}",
        'DependencyDenseMS': f"{median(r['median_build_ms'] for r in graph_dense):.2f}",
        'DependencyDenseMiB': f"{median(r['python_peak_bytes'] for r in graph_dense)/2**20:.2f}",
    })
    graph_rows = [r'\begin{table}[t]\centering\scriptsize\setlength{\tabcolsep}{2pt}',
        r'\caption{Dependency-graph construction on declared overwrite models. Each time is the median of three seed-level medians (seven runs each); peak is the median Python allocation peak from separate untimed runs, in KiB. $e$ counts distinct undirected edges; $d=e/\binom{n}{2}$. Rows with $m=0,e>0$ are same-slot storage cliques.}',
        r'\label{tab:dependency-construction}',
        r'\begin{tabular}{@{}rrrrrr@{}}\toprule',
        r'$n$ & $m$ & $e$ & $d$ (\%) & Build (ms) & Peak (KiB) \\',
        r'\midrule']
    for n in (32, 128, 512):
        for family in ('invisible', 'sparse', 'denser', 'storage_clique'):
            group = [r for r in dependency['construction'] if r['n']==n and r['family']==family]
            assert len(group) == 3
            graph_rows.append(f"{n} & {group[0]['m']} & {group[0]['edges']:,} & "
                f"{100*median(r['density'] for r in group):.2f} & "
                f"{median(r['median_build_ms'] for r in group):.2f} & "
                f"{median(r['python_peak_bytes'] for r in group)/1024:,.1f} " + r'\\')
        if n != 512:
            graph_rows.append(r'\midrule')
    graph_rows += [r'\bottomrule\end{tabular}\end{table}',
        r'\begin{table}[t]\centering\scriptsize\setlength{\tabcolsep}{3pt}',
        r'\caption{Matched end-to-end exploration at eight actions (40,320 exhaustive orders per fixture). Times include DFS, prefix evaluation, and outcome aggregation; cached time also includes graph construction. Each value is a median across two seed-level medians, with three timings per seed. Raw per-seed results for 4, 6, and 8 actions are retained.}',
        r'\label{tab:dependency-exploration}',
        r'\begin{tabular}{@{}rrrrr@{}}\toprule',
        r'$m$ & $d$ (\%) & Retained orders & Online (ms) & Cached (ms) \\ \midrule']
    for m in (0, 4, 8, 28):
        group = [r for r in dependency['exploration'] if r['n']==8 and r['m']==m]
        assert len(group) == 2
        graph_rows.append(f"{m} & {100*median(r['density'] for r in group):.2f} & "
            f"{median(r['retained_orders'] for r in group):,.0f} & "
            f"{median(r['median_online_ms'] for r in group):.2f} & "
            f"{median(r['median_cached_total_ms'] for r in group):.2f} " + r'\\')
    graph_rows += [r'\bottomrule\end{tabular}\end{table}']
    (RESULTS/'dependency_overhead_table.tex').write_text('\n'.join(graph_rows)+'\n', encoding='utf-8')
    facts_text='\n'.join('\\newcommand{\\'+k+'}{'+str(v)+'}' for k,v in facts.items())
    (RESULTS/'facts.tex').write_text(facts_text+'\n',encoding='utf-8')
    rows=['% Generated by experiments/build_evidence.py from the saved public-data summary.',
          r'\begin{table}[t]\centering\small',
          r'\caption{Descriptive public-governance corpus retrieved from Snapshot. Keyword candidates are retained for evidence binding.}',
          r'\label{tab:public-corpus}',r'\begin{tabular}{@{}lrr@{}}\toprule',
          r'Year & Proposals & Keyword candidates \\ \midrule']
    for year, values in sorted(public_summary['by_year'].items()):
        rows.append(f"{year} & {values['proposals']} & {values['keyword_candidates']} \\\\")
    rows += [r'\bottomrule',r'\end{tabular}',r'\end{table}']
    (RESULTS/'table.tex').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    analyzed_ids = [replay['proposal_id']] + sorted(case['proposal_id'] for case in additional['cases'])
    supported_count = len(analyzed_ids)
    excluded_count = public_meta['keyword_candidate_count'] - supported_count
    coverage_rows=['% Generated by experiments/build_evidence.py from the saved public-data and replay manifests.',
                   r'\begin{table}[t]\centering\scriptsize\setlength{\tabcolsep}{2pt}',
                   r'\caption{Coverage accounting from the candidate population to the evidence-backed replay set. Excluded candidates receive no security label; all supported records in this artifact are analyzed.}',
                   r'\label{tab:coverage-accounting}',
                   r'\begin{tabular}{@{}p{0.21\linewidth}p{0.43\linewidth}r p{0.20\linewidth}@{}}\toprule',
                   r'Stage & Inclusion rule & Count & Records / treatment \\ \midrule',
                   f"Candidate population & All closed Snapshot proposals retrieved under the fixed query & {public_meta['proposal_count']} & corpus " + r"\\",
                   f"Keyword candidates & Case-insensitive hit in title or body using the fixed keyword list & {public_meta['keyword_candidate_count']} & sampling frame " + r"\\",
                   f"Supported for replay & Exact execution transaction, route/ABI, and archived destination evidence retained & {supported_count} & {', '.join(map(str, analyzed_ids))} " + r"\\",
                   f"Excluded before classification & Candidate lacks the complete pinned evidence bundle in this artifact & {excluded_count} & no security label " + r"\\",
                   f"Analyzed & Every supported record replayed by the real-history adapter and BTG & {supported_count} & {', '.join(map(str, analyzed_ids))} " + r"\\",
                   r'\bottomrule',r'\end{tabular}',r'\end{table}']
    (RESULTS/'coverage_accounting_table.tex').write_text('\n'.join(coverage_rows)+'\n',encoding='utf-8')
    related_rows=['% Generated by experiments/build_evidence.py from the cited system descriptions and BTG artifact contract.',
                  r'\begin{table}[t]\centering\tiny\setlength{\tabcolsep}{2pt}',
                  r'\caption{Related-system comparison. Each system is evaluated against the question its input and output are designed to answer; a different question is not treated as a false negative.}',
                  r'\label{tab:related-systems}',
                  r'\begin{tabular}{@{}p{0.20\linewidth}p{0.19\linewidth}p{0.24\linewidth}p{0.28\linewidth}@{}}\toprule',
                  r'System & Primary input & Sequence / state boundary & Question answered \\ \midrule',
                  r'BTG & Supplied protocol norm, action effects, receipts, logs, and state witnesses & Cross-domain transaction prefixes; property dependencies; tri-state evidence decisions & Does the declared norm hold at each observed boundary, and can a reviewer audit the decision? \\',
                  r'XChainWatcher~\cite{augusto2025xchainwatcher} & Bridge-specific facts and released Datalog rules & Matched bridge-side deposits, withdrawals, and lifecycle events & Is there a bridge anomaly under the supplied bridge model? \\',
                  r'Echidna~\cite{echidna,echidnarepo} / SMARTIAN~\cite{choi2021smartian} & Contract code, ABI, and user properties & Generated transaction sequences guided by property or data-flow feedback & Can a generated contract sequence falsify a code-level property? \\',
                  r'Slither~\cite{feist2019slither,slitherrepo} / Mythril~\cite{mythril} & Solidity source or EVM bytecode & Local detector and bounded symbolic-analysis boundaries & Does the contract exhibit a known local pattern or reachable symbolic warning? \\',
                  r'Terminal-state checker & Same historical input and declared property & Final post-state only; no earlier boundary observations & Does the final committed state satisfy the declared property? \\',
                  r'\bottomrule',r'\end{tabular}',r'\end{table}']
    (RESULTS/'related_system_comparison_table.tex').write_text('\n'.join(related_rows)+'\n',encoding='utf-8')
    replay_rows=['% Generated by experiments/build_evidence.py from the saved proposal-94 replay.',
                 r'\begin{table}[t]\centering\scriptsize',
                 r"\caption{Six-transaction replay of Uniswap proposal 94. ``new'' and ``old'' abbreviate the declared V3 owner and V2 feeTo values; full addresses and receipts are retained in the artifact.}",
                 r'\label{tab:real-replay}',r'\begin{tabular}{@{}p{0.20\linewidth}p{0.20\linewidth}p{0.17\linewidth}p{0.25\linewidth}@{}}\toprule',
                 r'Domain / update & Block / tx & V3 / V2 after tx & Prefix oracle \\ \midrule']
    for row in replay['cross_domain_prefix']:
        operation = 'V3 owner' if row['operation'].startswith('V3Factory') else 'V2 feeTo'
        result = row['prefix_oracle']['status']
        v3_state = 'new' if row['state_after']['v3_owner'].lower() == replay['chains'][row['chain']]['expected_v3_owner'].lower() else 'old'
        v2_state = 'new' if row['state_after']['v2_fee_to'].lower() == replay['chains'][row['chain']]['expected_v2_fee_to'].lower() else 'old'
        replay_rows.append(f"{row['chain']} ({operation}) & {row['block']:,} / {row['transaction_index']} & {v3_state} / {v2_state} & {result}; active {len(row['active_domains'])}/{len(replay['chains'])} " + r"\\")
    replay_rows += [r'\bottomrule',r'\end{tabular}',r'\end{table}']
    (RESULTS/'real_replay_table.tex').write_text('\n'.join(replay_rows)+'\n',encoding='utf-8')
    audius_btg=btg_by_case['audius_governance_takeover']
    audius_statuses=[row['status'] for row in audius_btg['transactions']]
    audius_rows=['% Generated by experiments/build_evidence.py from the saved Audius incident replay and BTG output.',
                 r'\begin{table}[t]\centering\scriptsize',
                 r'\caption{Unified replay of Audius proposals 82--85. BTG recomputes the tri-state result from receipts, event logs, and independent permission-state reads; exact evidence is retained in the artifact.}',
                 r'\label{tab:audius-incident}',r'\begin{tabular}{@{}p{0.20\linewidth}p{0.10\linewidth}p{0.34\linewidth}p{0.16\linewidth}@{}}\toprule',
                 r'Prefix class & IDs & Transaction-level witness & Result \\ \midrule',
                 f"Initialization corruption & 82, 83 & 15201736; {audius['derived_checks']['permission_changed_field_count']} permission reads changed & {audius_statuses[0]} " + r"\\",
                 f"Quorum guard & 84 & 15201794; defeated state; no vote & {audius_statuses[1]} " + r"\\",
                 f"Successful transfer & 85 & 15201799; executed; 18.56M AUDIO out & {audius_statuses[3]} " + r"\\"]
    audius_rows += [r'\bottomrule',r'\end{tabular}',r'\end{table}']
    (RESULTS/'audius_incident_table.tex').write_text('\n'.join(audius_rows)+'\n',encoding='utf-8')
    additional_rows=['% Generated by experiments/build_evidence.py from additional real cross-chain replays and BTG output.',
                     r'\begin{table}[t]\centering\scriptsize',
                     r'\caption{Additional real Uniswap cross-chain governance cases. Proposal 29 joins a repair boundary with a later governance use and records the resulting permission consequence; Proposal 43 records an official bridge-authority migration and its permission boundary.}',
                     r'\label{tab:additional-crosschain}',r'\begin{tabular}{@{}p{0.08\linewidth}p{0.13\linewidth}p{0.16\linewidth}p{0.18\linewidth}p{0.20\linewidth}@{}}\toprule',
                     r'Prop. & Norm & Evidence & BTG & Permission consequence \\ \midrule']
    for case in additional['cases']:
        if case['proposal_id']==69:
            witness='L1/Base state'
            property_label='normal async'
            consequence='pending allowed'
        elif case['proposal_id']==29:
            witness='L1/L2 repair + P94 use'
            property_label='official owner repair'
            consequence='governance unusable before repair; alias later succeeds'
        else:
            witness='L1/Celo + owner event'
            property_label='official authority migration'
            consequence='authority moves to approved receiver'
        additional_rows.append(f"{case['proposal_id']} & {property_label} & {witness} & {case['btg_result']} & {consequence} " + r"\\")
    additional_rows += [r'\bottomrule',r'\end{tabular}',r'\end{table}']
    (RESULTS/'additional_crosschain_table.tex').write_text('\n'.join(additional_rows)+'\n',encoding='utf-8')
    norm_rows=['% Generated by experiments/build_evidence.py from the official Proposal 29 text and the saved BTG evidence.',
               r'\begin{table}[t]\centering\scriptsize',
               r'\caption{Proposal 29 norm-to-property mapping. The quoted statements are from the official proposal. The temporal quantifier is made explicit by BTG for the committed Arbitrum owner boundaries; it is not inferred from an execution label.}',
               r'\label{tab:proposal29-norm-mapping}',
               r'\begin{tabular}{@{}p{0.30\linewidth}p{0.32\linewidth}p{0.28\linewidth}@{}}\toprule',
               r'Official statement & Formal property / decision & Bound evidence \\ \midrule',
               r"``The Uniswap Factory was deployed with the owner set to the same, unaliased address of the L1 Uniswap Timelock.'' ``Therefore, nobody can execute governance proposals on Arbitrum in the current state.''~\cite{uniswapproposal29} & ",
               r'$\varphi_{29}(S_t)\equiv owner_{Arb}(S_t)=alias(Timelock_{L1})$ at each observed committed Arbitrum owner boundary. A different value is \textsc{violation}. & ',
               r'Pre-repair owner read; contract address; archived block and code/storage witness \\',
               r"The proposal instructs governance to send a cross-chain message that sets the owner to the L1 Timelock's address alias~\cite{uniswapproposal29} & ",
               r'A successful repair effect must produce $owner_{after}=alias(Timelock_{L1})$; missing or malformed owner/event evidence is \textsc{unknown}. & ',
               r'L1 calldata and receipt; destination OwnerChanged log; post-repair owner read \\',
               r"``Once this is complete, cross-chain governance between Uniswap and Arbitrum will be fully functional.''~\cite{uniswapproposal29} & ",
               r'The later governance-use transaction is a consequence check: the same alias caller must be accepted by the factory $\texttt{setOwner}$ call. & ',
               r'Proposal 94 calldata/caller, receipt status, and before/after owner witness \\',
               r'\bottomrule',r'\end{tabular}',r'\end{table}']
    (RESULTS/'proposal29_norm_mapping_table.tex').write_text('\n'.join(norm_rows)+'\n',encoding='utf-8')
    sequence_decisions = {row['prefix_index']: row['external_decision'] for row in nomad_sequence_souffle['decisions']}
    sequence_btg_decisions = {row['tx_index']: row['decision'] for row in nomad_sequence_btg['decisions']}
    sequence_cast_decisions = {row['tx_index']: row['decision'] for row in nomad_cast_sequence['transactions']}
    nomad_rows=['% Generated from trace-derived Nomad transaction sequence and hash-verified Souffle output relations.',
                r'\begin{table*}[t]\centering\scriptsize\setlength{\tabcolsep}{3pt}',
                r'\caption{Nomad transaction-level comparison. V = VIOLATION. The adapter obtains calldata, receipts, logs, and pre/post storage diffs from the archive RPC for the deployment, upgrade, and three attack transactions. BTG, the independent archive-state validator, the separate accepted-root rule executed by Souffl\'e, and the terminal projection use the same five-transaction state-input hash and executable-state invariant. The deployment row is a code-absent pre-state boundary whose post-state is the first executable Replica observation; the attack rows have independent pre=0/post=2 message states within the shared block.}',
                r'\label{tab:nomad-attack}',
                r'\begin{tabular}{@{}p{0.13\linewidth}p{0.24\linewidth}p{0.16\linewidth}cccc@{}}\toprule',
                r'Row / transaction & Extracted effect & Pre $\rightarrow$ post state & BTG & Souffl\'e & Archive validator & Terminal \\ \midrule']
    for row in nomad_sequence['transactions']:
        effects = row['effects']
        if effects['logs']['process']:
            observed = f"Process + Receive; {effects['logs']['receive'][0]['amount'] / 10**8:g} WBTC"
            transition = f"message 0 $\\rightarrow$ 2; pre {row['pre_state']['block']:,}"
        else:
            observed = f"selector {effects['selector']}; {len(effects['storage_diff'])} target slots changed"
            transition = f"root witness; {row['pre_state']['block']:,} $\\rightarrow$ {row['post_state']['block']:,}"
        terminal_cell = 'V (final)' if row['tx_index'] == len(nomad_sequence['transactions']) and nomad_terminal['decision'] == 'VIOLATION' else '--'
        status = sequence_btg_decisions[row['tx_index']]
        ext = sequence_decisions[row['tx_index']]
        cast = sequence_cast_decisions[row['tx_index']]
        nomad_rows.append(f"{row['tx_index']} / \\texttt{{{row['transaction_hash'][:10]}...}} & {observed} & {transition} & "
            f"{'V' if status == 'VIOLATION' else status} & {'V' if ext == 'VIOLATION' else ext} & "
            f"{'V' if cast == 'VIOLATION' else cast} & {terminal_cell} " + r'\\')
    nomad_rows += [r'\bottomrule',r'\end{tabular}',
        r'\par\smallskip\parbox{0.97\linewidth}{\textit{Provenance.} The five transaction hashes, complete raw JSON responses, trace pre/post accounts, storage-diff keys, decoded Process/Receive effects, independent archive calls, rule SHA-256, state-input hash, and all Souffl\'e relations are retained. The deployment boundary is not treated as a missing row: its absent pre-state is explicit. The terminal cell is a final-post-state projection over this same state-input bundle.}',
        r'\end{table*}']
    (RESULTS/'nomad_attack_table.tex').write_text('\n'.join(nomad_rows)+'\n',encoding='utf-8')
    isolation_rows=['% Generated by experiments/build_evidence.py from the Proposal 29 isolated and archive-fork replays.',
                    r'\begin{table}[t]\centering\scriptsize',
                     r'\caption{Proposal 29 repair-boundary replay. The same Proposal 94 calldata and alias caller revert before the committed repair and succeed after it on a Foundry archive fork; the read-only state-override result is retained as a complementary check.}',
                    r'\label{tab:proposal29-isolation}',
                    r'\begin{tabular}{@{}p{0.19\linewidth}p{0.26\linewidth}p{0.23\linewidth}p{0.11\linewidth}@{}}\toprule',
                    r'State & Injected owner & Calldata / caller & Result \\ \midrule',
                    r'Before repair & unaliased L1 Timelock & setOwner; alias caller & ' + isolated29['calls']['before_repair']['status'] + r' \\',
                     r'After repair & repaired aliased owner & same calldata / caller & ' + isolated29['calls']['after_repair']['status'] + r' \\',
                     r'Archive fork & real pre/post code + storage & same calldata / caller & REVERT $\rightarrow$ PASS \\',
                    r'\bottomrule',r'\end{tabular}',r'\end{table}']
    (RESULTS/'proposal29_isolation_table.tex').write_text('\n'.join(isolation_rows)+'\n',encoding='utf-8')
    mythril_status = 'completed' if mythril['status'] == 'completed' else 'inconclusive'
    foundry_status = '3 violation / 3 pass' if foundry['status'] == 'complete' else 'incomplete'
    nomad_cast_status = '4 violation' if nomad_cast['summary']['violation'] == 4 else 'incomplete'
    nomad_cast_sequence_status = '5 violation' if nomad_cast_sequence['summary']['violation'] == 5 else 'incomplete'
    comparison_rows=['% Generated by experiments/build_evidence.py from the same proposal-94 input and complementary baselines.',
                     r'\begin{table}[t]\centering\scriptsize',
                     r'\caption{External comparison. The Proposal 94 rows use identical historical inputs; the Proposal 29 Echidna row uses the identical target, caller, calldata, owner attribute, and archived code/storage witnesses. The Nomad rows use the complete five-transaction state input and executable-state accepted-root invariant. Mythril provides a complementary analysis.}',
                     r'\label{tab:tool-comparison}',r'\begin{tabular}{@{}p{0.22\linewidth}p{0.25\linewidth}p{0.42\linewidth}@{}}\toprule',
                     r'Tool & Result & Evidence boundary \\ \midrule',
                     r'BTG & 3 violation / 3 pass & six transaction boundaries; three partial pairs \\',
                     r'Independent prefix checker & 3 violation / 3 pass & same six hashes, property, and state witnesses \\',
                     f'Foundry cast & {foundry_status} & raw receipt/transaction plus archive calls; same six hashes and prefix order \\\\',
                     r'Foundry Anvil + cast & REVERT $\rightarrow$ PASS & same Proposal 29 calldata/caller on real pre/post archive forks ' + r'\\',
                     f'Independent Proposal 29 checker & {independent29["summary"]["violation"]} violation / {independent29["summary"]["pass"]} pass & same four boundaries, property, and saved witnesses \\\\',
                     r'Echidna 2.3.3 & VIOLATION / PASS & same Proposal 29 target/caller/calldata; archived code and slot 3; external property engine \\',
                     r'Archive terminal check & pass & same six hashes, property, and terminal blocks \\',
                       f'Archive-state validator / cast / Nomad & {nomad_cast_sequence_status} & same five-transaction prefix and executable-state accepted-root invariant; every state field agrees with the adapter; raw output retained \\\\',
                       f'Souffle/Datalog / Nomad & {nomad_sequence_souffle["summary"]["violation"]} violation & separate rules; same five-transaction state hash and property; all relations retained \\\\',
                      f'Mythril & {mythril_status} & Effects fixture; bounded symbolic analysis; {mythril.get("finding_count", 0)} high-severity finding(s) \\\\',
                     r'\bottomrule',r'\end{tabular}',r'\end{table}']
    (RESULTS/'tool_comparison_table.tex').write_text('\n'.join(comparison_rows)+'\n',encoding='utf-8')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9})
    with (RESULTS/'schedules'/'runs.csv').open(newline='') as f: records=list(csv.DictReader(f))
    fig,axs=plt.subplots(1,2,figsize=(9,3.2),layout='constrained')
    colors=['#555555','#b34747','#14395b','#6b4e9b']
    for name,label,color in zip(['exhaustive_prefix','storage_only_por','property_aware_por','persistent_property_por'],
                                ['Exhaustive','Storage-only POR','Property-aware POR','Persistent-set POR'],colors):
        totals=[sum(int(r['orders']) for r in records if r['method']==name and int(r['n'])==n) for n in (3,4,5,6)]
        axs[0].plot((3,4,5,6),totals,'o-',label=label,color=color)
    axs[0].set_yscale('log');axs[0].set_xticks([3,4,5,6]);axs[0].set_xlabel('Actions per model')
    axs[0].set_ylabel('Total complete orders (32 models each)');axs[0].legend(fontsize=8)
    axs[0].grid(alpha=.2)
    miss_names=names[1:]; miss_labels=['Final\nonly','Fixed\norder','Storage\nPOR','Property\nPOR','Persistent\nPOR']
    bars=axs[1].bar(miss_labels,[methods[x]['missed_models'] for x in miss_names],color=['#999999','#c98b57','#b34747','#14395b','#6b4e9b'])
    axs[1].bar_label(bars);axs[1].set_ylim(0,100);axs[1].set_ylabel('Missed unsafe constructed models / 120')
    fig.savefig(ROOT/'figures'/'verified_schedules.pdf');plt.close(fig)
    # A deterministic conceptual plot of the two actually executed EVM traces.
    prefix=next(r['observed']['traces'] for r in runs if r['case']=='prefix_order')
    fig,ax=plt.subplots(figsize=(4.4,2.4),layout='constrained')
    for trace,label,color in zip(prefix,['x then y','y then x'],['#14395b','#b34747']):
        margins=[0]+[p['state'][0]-p['state'][1] for p in trace['prefixes']]
        ax.plot([0,1,2],margins,'o-',label=label,color=color)
    ax.axhline(0,color='gray',linewidth=.7);ax.set_xticks([0,1,2]);ax.set_yticks([-1,0,1])
    ax.set_xlabel('Delivered updates');ax.set_ylabel('Observed x - y');ax.legend(fontsize=8)
    fig.savefig(ROOT/'figures'/'verified_prefix.pdf');plt.close(fig)
    # Freeze versions actually present, including transitives, for reproducibility.
    packages=sorted(f'{d.metadata["Name"]}=={d.version}' for d in importlib.metadata.distributions())
    (ROOT/'experiments'/'requirements-lock.txt').write_text('\n'.join(packages)+'\n',encoding='utf-8')
    files=[ROOT/'main.tex',ROOT/'references_verified.bib',*sorted((ROOT/'experiments').glob('*.py')),
           ROOT/'experiments'/'Fixtures.sol',ROOT/'experiments'/'Proposal29EchidnaReplay.sol',
           ROOT/'experiments'/'nomad_accepted_root.dl',
           *sorted(RESULTS.rglob('*.json')),*sorted(RESULTS.rglob('*.csv')),
           *sorted((RESULTS/'tool_comparison').rglob('*.txt')),
           *sorted((RESULTS/'tool_comparison').rglob('*.facts'))]
    files += [ROOT/'experiments'/'requirements-lock.txt',ROOT/'README.md',ROOT/'experiments'/'README.md',
              *sorted((RESULTS/'public_governance').glob('*.tex')),
              RESULTS/'real_replay_table.tex',
              RESULTS/'audius_incident_table.tex',
               RESULTS/'tool_comparison_table.tex',
               RESULTS/'nomad_attack_table.tex',
               RESULTS/'scale_ablation.json',
              RESULTS/'scale_ablation_table.tex',
              RESULTS/'dependency_overhead_table.tex',
              RESULTS/'proposal29_isolation_table.tex',
              RESULTS/'proposal29_terminal_prefix_table.tex',
              RESULTS/'proposal29_norm_mapping_table.tex',
              RESULTS/'coverage_accounting_table.tex',
              RESULTS/'related_system_comparison_table.tex',
              ROOT/'experiments'/'appendix_extended_details.tex',
              *sorted((RESULTS/'tool_comparison').glob('*.json')),
              *sorted((RESULTS/'real_replay').glob('*.json')),
              *sorted((RESULTS/'real_replay').glob('*.html')),
              *sorted((ROOT/'figures').glob('verified_*.pdf'))]
    hashes={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files if p.exists() and p.name not in ('checksums.json','semantic_sanity.json')}
    (RESULTS/'checksums.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')
    print('Generated evidence figures, tables, package lock, and checksums.')


if __name__=='__main__':main()
