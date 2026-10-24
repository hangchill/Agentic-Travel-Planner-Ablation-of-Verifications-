"""phase_outcomes.csv commonsense columns cover every commonsense round of a query."""
import unittest

from scripts.build_repair_summary import commonsense_step_metrics, _commonsense_report


def entry(step, phase, accepted, personal, errors, newly=(), scope='slot', targets=None):
    verification = dict(personal_constraints=personal, commonsense_errors=list(errors),
                        passed=all(p is True for p in personal) and not errors)
    attempt = dict(step=step, repair_phase=phase, accepted=accepted, editable_scope=scope,
                   after_personal_constraints=personal, newly_violated=list(newly),
                   target_commonsense_errors=list(targets or []))
    return dict(step=step, verification=verification, repair_attempt=attempt)


class CommonsenseRoundMetricsTests(unittest.TestCase):
    def test_no_commonsense_round(self):
        history = [dict(verification=dict(personal_constraints=[True], commonsense_errors=[]))]
        self.assertTrue(all(v is None for v in commonsense_step_metrics(history).values()))

    def test_several_rounds_first_before_vs_last_after(self):
        history = [
            dict(verification=dict(personal_constraints=[True, True], commonsense_errors=['a', 'b'])),
            entry(1, 'commonsense', True, [True, False], ['b'], newly=[2], targets=['a', 'b']),
            entry(2, 'personal', True, [True, True], ['b', 'c']),
            entry(3, 'commonsense', False, [True, True], ['x', 'y', 'z'], scope='day', targets=['b', 'c']),
            entry(4, 'commonsense', True, [True, True], ['c'], scope='day', targets=['b', 'c']),
        ]
        m = commonsense_step_metrics(history)
        self.assertEqual(m['cs_attempts'], 3)
        self.assertEqual(m['cs_accepted'], 2)
        self.assertEqual((m['cs_step'], m['cs_scope']), (1, 'slot'))
        self.assertEqual(m['cs_errors_before'], 2)          # ['a', 'b'] targeted by round 1
        self.assertEqual(m['cs_errors_after'], 1)           # accepted plan after round 4: ['c']
        self.assertEqual((m['cs_errors_fixed'], m['cs_errors_new']), (2, 1))
        self.assertFalse(m['cs_passed_after'])
        self.assertEqual(m['cs_broke_personal'], 1)
        self.assertTrue(m['cs_recovered'])                   # constraint 2 passes again at the end

    def test_rejected_last_round_keeps_accepted_plan(self):
        history = [
            dict(verification=dict(personal_constraints=[True], commonsense_errors=['a'])),
            entry(1, 'commonsense', True, [True], [], targets=['a']),
        ]
        history[1]['verification']['passed'] = True
        m = commonsense_step_metrics(history)
        self.assertEqual((m['cs_errors_after'], m['cs_passed_after']), (0, True))
        rejected = history[:1] + [entry(1, 'commonsense', False, [False], ['a', 'b'], newly=[1], targets=['a'])]
        m = commonsense_step_metrics(rejected)
        self.assertEqual(m['cs_errors_after'], 1)            # the initial plan is still the accepted one
        self.assertEqual(m['cs_broke_personal'], 1)
        self.assertIsNone(m['cs_recovered'])                 # nothing accepted broke a constraint

    def test_report_counts_queries_and_rounds(self):
        rows = [dict(cs_step=1, cs_attempts=3, cs_errors_before=2, cs_errors_fixed=2, cs_errors_new=1,
                     cs_passed_after=False, cs_broke_personal=1, cs_recovered=True),
                dict(cs_step=6, cs_attempts=1, cs_errors_before=1, cs_errors_fixed=1, cs_errors_new=0,
                     cs_passed_after=True, cs_broke_personal=0, cs_recovered=None),
                dict(cs_step=None)]
        report = _commonsense_report(rows)
        self.assertEqual((report['cs_steps'], report['cs_attempts']), (2, 4))
        self.assertEqual((report['cs_steps_1_2'], report['cs_steps_5_6']), (1, 1))
        self.assertEqual(report['cs_fix_rate'], 1.0)


if __name__ == '__main__':
    unittest.main()
