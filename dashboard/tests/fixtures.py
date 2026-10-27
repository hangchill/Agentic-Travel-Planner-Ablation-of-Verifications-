"""Synthetic persisted dashboard evidence. Never evaluates plans or calls models."""
import hashlib
import json
from pathlib import Path
import tempfile

import pandas as pd

from chinatravel.evaluation.repair_attempt import RepairAttemptRecord
from scripts.result_analysis import build_test_result_tables as team


class Repository:
    def __init__(self, size=3, steps=(1, 2), strategies=('R0', 'R1', 'R2', 'R3', 'R4')):
        self.tmp = tempfile.TemporaryDirectory(prefix='dashboard-fixture-')
        self.root = Path(self.tmp.name)
        self.analysis = self.root / 'results/analysis/repair_strategies'
        self.reporting = self.root / 'test_result_analysis'
        self.manifests, self.rows = {}, {}
        self.strategies = strategies
        for partition in ('TRAIN', 'TEST'):
            for strategy in strategies:
                self.make_run(partition, strategy, size, steps)
        self.write_reporting()

    def close(self):
        self.tmp.cleanup()

    def make_run(self, partition, strategy, size, steps):
        folder = self.root / 'experiments' / f'{"development" if partition == "TRAIN" else "final_test"}-{strategy.lower()}'
        folder.mkdir(parents=True)
        ids = [f'fixture-{i}' for i in range(size)]
        manifest = dict(run_id=f'{partition.lower()}-{strategy}', split_query_source=f'fixture_{partition.lower()}',
                        partition=partition.lower(), repair_strategies_requested=[strategy], query_uids=ids,
                        language='en', max_steps=max(steps, default=0), model_identifier='fixture', sampling_settings={},
                        oracle_translation=True, seed=1, implementation_hash='fixture')
        self.manifests[(partition, strategy)] = (folder, manifest)
        (folder / 'run_manifest.json').write_text(json.dumps(manifest))
        raw, reporting = [], []
        refs = {}
        for uid in ids:
            query = folder / 'queries' / uid
            query.mkdir(parents=True)
            initial_plan = {'itinerary': [{'day': 1, 'activities': [{'position': 'Initial', 'type': 'attraction'}]}]}
            before = [False, True]
            current_plan = initial_plan
            initial_v = {'personal_constraints': before, 'commonsense_errors': ['initial error'], 'translated_plan': initial_plan}
            history = [{'step': 0, 'accepted': True, 'verification': initial_v}]
            local = []
            for index, step in enumerate(steps):
                accepted = not (strategy == 'R2' and index == 0)
                after = ([True, False] if not accepted else [False, True]
                         if strategy == 'R3' and index == 0 else [True, True])
                plan = {'itinerary': [{'day': 1, 'activities': [{'position': f'Round {step}', 'type': 'attraction'}]}]}
                categories = {key: [] for key in ('fixed', 'newly_violated', 'still_failed', 'still_passed', 'unknown')}
                for j, (x, y) in enumerate(zip(before, after), 1):
                    key = 'fixed' if not x and y else 'newly_violated' if x and not y else 'still_passed' if x else 'still_failed'
                    categories[key].append(j)
                metadata = {'editable_slots': [{'day': 0, 'activity_index': 0}]}
                if strategy == 'R4':
                    metadata['commonsense_source_risks'] = [{'family': 'monetary_budget', 'support_count': 1400, 'regression_probability': .1}]
                record = RepairAttemptRecord(
                    step=step, query_uid=uid, repair_strategy=strategy,
                    before_personal_constraints=before, after_personal_constraints=after,
                    target_constraint_indices=[1] if before[0] is False else [], target_constraint_labels=[],
                    candidate_plan=plan, accepted_plan_after=plan if accepted else current_plan,
                    accepted=accepted, repair_phase='personal', editable_scope='slot' if index == 0 else 'day',
                    protected_constraint_indices=[2], repair_metadata=metadata,
                    total_tokens_delta=100, repair_time_seconds=1., model_calls=1, verification_count=1,
                    changed_slot_count=1, total_comparable_slots=1, changed_slot_rate=1.,
                    constraint_descriptors=[{'constraint_index': 1, 'hard_logic_py': 'result=(day_count(plan)==1)'},
                                            {'constraint_index': 2, 'hard_logic_py': 'result=(total_cost<=100)'}],
                    **categories).to_dict()
                verification = {'personal_constraints': after, 'commonsense_errors': [], 'translated_plan': plan}
                history.append({'step': step, 'accepted': accepted, 'verification': verification, 'repair_attempt': record})
                raw.append(record); local.append(record)
                if accepted:
                    before, current_plan = after, plan
            checkpoint = dict(query_uid=uid, repair_strategy=strategy, matrix_run_id=f'{uid}/trial',
                              initial_raw_plan=initial_plan, initial_verification=initial_v,
                              final_accepted_plan=current_plan, final_verification={'personal_constraints': before, 'commonsense_errors': []},
                              repair_history=history, repair_attempts=local, stop_reason='repair_budget_exhausted', execution_status='completed')
            cpdir = query / 'trials' if strategy == 'R4' else query
            cpdir.mkdir(exist_ok=True)
            (cpdir / f'{strategy}-fixture.json').write_text(json.dumps(checkpoint))
            (query / 'initial_state.json').write_text(json.dumps({'query_uid': uid, 'initial_plan_hash': 'same-input', 'state': {}}))
            if strategy == 'R4':
                selected = dict(checkpoint, matrix_run_id=f'{uid}/selected', selected_source='R4', selected_step=steps[-1] if steps else 0)
                (query / 'final_state.json').write_text(json.dumps(selected))
            refs[uid] = {'hard_logic_py': ['result=(day_count(plan)==1)', 'result=(total_cost<=100)']}
            reporting.append(dict(query_uid=uid, group='easy', repair_strategy=strategy,
                execution_status='completed', stop_reason='repair_budget_exhausted', initial_generation_failed=False,
                stopped_early_while_failing=False, pc_total=2, pc_passed_initial=1, pc_passed_final=2,
                pc_share_initial=.5, pc_share_final=1., pc_failed_final=0, pc_failed_kinds_final='',
                pc_total_excl_named=2, pc_passed_final_excl_named=2, cs_total=28, cs_passed_initial=25,
                cs_passed_final=27, cs_failed_checks_final='Timing', cs_evaluator_exception_initial=False,
                cs_evaluator_exception_final=False, cs_failed_raw_final=1, cs_total_raw_final=28,
                schema_initial=True, schema_final=True, all_pass_initial=False, all_pass_final=False,
                tokens_spent=100 * len(steps), tokens_spent_known=100 * len(steps), rounds_missing_tokens=0,
                repair_time_s=float(len(steps)), rounds=len(steps), error_reply_rounds=0, changed=len(steps), unchanged_cache=0,
                unchanged_other=0, dpc_per_changed=.5, dcs_per_changed=-.5))
        (folder / 'attempts.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in raw))
        bench = folder / 'benchmark_eval' / f'{strategy}-fixture'
        bench.mkdir(parents=True)
        (bench / 'evaluation_population.json').write_text(json.dumps({'queries': refs}))
        diagnostics = self.analysis / partition.lower() / strategy
        diagnostics.mkdir(parents=True)
        (diagnostics / 'provenance.json').write_text(json.dumps({
            'source_run_path': str(folder), 'manifest_run_id': manifest['run_id'],
            'analysis_timestamp': '2026-01-01T00:00:00+00:00',
            'source_checksums': {'attempts.jsonl': hashlib.sha256((folder / 'attempts.jsonl').read_bytes()).hexdigest()}}))
        pd.DataFrame({'query_uid': ids}).to_csv(diagnostics / 'query_level.csv', index=False)
        matrix = pd.DataFrame([{'scope': 'all', 'perspective': p, 'source_family': src,
            'destination_family': dst, 'support_count': n, 'regression_count': 0,
            'regression_rate': 0. if n else None}
            for p in ['candidate', 'accepted_trajectory'] for src, dst, n in [
                ('trip_specification', 'monetary_budget', 1700), ('monetary_budget', 'trip_specification', 0)]])
        matrix.to_csv(diagnostics / 'matrix_summary.csv', index=False)
        if strategy == 'R4':
            pd.DataFrame({'query_uid': ids, 'selected_source': ['R4'] * size,
                          'selected_step': [max(steps, default=0)] * size, 'considered_outcomes': [len(steps) + 1] * size}).to_csv(diagnostics / 'r4_selections.csv', index=False)
        self.rows[(partition, strategy)] = (reporting, refs)

    def write_reporting(self, strategies=None):
        notes = []
        for strategy in self.strategies if strategies is None else strategies:
            folder, manifest = self.manifests[('TEST', strategy)]
            rows, refs = self.rows[('TEST', strategy)]
            out = self.reporting / strategy
            out.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(rows).to_csv(out / 'per_query.csv', index=False)
            for name, function in [('table1_pc', team.table_pc), ('table2_cs', team.table_cs),
                                   ('table3_repair_process', team.table_process), ('table4_eval_exp', team.table_eval_exp)]:
                pd.DataFrame(function(rows)).to_csv(out / f'{name}.csv', index=False)
            pd.DataFrame(team.table_pc_kinds(rows, refs)).to_csv(out / 'table1b_pc_failure_by_kind.csv', index=False)
            notes.append((strategy, team.run_notes(strategy, folder, manifest, rows)))
        (self.reporting / 'README.md').write_text(team.readme(notes))


_default = None


def repository():
    global _default
    if _default is None:
        _default = Repository()
    return _default
