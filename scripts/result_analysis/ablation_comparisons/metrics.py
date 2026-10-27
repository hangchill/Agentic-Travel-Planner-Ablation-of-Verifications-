"""Metric catalog and mechanism adapters over existing authoritative helpers."""
import math
import re

import pandas as pd

from scripts import analyze_repair_strategies as analysis
from scripts.result_analysis import build_test_result_tables as team

# id, group, display label, file, exact source row(s), unit, direction, denominator
CATALOG = [
 ('pc_final','PC','Avg % PC passed: final','table1_pc',('Avg % PC passed per query - final plan',),'%','higher','Queries; mean per-query share'),
 ('pc_change','PC','Avg % PC passed: change','table1_pc',('Avg % PC passed per query - change (percentage points)',),'percentage points','higher','Queries; mean per-query share change'),
 ('pc_zero','PC','Final plans with 0 failed PC','table1_pc',('Final plans with 0 failed PC',),'queries','higher','Queries'),
 ('pc_all_rate','PC','All-PC-pass rate','table1_pc',('Final plans with 0 failed PC',),'%','higher','Selected query N; saved zero-failure count / N'),
 ('pc_decreased','PC','Queries with PC pass rate decreased','table1_pc',('Queries where % PC passed decreased',),'queries','lower','Queries; saved count'),
 ('pc_new','PC','Avg new PC violations (candidate loop)','attempts',('newly_violated_count',),'PCs/proposal','lower','Observed proposals with shared PC transition evidence; includes rejected candidates'),
 ('pc_net','PC','Avg net PC change (candidate loop)','attempts',('net_repair_gain',),'PCs/proposal','higher','Observed proposals; shared candidate fixed minus regressed count'),
 ('pc_new_accepted','PC','Avg new PC violations (accepted loop)','attempts',('accepted_newly_violated_count',),'PCs/proposal','lower','Observed proposals; rejected proposals contribute no accepted regression'),
 ('cs_final','CS','Avg % CS passed: final','table2_cs',('Avg % CS checks passed per query - final plan',),'%','higher','Queries; mean corrected standard-check share'),
 ('cs_change','CS','Avg % CS passed: change','table2_cs',('Avg % CS checks passed per query - change (percentage points)',),'percentage points','higher','Queries; mean corrected standard-check share change'),
 ('cs_zero','CS','Final plans with 0 failed CS','table2_cs',('Final plans with 0 failed CS checks',),'queries','higher','Queries; saved zero-failure count'),
 ('cs_85','CS','>85% CS success rate','threshold',(),'%','higher','Selected query N; original strict threshold table count / N'),
 ('cs_new','CS','Avg new CS violations','unavailable',(),'checks/proposal','lower','Unavailable: no standard-check transition table in existing reporting'),
 ('cs_net','CS','Avg net CS check change','unavailable',(),'checks/proposal','higher','Unavailable: loop messages are not benchmark check identities'),
 ('attempts','Process','Avg repair attempts/query','queries',('rounds',),'attempts/query','descriptive','Selected queries; saved per_query.rounds mean'),
 ('tokens','Process','Avg tokens/query (complete data)','table3_repair_process',('[per query] Avg tokens spent per query (queries with complete token data)',),'tokens','lower','Queries with complete summed total_tokens_delta; source rounding retained'),
 ('token_coverage','Process','Token completeness','table3_repair_process',('[per query] Queries with token data',),'%','descriptive','Selected query N; saved complete-token query count / N'),
 ('token_lower','Process','Avg tokens/query lower bound','table3_repair_process',('[per query] Avg tokens spent per query - all queries, failed requests counted as 0 (lower bound)','[per query] Avg tokens spent per query - known values only, all queries (lower bound)'),'tokens','lower','All queries; missing token deltas add 0 only as a lower bound'),
 ('time','Process','Avg repair time/query','table3_repair_process',('[per query] Avg repair time per query (s)',),'seconds','lower','Queries with complete repair-time sums; source rounding retained'),
 ('changed','Process','Plan-change rate','table3_repair_process',('[round-wise] % of rounds where the plan changed',),'%','descriptive','Observed repair rounds; candidate translated plan vs preceding accepted plan'),
 ('call_failure','Process','Model-call failure rate (error reply)','table3_repair_process',('[round-wise] % of rounds where the model call failed (error text instead of a plan; includes cached repeats of a failed reply)',),'%','lower','Observed rounds; source raw_response error-text marker, including cached failures'),
 ('cache','Process','Cache-unchanged rate','table3_repair_process',('[round-wise] % of rounds unchanged - answered from cache (exact repeat of an earlier request)',),'%','descriptive','Observed rounds; unchanged candidate and llm_cache_hits > 0'),
 ('noop','Process','Explicit no-progress rate','attempts',('unchanged_confirmed',),'%','descriptive','Observed proposals; decision_reason == no_progress_unchanged'),
 ('cs_micro','Evaluation','Commonsense micro','table4_eval_exp',('Commonsense micro (%) - share of all (plan, check) pairs passed',),'%','higher','Pooled raw evaluator cells including exception column; unchanged Table 4 caveat'),
 ('cs_macro','Evaluation','Commonsense macro','table4_eval_exp',('Commonsense macro (%) - plans passing every CS check',),'%','higher','Queries; raw CS all-pass plans / N'),
 ('logical_micro','Evaluation','Logical micro','table4_eval_exp',('Logical micro (%) - share of all personal constraints passed (pooled)',),'%','higher','Pooled reference PCs; passed / total'),
 ('logical_macro','Evaluation','Logical macro','table4_eval_exp',('Logical macro (%) - plans passing every personal constraint',),'%','higher','Queries; all reference PCs pass / N'),
 ('allpass','Evaluation','All-pass ratio','table4_eval_exp',('All-pass ratio (%) - schema + CS + PC all passed',),'%','higher','Queries; schema AND CS AND PC pass / N'),
]


def number(value):
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):
        return None


def subset(evidence,uids,difficulty):
    if evidence is None:
        return pd.DataFrame(),pd.DataFrame()
    ids=set(uids)
    q=evidence.q[evidence.q.query_uid.isin(ids)].copy() if not evidence.q.empty else pd.DataFrame({'query_uid':sorted(ids),'group':[None]*len(ids)})
    if difficulty!='All':
        ids=set(q.loc[q.group==difficulty.lower(),'query_uid']) if not q.empty else set()
        q=q[q.query_uid.isin(ids)] if not q.empty else q
    a=evidence.attempts
    return q, a[a.query_uid.isin(ids)].copy() if 'query_uid' in a else pd.DataFrame()


def source_tables(evidence,uids):
    if evidence is None or evidence.q.empty:
        return {}
    if set(uids)==set(evidence.q.query_uid):
        return evidence.tables
    q=evidence.q[evidence.q.query_uid.isin(uids)]
    rows=q.astype(object).where(pd.notna(q),None).to_dict('records')
    for r in rows:
        for key in ('pc_failed_kinds_final','cs_failed_checks_final'):
            r[key]=r.get(key) or ''
    result={}
    for name,helper in [('table1_pc',team.table_pc),('table2_cs',team.table_cs),('table3_repair_process',team.table_process),('table4_eval_exp',team.table_eval_exp)]:
        try:
            result[name]=pd.DataFrame(helper(rows))
        except (KeyError,TypeError,ZeroDivisionError):
            # Missing per-query columns never get reconstructed from aggregates.
            result[name]=pd.DataFrame()
    return result


def common_value(spec,q,a,tables,difficulty):
    identifier,_,_,source,fields,unit,_,_=spec
    if q.empty:
        return None,0
    if source=='unavailable':
        return None,0
    if source=='attempts':
        if fields[0] not in a:
            return None,0
        values=pd.to_numeric(a[fields[0]],errors='coerce').dropna()
        return (float(values.mean())*(100 if unit=='%' else 1) if len(values) else None),len(values)
    if source=='queries':
        values=pd.to_numeric(q.get(fields[0],pd.Series(dtype=float)),errors='coerce').dropna()
        return (float(values.mean()) if len(values) else None),len(values)
    if source=='threshold':
        table=tables.get('table2_cs',pd.DataFrame())
        if (table.empty or 'cs_total' not in q or q.cs_total.nunique()!=1 or team.CS_PASS_THRESHOLD!=.85):
            return None,0
        matches=table[table.metric.str.contains(r'^Final plans with at most .*\(more than 85%',regex=True)]
        if len(matches)!=1:
            return None,0
        total=re.search(r'of the (\d+) checks passed',matches.iloc[0].metric)
        if not total or int(total[1]) != q.cs_total.iloc[0]:
            return None,0
        value=number(matches.iloc[0].get(difficulty))
        return (100*value/len(q) if value is not None else None),len(q)
    table=tables.get(source,pd.DataFrame())
    if table.empty or 'metric' not in table or difficulty not in table:
        return None,0
    for field in fields:
        found=table[table.metric==field]
        if len(found)==1:
            value=number(found.iloc[0][difficulty])
            if identifier in ('pc_all_rate','token_coverage'):
                value=100*value/len(q) if value is not None else None
            n=int(q.tokens_spent.notna().sum()) if identifier=='tokens' and 'tokens_spent' in q else int(q.repair_time_s.notna().sum()) if identifier=='time' and 'repair_time_s' in q else len(q)
            return value,n
    return None,0


def mechanism(evidence,uids,difficulty):
    """Tidy diagnostics reuse analyzer hooks and shared accepted-state events."""
    if evidence is None or evidence.error:
        return []
    q,a=subset(evidence,uids,difficulty)
    if a.empty:
        return []
    rows=[]
    def emit(metric,value,n,source,direction='descriptive',unit='count',denominator=None):
        rows.append({'run':evidence.key,'difficulty':difficulty,'metric':metric,'value':number(value),
                     'evidence_n':n,'source':source,'denominator': denominator or ('observed proposals' if unit!='queries' else 'selected queries'),
                     'unit':unit,'direction':direction})
    def count(metric,values,source,unit='count'):
        values=pd.Series(values).dropna()
        emit(metric,int(values.sum()) if len(values) else None,len(values),source,unit=unit)
    count('Candidate PC-regression proposals',a.newly_violated_count>0,'analyze_repair_strategies.build_tables / compute_attempt_metrics')
    count('Accepted PC-regression proposals',a.accepted_newly_violated_count>0,'shared accepted_newly_violated_count')
    count('Proposals',pd.Series([True]*len(a)),'validated persisted attempts')
    if evidence.strategy=='R2':
        hook=analysis.hook_r2(a)[0]['protection_and_rollback']
        known=hook[hook.protected_regression_count.notna()]
        harmful=known[known.protected_regression_count>0]
        emit('Protection evidence proposals',len(known),len(a),'hook_r2.protected_regression_count')
        emit('Harmful candidates generated',len(harmful) if len(known) else None,len(known),'hook_r2: protected PC True→False')
        rejected=harmful[harmful.rejected.eq(True)]
        emit('Harmful candidates rejected',len(rejected) if len(known) else None,len(known),'hook_r2.harmful_candidate_blocked')
        emit('Harmful candidates accepted',int(harmful.accepted.eq(True).sum()) if len(known) else None,len(known),'hook_r2: harmful candidate AND accepted')
        emit('Harmful-candidate rejection rate',100*len(rejected)/len(harmful) if len(harmful) else None,len(harmful),'hook_r2; rejected harmful / harmful',unit='%',denominator='harmful candidates with known acceptance')
        emit('Queries with >=1 harmful candidate',harmful.query_uid.nunique() if len(known) else None,len(q),'hook_r2',unit='queries')
        retained=set();known_equality=0
        for uid,cp in evidence.raw.checkpoints.items():
            if uid not in set(q.query_uid):
                continue
            current=cp.get('initial_raw_plan')
            harmful_steps=set(rejected.loc[rejected.query_uid==uid,'step'])
            for entry in cp.get('repair_history',[])[1:]:
                after=(entry.get('repair_attempt') or {}).get('accepted_plan_after')
                if entry.get('step') in harmful_steps and entry.get('accepted') is False and current is not None and after is not None:
                    known_equality+=1
                    if current==after:
                        retained.add(uid)
                if entry.get('accepted') is True:
                    current=after
        emit('Queries where harmful rollback preserved prior accepted plan',len(retained) if known_equality or (len(known)==len(a) and not len(harmful)) else None,known_equality,'checkpoint raw accepted-plan equality; harmful rejected proposals only',unit='queries',denominator='harmful rejected rounds with both raw plans; value counts distinct queries')
    if evidence.strategy=='R1':
        h=analysis.hook_r1(a)[0]['localization']
        eligible=h[h.localization_eligible]
        emit('Localization attempts',len(eligible),len(h),'hook_r1.localization_eligible')
        count('Successful localization (slot selected)',eligible.slot_selected,'hook_r1: recorded two-element editable_slot; not repair success')
        count('Localization failures',eligible.recorded_localization_failure,'hook_r1: failure_reason contains localiz')
        for reason,count_value in eligible.failure_reason.dropna().value_counts().items():
            emit('Localization reason: '+str(reason),count_value,len(eligible),'hook_r1.failure_reason')
        measured=pd.to_numeric(a.changed_slot_count,errors='coerce').dropna()
        emit('Mean measured changed slots',measured.mean(),len(measured),'shared changed_slot_count; measured proposals only',unit='slots/proposal',denominator='proposals with measured changed_slot_count')
    if evidence.strategy=='R3':
        hooks,_=analysis.hook_r3(a)
        h=hooks['scope_transitions']
        for scope in ('slot','day','plan'):
            part=h[h.editable_scope==scope]
            emit('Queries reaching '+scope,part.query_uid.nunique(),len(q),'hook_r3.scope_transitions',unit='queries')
            emit('Attempts at '+scope,len(part),len(a),'hook_r3.scope_outcomes')
            count('Successful target repairs at '+scope,a.loc[a.editable_scope==scope,'targeted_fixed_count']>0,'shared targeted_fixed_count > 0; candidate diagnostic')
            count('Accepted successful target repairs at '+scope,a.loc[a.editable_scope==scope,'targeted_fixed_count'].gt(0) & a.loc[a.editable_scope==scope,'accepted'].eq(True),'shared targeted_fixed_count > 0 AND accepted')
        for source,target in [('slot','day'),('day','plan')]:
            part=h[h.editable_scope==source]
            count(source+' → '+target+' transitions',part.next_scope==target,'hook_r3.next_scope; observed same-trial next proposal')
        for scope,count_value in evidence.query_analysis[evidence.query_analysis.query_uid.isin(q.query_uid)].scope_sequence.fillna('').map(
                lambda s:max([x for x in str(s).split(',') if x in analysis.SCOPE_LEVEL],key=analysis.SCOPE_LEVEL.get,default='unknown')).value_counts().items():
            emit('Highest scope reached: '+scope,count_value,len(q),'analyzer query_level.scope_sequence',unit='queries')
    if evidence.strategy=='R4':
        for status in ('supported','unsupported','no logged relationship'):
            flags=[]
            for raw in evidence.raw.attempts:
                if raw['query_uid'] not in set(q.query_uid):
                    continue
                meta=raw.get('repair_metadata') or {}
                if evidence.key=='R4-no-matrix' and not any(k in meta for k in ('risk_target_ranking','commonsense_source_risks')):
                    continue  # Do not manufacture guidance fields for a no-matrix run.
                cells=list(meta.get('commonsense_source_risks') or [])
                for ranked in meta.get('risk_target_ranking') or []:
                    cells.extend(ranked.get('destination_risks') or [])
                actual='supported' if any((c.get('support_count') or 0)>0 for c in cells) else 'unsupported' if cells else 'no logged relationship'
                flags.append(actual==status)
            count('Guidance: '+status,flags,'logged risk_target_ranking.destination_risks / commonsense_source_risks')
        raw=[r for r in evidence.raw.attempts if r['query_uid'] in set(q.query_uid)]
        count('Structural guard failures',[bool((r.get('repair_metadata') or {}).get('proposal_rejected_reason')) if 'proposal_rejected_reason' in (r.get('repair_metadata') or {}) else None for r in raw],'logged proposal_rejected_reason')
        supports=[c.get('support_count') for r in raw for c in guidance_cells(r.get('repair_metadata') or {}) if (c.get('support_count') or 0)>0]
        has_fields=any(any(k in (r.get('repair_metadata') or {}) for k in ('risk_target_ranking','commonsense_source_risks')) for r in raw)
        emit('Supported relationship occurrences',len(supports) if has_fields else None,len(raw) if has_fields else 0,'logged cells; duplicates retained as supplied guidance')
        all_cells=[c for r in raw for c in guidance_cells(r.get('repair_metadata') or {})]
        unsupported=sum(c.get('support_count') is None or c.get('support_count')==0 for c in all_cells)
        emit('Unsupported relationship occurrences',unsupported if has_fields else None,len(all_cells),'repair_analysis_r4: missing/zero support cells; occurrences, not queries',denominator='logged relationship occurrences, including repeats')
        emit('Mean support per supported relationship occurrence',sum(supports)/len(supports) if supports else None,len(supports),'logged support_count; opportunities, not independent queries',unit='support',denominator='supported relationship occurrences, including repeated guidance')
        selections=evidence.raw.extra.get('_comparison_tables',{}).get('r4_selections',pd.DataFrame())
        selections=selections.to_dict('records') if isinstance(selections,pd.DataFrame) else selections
        selections=[r for r in selections if r.get('query_uid') in set(q.query_uid)]
        for label,initial in [('Initial outcomes selected',True),('Repaired outcomes selected',False)]:
            known=[r for r in selections if r.get('selected_source') is not None]
            emit(label,sum((r['selected_source']=='initial')==initial for r in known) if known else None,len(known),'R4 final_state.json post-hoc selection; separate from benchmark',unit='queries')
        considered=[number(r.get('considered_outcomes',r.get('candidate_outcomes_considered'))) for r in selections]
        considered=[v for v in considered if v is not None]
        emit('Candidate outcomes considered/query',sum(considered)/len(considered) if considered else None,len(considered),'R4 selection artifact considered_outcomes; includes initial when recorded',unit='outcomes/query',denominator='queries with validated recorded outcome pools')
    return rows


def guidance_cells(meta):
    cells=list(meta.get('commonsense_source_risks') or [])
    for ranked in meta.get('risk_target_ranking') or []:
        cells.extend(ranked.get('destination_risks') or [])
    return cells
