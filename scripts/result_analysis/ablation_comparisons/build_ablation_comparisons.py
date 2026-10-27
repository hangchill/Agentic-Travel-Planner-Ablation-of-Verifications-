"""Build reproducible offline pairwise outputs. Never executes experiments/scoring."""
import argparse
from datetime import datetime, timezone
import json
import shutil
from pathlib import Path
import sys

import pandas as pd

from scripts.analyze_repair_strategies import save_csv, write_json
from . import COMPARISONS, DIFFICULTIES
from .inputs import digest, load_evidence
from .comparison_validity import assess
from .metrics import CATALOG, common_value, mechanism, source_tables, subset

SUMMARY_COLUMNS = ['comparison_id','comparison_type','cohort_label','difficulty','left_run','right_run',
                   'left_strategy','right_strategy','metric_group','metric_id','metric','left_value','right_value','delta',
                   'unit','direction','n_left','n_right','n_matched','n_values_left','n_values_right','validity_class',
                   'source','denominator','cohort_compatible','unavailable_reason']
MECHANISM_COLUMNS = ['comparison_id','side','run','difficulty','metric','value','evidence_n','source','denominator','unit','direction']


def interpretation(identifier,validity):
    if identifier=='r3_vs_r4':
        return 'Strategy comparison — not a matrix ablation'
    if identifier=='r0_vs_r4_matrix':
        return validity['classification']
    return COMPARISONS[identifier][3]


def build_comparison(identifier,left,right,intersection=False):
    validity=assess(left,right,identifier,intersection)
    definition=COMPARISONS[identifier]
    uids=validity['uids']
    tables=[source_tables(e,uids) for e in (left,right)]
    rows=[];mechanisms=[];cohorts={}
    for difficulty in DIFFICULTIES:
        parts=[subset(e,uids,difficulty) for e in (left,right)]
        qs=[p[0] for p in parts]
        ids=[set(q.query_uid) if 'query_uid' in q else set() for q in qs]
        compatible=bool(ids[0]) and ids[0]==ids[1] and validity['allow_deltas']
        cohorts[difficulty]={'compatible':bool(compatible),'n_left':len(ids[0]),'n_right':len(ids[1]),
                             'n_matched':len(ids[0]&ids[1])}
        for spec in CATALOG:
            values=[common_value(spec,q,a,table,difficulty) for (q,a),table in zip(parts,tables)]
            lv,rv=values[0][0],values[1][0]
            delta=rv-lv if compatible and lv is not None and rv is not None else None
            row=dict(zip(SUMMARY_COLUMNS,[None]*len(SUMMARY_COLUMNS)))
            row.update(comparison_id=identifier,comparison_type=definition[3],cohort_label=validity['cohort_label'],
                       difficulty=difficulty,left_run=left.manifest.get('run_id') if left else None,
                       right_run=right.manifest.get('run_id') if right else None,left_strategy=definition[1],right_strategy=definition[2],
                       metric_group=spec[1],metric_id=spec[0],metric=spec[2],left_value=lv,right_value=rv,delta=delta,
                       unit=spec[5],direction=spec[6],n_left=len(ids[0]),n_right=len(ids[1]),n_matched=len(ids[0]&ids[1]),
                       n_values_left=values[0][1],n_values_right=values[1][1],validity_class=validity['classification'],
                       source=(spec[3]+'.csv: '+' OR '.join(spec[4])) if spec[3].startswith('table') else spec[3]+': '+' OR '.join(spec[4]),
                       denominator=spec[7],cohort_compatible=bool(compatible),
                       unavailable_reason=('Selected difficulty populations are unavailable or incompatible.' if not compatible else
                                           spec[7] if spec[3]=='unavailable' else 'Missing required source cells/evidence on one or both sides.' if lv is None or rv is None else ''))
            rows.append(row)
        # No incompatible-cohort mechanism counts are presented as paired evidence.
        if compatible:
            for side,e in [('Left',left),('Right',right)]:
                for row in mechanism(e,uids,difficulty,matrix_comparison=identifier=='r0_vs_r4_matrix'):
                    mechanisms.append(dict(row,comparison_id=identifier,side=side))
    validity['difficulty_cohorts']=cohorts
    return pd.DataFrame(rows,columns=SUMMARY_COLUMNS),pd.DataFrame(mechanisms,columns=MECHANISM_COLUMNS),validity


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('r0','r1','r2','r3','r4'):
        p.add_argument('--'+name,type=Path)
    p.add_argument('--test-reporting-dir',type=Path,default=Path('test_result_analysis'))
    p.add_argument('--analysis-dir',type=Path,default=Path('results/analysis/repair_strategies/test'))
    p.add_argument('--output-dir',type=Path,default=Path('results/analysis/ablation_comparisons'))
    p.add_argument('--repository-root',type=Path,default=Path.cwd(),help='Base for relative paths recorded in generated provenance.')
    p.add_argument('--comparison',choices=list(COMPARISONS),action='append',help='Build only named comparison(s); default all four.')
    p.add_argument('--matched-query-subset',action='store_true',help='Explicit intersection analysis, labelled Matched-query subset; original/excluded UIDs retained.')
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    repository=args.repository_root.resolve();output=args.output_dir.resolve()
    # Output-only locations protect all supplied inputs from accidental overwrite.
    input_roots=[p.resolve() for p in [args.test_reporting_dir,args.analysis_dir,
                 *[getattr(args,k) for k in ('r0','r1','r2','r3','r4')]] if p is not None]
    if any(output==p or output.is_relative_to(p) or p.is_relative_to(output) for p in input_roots):
        raise ValueError('Output directory must be separate from all input directories')
    selected=args.comparison or list(COMPARISONS)
    keys={key for identifier in selected for key in COMPARISONS[identifier][1:3]}
    evidence={}
    for key in sorted(keys):
        path=getattr(args,key.lower().replace('-','_'))
        evidence[key]=load_evidence(key,path,args.test_reporting_dir,args.analysis_dir,repository)
    output.mkdir(parents=True,exist_ok=True)
    tidy=[];all_mechanisms=[];index={}
    timestamp=datetime.now(timezone.utc).isoformat()
    code_files=[*Path(__file__).parent.glob('*.py'),Path(__file__).parents[2]/'analyze_repair_strategies.py',
                Path(__file__).parents[1]/'build_test_result_tables.py',repository/'chinatravel/evaluation/repair_metrics.py',
                repository/'scripts/repair_analysis_r4.py',
                *[repository/'chinatravel/agent/nesy_verifier/repair_strategies'/name for name in ('r0.py','r3.py','r4.py','base.py')],
                repository/'chinatravel/agent/nesy_verifier/shared_repair_loop.py',repository/'r4/select_outcomes.py']
    code={str(p.resolve()):digest(p) for p in code_files if p.is_file()}
    for identifier in selected:
        definition=COMPARISONS[identifier];left,right=[evidence[k] for k in definition[1:3]]
        summary,mechanisms,validity=build_comparison(identifier,left,right,args.matched_query_subset)
        folder=output/identifier;folder.mkdir(parents=True,exist_ok=True)
        save_csv(folder/'summary.csv',summary);save_csv(folder/'mechanism.csv',mechanisms)
        write_json(folder/'validity.json',validity)
        metadata={'schema_version':1,'comparison_id':identifier,'title':definition[0],'question':definition[4],
                  'comparison_type':definition[3],'delta_convention':'Right - Left',
                  'interpretation':interpretation(identifier,validity),
                  'causal_language_allowed':validity['classification']=='Controlled ablation','generated_at':timestamp,
                  'command':['python','-m','scripts.result_analysis.ablation_comparisons.build_ablation_comparisons',*(argv if argv is not None else sys.argv[1:])],
                  'source_checksums':{p:h for e in (left,right) if e for p,h in e.inputs.items()},
                  'analysis_code_checksums':code,
                  'notes':{e.key:e.notes for e in (left,right) if e},
                  'source_runs':{e.key:{'path':str(e.path),'run_id':e.manifest.get('run_id'),'error':e.error} for e in (left,right) if e}}
        metadata['output_checksums']={p.name:digest(p) for p in (folder/'summary.csv',folder/'mechanism.csv',folder/'validity.json')}
        write_json(folder/'metadata.json',metadata)
        tidy.append(summary);all_mechanisms.append(mechanisms)
        index[identifier]={'classification':validity['classification'],'available':validity['available'],'reason':validity['reason']}
        print(identifier+': '+validity['classification']+' — '+validity['reason'])
    save_csv(output/'comparison_metrics.csv',pd.concat(tidy,ignore_index=True))
    save_csv(output/'mechanism_metrics.csv',pd.concat(all_mechanisms,ignore_index=True))
    write_json(output/'index.json',index)
    (output/'README.md').write_text('# Ablations & Comparisons\n\nGenerated offline; never edit numerical cells by hand.\n\n'+
        '\n'.join(f'- `{key}`: {value["classification"]}. {value["reason"]}' for key,value in index.items())+
        '\n\nDelta = Right - Left. A positive delta is not automatically better.\n'+
        'Only Controlled ablation licenses a causal interpretation. Other comparisons are descriptive.\n'+
        'Each folder contains summary.csv, mechanism.csv, validity.json, metadata.json.\n',encoding='utf-8')
    # Retire only the known obsolete generated comparison; never touch run inputs.
    retired=output/'r4_matrix_ablation'
    if retired.is_dir() and not retired.is_symlink():
        shutil.rmtree(retired)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
