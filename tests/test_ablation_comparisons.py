"""Offline comparison contracts; synthetic artifacts and original helper parity."""
import copy
from dataclasses import replace
import io
import json
from pathlib import Path
import subprocess
import shutil
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import pandas as pd

from dashboard.tests.fixtures import Repository
from scripts.result_analysis.ablation_comparisons import COMPARISONS
from scripts.result_analysis.ablation_comparisons.inputs import load_evidence
from scripts.result_analysis.ablation_comparisons.comparison_validity import assess
from scripts.result_analysis.ablation_comparisons.metrics import mechanism
from scripts.result_analysis.ablation_comparisons.build_ablation_comparisons import build_comparison, main


class AblationTests(unittest.TestCase):
    def setUp(self):
        self.repo=Repository(size=3,steps=(1,2,3))
        self.addCleanup(self.repo.close)
        self.evidence={}
        for strategy in ('R0','R1','R2','R3','R4'):
            path,_=self.repo.manifests[('TEST',strategy)]
            e=load_evidence(strategy,path,self.repo.reporting,self.repo.analysis/'test',self.repo.root)
            self.assertFalse(e.error,e.error)
            self.evidence[strategy]=e
        self.output=self.repo.root/'comparisons'

    def args(self):
        values=['--repository-root',str(self.repo.root),'--test-reporting-dir',str(self.repo.reporting),
                '--analysis-dir',str(self.repo.analysis/'test'),'--output-dir',str(self.output)]
        for key in ('R0','R2','R3','R4'):
            values.extend(['--'+key.lower(),str(self.evidence[key].path)])
        return values

    def controls(self,left,right,matrix=False):
        for e in (left,right):
            e.manifest=copy.deepcopy(e.manifest)
            for key,value in {'scheduler_version':'schedule-v1','repair_implementation_hash':'shared-code',
                              'verifier_config':{'v':1},'evaluator_config':{'v':1},
                              'benchmark_population_hash':'benchmark','seed':42,'language':'en',
                              'oracle_translation':True,'max_steps':6,'model_identifier':'model',
                              'sampling_settings':{'temperature':0}}.items():
                e.manifest[key]=value
            e.manifest.setdefault('compatibility',{})['query_hashes']={uid:'query-'+uid for uid in e.population}
            e.initial_hashes={uid:'initial-'+uid for uid in e.population}
        if matrix:
            right.raw.extra['_comparison_matrix_audit']={'train_only_guidance_verified':True}
            for row in left.raw.attempts:
                row['repair_metadata']={}
            for cp in [*left.raw.checkpoints.values(),*left.raw.extra.get('trials',[])]:
                for entry in cp.get('repair_history',[])[1:]:
                    entry.get('repair_attempt',{})['repair_metadata']={}
            for e,flag in ((left,False),(right,True)):
                e.manifest['matrix_guidance_enabled']=flag
                snapshot={k:copy.deepcopy(e.manifest[k]) for k in ('scheduler_version','repair_implementation_hash',
                          'verifier_config','evaluator_config','benchmark_population_hash','seed','language','oracle_translation',
                          'max_steps','model_identifier','sampling_settings','matrix_guidance_enabled')}
                snapshot['other_settings']={}
                e.manifest.update(ablation_settings=snapshot,ablation_settings_complete=True)

    def test_cli_reproducibility_missing_runs_and_tidy_outputs(self):
        with patch('scripts.result_analysis.build_test_result_tables.score_plans',side_effect=AssertionError('No scoring')), \
             patch('scripts.result_analysis.build_test_result_tables.build_queries',side_effect=AssertionError('No rescoring')):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(self.args()),0)
            first={str(p.relative_to(self.output)):p.read_bytes() for p in self.output.rglob('*.csv')}
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(self.args()),0)
        self.assertEqual(first,{str(p.relative_to(self.output)):p.read_bytes() for p in self.output.rglob('*.csv')})
        matrix=json.loads((self.output/'r4_matrix_ablation/validity.json').read_text())
        self.assertEqual(matrix['reason'],'Required no-matrix R4 TEST run is not currently available.')
        self.assertFalse(matrix['allow_deltas'])
        self.assertFalse(json.loads((self.output/'r1_vs_r3/validity.json').read_text())['available'])
        tidy=pd.read_csv(self.output/'comparison_metrics.csv')
        self.assertEqual(set(tidy.comparison_id),set(COMPARISONS))

    def test_cli_has_no_streamlit_dependency(self):
        command=[str(Path('.venv/bin/python').resolve()),'-c',
                 "import sys; from scripts.result_analysis.ablation_comparisons.build_ablation_comparisons import main; assert 'streamlit' not in sys.modules; raise SystemExit(main(['--help']))"]
        result=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('--r4-no-matrix-reporting-dir',result.stdout)

    def test_delta_and_existing_test_table_values(self):
        left,right=self.evidence['R0'],self.evidence['R2']
        right.tables['table1_pc']=right.tables['table1_pc'].copy()
        right.tables['table1_pc'].loc[right.tables['table1_pc'].metric=='Avg % PC passed per query - final plan','All']='87.5'
        summary,_,_=build_comparison('r0_vs_r2',left,right)
        row=summary[(summary.difficulty=='All') & (summary.metric_id=='pc_final')].iloc[0]
        self.assertEqual(row.right_value,87.5)
        self.assertEqual(row.delta,row.right_value-row.left_value)
        self.assertEqual(row.left_value,float(left.tables['table1_pc'].set_index('metric').loc['Avg % PC passed per query - final plan','All']))
        self.assertTrue(summary.loc[summary.metric_id=='cs_new','left_value'].isna().all())

    def test_incompatible_population_blocks_default_and_explicit_subset(self):
        left,right=self.evidence['R0'],self.evidence['R2']
        right.population=right.population[:-1];right.q=right.q.iloc[:-1].copy()
        full,_,validity=build_comparison('r0_vs_r2',left,right)
        self.assertEqual(validity['classification'],'Incompatible / blocked')
        self.assertTrue(full.delta.isna().all())
        subset,_,validity=build_comparison('r0_vs_r2',left,right,intersection=True)
        self.assertEqual(validity['cohort_label'],'Matched-query subset')
        self.assertEqual(validity['n_left'],3);self.assertEqual(validity['n_matched'],2)
        self.assertEqual(len(validity['excluded_left']),1)
        self.assertFalse(subset[subset.difficulty=='All'].delta.isna().all())
        self.assertTrue(subset[subset.difficulty=='All'].n_left.eq(2).all())

    def test_difficulty_uid_mapping_not_just_counts(self):
        left,right=self.evidence['R0'],self.evidence['R2']
        right.q.loc[0,'group']='human'
        result=assess(left,right,'r0_vs_r2')
        self.assertFalse(result['allow_deltas'])
        self.assertEqual(result['classification'],'Incompatible / blocked')

    def test_validity_downgrades_unknown_or_different_controls(self):
        left,right=self.evidence['R0'],self.evidence['R2']
        self.assertEqual(assess(left,right,'r0_vs_r2')['classification'],'Descriptive comparison only')
        self.controls(left,right)
        self.assertEqual(assess(left,right,'r0_vs_r2')['classification'],'Matched strategy comparison')
        right.manifest['sampling_settings']={'temperature':1}
        self.assertEqual(assess(left,right,'r0_vs_r2')['classification'],'Descriptive comparison only')
        self.assertTrue(assess(left,right,'r0_vs_r2')['allow_deltas'])

    def test_matrix_ablation_requires_explicit_controls_and_pairing(self):
        right=self.evidence['R4'];left=copy.deepcopy(right)
        left.key='R4-no-matrix';left.path=left.path.with_name('final_test-r4-no-matrix')
        self.controls(left,right,matrix=True)
        result=assess(left,right,'r4_matrix_ablation')
        self.assertEqual(result['classification'],'Controlled ablation')
        right.manifest['ablation_settings']['other_settings']={'guard':'different'}
        self.assertEqual(assess(left,right,'r4_matrix_ablation')['classification'],'Descriptive comparison only')
        right.manifest['ablation_settings']['other_settings']={}
        left.manifest.pop('matrix_guidance_enabled')
        self.assertNotEqual(assess(left,right,'r4_matrix_ablation')['classification'],'Controlled ablation')
        left.path=right.path
        self.assertFalse(assess(left,right,'r4_matrix_ablation')['allow_deltas'])

    def test_r2_candidate_harm_rejected_and_preserved_are_distinct(self):
        e=self.evidence['R2']
        a=e.attempts
        # Fixture rejected final proposal regresses protected PC2, initial candidates do not.
        a.loc[:,'protected_regression_count']=0
        a.loc[0,['protected_regression_count','accepted','rejected']]=[1,True,False]
        a.loc[1,['protected_regression_count','accepted','rejected']]=[1,False,True]
        rows={r['metric']:r for r in mechanism(e,e.population,'All')}
        self.assertEqual(rows['Harmful candidates generated']['value'],2)
        self.assertEqual(rows['Harmful candidates rejected']['value'],1)
        self.assertEqual(rows['Harmful candidates accepted']['value'],1)
        self.assertEqual(rows['Harmful-candidate rejection rate']['value'],50)
        self.assertNotIn('Harmful candidates rejected',{r['metric'] for r in mechanism(self.evidence['R0'],e.population,'All')})

    def test_protected_definition_and_verified_rollback_on_actual_events(self):
        from scripts import analyze_repair_strategies as analysis
        e=self.evidence['R2']
        rows={r['metric']:r for r in mechanism(e,e.population,'All')}
        self.assertEqual(rows['Harmful candidates generated']['value'],3)
        self.assertEqual(rows['Harmful candidates rejected']['value'],3)
        self.assertEqual(rows['Harmful candidates accepted']['value'],0)
        self.assertEqual(rows['Queries where harmful rollback preserved prior accepted plan']['value'],3)
        self.assertGreater(e.attempts.newly_violated_count.sum(),0)
        self.assertEqual(e.attempts.accepted_newly_violated_count.sum(),0)
        e.raw.attempts[0]['protected_constraint_indices']=[]
        e.attempts,e.query_analysis,_=analysis.build_tables(e.raw)
        rows={r['metric']:r for r in mechanism(e,e.population,'All')}
        self.assertEqual(rows['Harmful candidates generated']['value'],2)

    def test_difficulty_sources_and_missing_reporting_never_use_train(self):
        left,right=self.evidence['R3'],self.evidence['R4']
        summary,mechanisms,validity=build_comparison('r3_vs_r4',left,right)
        self.assertEqual(validity['classification'],'Descriptive comparison only')
        self.assertTrue(summary[summary.difficulty=='Human'].delta.isna().all())
        self.assertEqual(set(mechanisms.run),{'R3','R4'})
        self.assertEqual(summary.comparison_type.unique().tolist(),['strategy comparison'])

    def test_localization_and_scheduled_scope_diagnostics_reuse_hooks(self):
        self.evidence['R1'].attempts.at[0,'editable_slot']=[0,1]
        self.evidence['R1'].attempts.at[1,'failure_reason']='no_localizable_slot'
        r1={r['metric']:r for r in mechanism(self.evidence['R1'],self.evidence['R1'].population,'All')}
        self.assertIn('Localization attempts',r1)
        self.assertEqual(r1['Successful localization (slot selected)']['value'],1)
        self.assertEqual(r1['Localization failures']['value'],1)
        self.assertEqual(r1['Localization reason: no_localizable_slot']['value'],1)
        r3={r['metric']:r for r in mechanism(self.evidence['R3'],self.evidence['R3'].population,'All')}
        self.assertEqual(r3['Queries reaching slot']['value'],3)
        self.assertEqual(r3['slot → day transitions']['value'],3)
        self.assertNotIn('Harmful candidates rejected',r3)
        self.assertNotIn('Guidance: supported',r3)

    def test_matrix_guidance_fields_are_actual_logged_counts(self):
        e=self.evidence['R4']
        rows={r['metric']:r for r in mechanism(e,e.population,'All')}
        self.assertEqual(rows['Guidance: supported']['value'],len(e.raw.attempts))
        self.assertEqual(rows['Supported relationship occurrences']['value'],len(e.raw.attempts))
        self.assertEqual(rows['Mean support per supported relationship occurrence']['value'],1400)

    def test_cli_pairs_two_r4_runs_with_separate_reporting(self):
        right=self.evidence['R4']
        clone=self.repo.root/'experiments/final_test-r4-no-matrix'
        shutil.copytree(right.path,clone)
        m=json.loads((clone/'run_manifest.json').read_text());m.update(run_id='R4-no-matrix-run',matrix_guidance_enabled=False)
        (clone/'run_manifest.json').write_text(json.dumps(m))
        right_manifest=json.loads((right.path/'run_manifest.json').read_text());right_manifest['matrix_guidance_enabled']=True
        (right.path/'run_manifest.json').write_text(json.dumps(right_manifest))
        records=[json.loads(line) for line in (clone/'attempts.jsonl').read_text().splitlines()]
        for row in records:
            row['repair_metadata']={}
        (clone/'attempts.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in records))
        for path in (clone/'queries').rglob('*.json'):
            cp=json.loads(path.read_text())
            if 'repair_history' in cp and isinstance(cp['repair_history'],list):
                for entry in cp['repair_history'][1:]:
                    entry.get('repair_attempt',{})['repair_metadata']={}
                path.write_text(json.dumps(cp))
        alternate=self.repo.root/'no-matrix-reporting'
        shutil.copytree(self.repo.reporting,alternate)
        notes=(alternate/'README.md').read_text().replace(str(right.path),str(clone)).replace(right.manifest['run_id'],m['run_id'])
        (alternate/'README.md').write_text(notes)
        with redirect_stdout(io.StringIO()):
            main(self.args()+['--r4-no-matrix',str(clone),'--r4-no-matrix-reporting-dir',str(alternate),'--comparison','r4_matrix_ablation'])
        summary=pd.read_csv(self.output/'r4_matrix_ablation/summary.csv')
        self.assertTrue(summary.left_run.eq(m['run_id']).all())
        self.assertTrue(summary.right_run.eq(right.manifest['run_id']).all())
        self.assertTrue(summary.left_strategy.eq('R4-no-matrix').all())
        self.assertFalse(summary[summary.difficulty=='All'].delta.isna().all())
        self.assertFalse(json.loads((self.output/'r4_matrix_ablation/metadata.json').read_text())['causal_language_allowed'])
        mechanism_table=pd.read_csv(self.output/'r4_matrix_ablation/mechanism.csv')
        no_matrix=mechanism_table[(mechanism_table.side=='Left') & (mechanism_table.metric=='Guidance: supported')]
        self.assertTrue(no_matrix.value.isna().all())

    def test_matrix_fields_not_manufactured_without_logging(self):
        e=self.evidence['R4'];e.key='R4-no-matrix'
        for r in e.raw.attempts:
            r['repair_metadata']={}
        values={r['metric']:r for r in mechanism(e,e.population,'All')}
        self.assertIsNone(values['Guidance: supported']['value'])
        self.assertIsNone(values['Supported relationship occurrences']['value'])

    def test_wrong_partition_and_reporting_binding(self):
        path,_=self.repo.manifests[('TRAIN','R2')]
        e=load_evidence('R2',path,self.repo.reporting,self.repo.analysis,self.repo.root)
        self.assertTrue(e.error)
        self.assertFalse(assess(e,self.evidence['R0'],'r0_vs_r2')['allow_deltas'])
        qpath=self.repo.reporting/'R2/per_query.csv'
        q=pd.read_csv(qpath);q.loc[0,'repair_strategy']='R0';q.to_csv(qpath,index=False)
        e=load_evidence('R2',self.evidence['R2'].path,self.repo.reporting,self.repo.analysis,self.repo.root)
        self.assertTrue(e.q.empty)
        self.assertTrue(any('reporting unavailable' in n for n in e.notes))


if __name__=='__main__':
    unittest.main()
