"""Integration tests with synthetic UI attestations; never contact a model or UI."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'control.py'


class LoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.project = self.base / 'project'
        self.project.mkdir()
        self.artifact = self.project / 'result.txt'
        self.artifact.write_text('initial result\n')
        self.root = self.base / 'supervisor'
        self.config = {
            'project': str(self.project), 'claude_title': 'Test calculation',
            'claude_session': 'test-session', 'goal': 'Verify the fixture result',
            'authorization': 'Synthetic user authorization used only by isolated tests',
            'success_criteria': [{'id': 'correct', 'description': 'Fixture result verified'}],
            'watch': ['**/*.txt'], 'max_rounds': 5, 'max_hours': 2,
            'max_no_progress_reviews': 3, 'lease_minutes': 10,
        }
        self.write('config.json', self.config)
        self.call('init', config=self.base / 'config.json')
        self.token = self.call('acquire')['lease']['token']

    def write(self, name, obj):
        path = self.base / name
        path.write_text(json.dumps(obj), encoding='utf-8')
        return path

    def state(self):
        return json.loads((self.root / 'state.json').read_text())

    def alter_state(self, modify):
        s = self.state()
        modify(s)
        (self.root / 'state.json').write_text(json.dumps(s))

    def command(self, action, **kwargs):
        cmd = [sys.executable, str(SCRIPT), '--root', str(self.root), action]
        for key, value in kwargs.items():
            cmd += ['--' + key.replace('_', '-'), str(value)]
        return cmd

    def call(self, action, ok=True, **kwargs):
        before = (self.root / 'state.json').read_bytes() if (self.root / 'state.json').exists() else None
        result = subprocess.run(self.command(action, **kwargs), capture_output=True, text=True,
                                cwd=self.base, timeout=10)
        if not ok:
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            if before is not None:
                self.assertEqual((self.root / 'state.json').read_bytes(), before)
            return result.stderr
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def observation(self, **updates):
        e = {'claude_title': self.config['claude_title'],
             'claude_session': self.config['claude_session'], 'observed_at': time.time(),
             'detail': 'Synthetic isolated fixture: idle final response, exact target',
             'idle': True, 'final_response_seen': True, 'composer_empty': True,
             'sent_marker_seen': True}
        if self.state()['round']:
            e['marker'] = self.state()['pending']['marker']
        e.update(updates)
        return self.write('observation.json', e)

    def complete(self, **updates):
        return self.call('completed', token=self.token, evidence=self.observation(**updates))

    def make_report(self, progress=True, met=False, issue=False, **updates):
        checkpoint = self.call('reconcile')
        r = {
            'round': self.state()['round'],
            'artifact_sha256': checkpoint['artifact_sha256'],
            'previous_review_sha256': checkpoint['previous_review_sha256'],
            'summary': 'Synthetic review of fixture result',
            'reconciliation': 'Compared fixture contents and complete prior registers',
            'progress': progress,
            'checks': [{'method': 'Read fixture result', 'result': self.artifact.read_text(),
                        'evidence': str(self.artifact)}],
            'criteria': {'correct': {'status': 'met' if met else 'not_met',
                                     'evidence': 'Fixture evaluation'}},
            'claims': [{'id': 'c1', 'statement': 'Fixture result under test',
                        'status': 'accepted', 'evidence': str(self.artifact)}],
            'issues': ([{'id': 'i1', 'statement': 'Fixture objection', 'status': 'open',
                         'blocking': True, 'evidence': str(self.artifact)}] if issue else []),
            'next_milestone': 'Repair fixture result or finish',
        }
        r.update(updates)
        return self.write('report.json', r)

    def review(self, **updates):
        return self.call('review', token=self.token, report=self.make_report(**updates))

    def prepare(self):
        s = self.call('status')
        path = self.base / 'prompt.txt'
        path.write_text(s['next_marker'] + '\nRepair the fixture and report actual checks.\n')
        return self.call('prepare', token=self.token, prompt=path)

    def ready(self):
        self.complete()
        self.review()
        return self.prepare()

    def dispatch(self):
        self.call('submitting', token=self.token, evidence=self.observation())
        return self.call('running', token=self.token, evidence=self.observation())

    def test_successful_two_milestone_loop(self):
        self.ready()
        self.dispatch()
        self.artifact.write_text('verified repaired result\n')
        self.complete()
        s = self.review(met=True)
        self.assertEqual(s['phase'], 'complete')
        self.assertFalse(s['enabled'])
        self.assertEqual(s['round'], 1)
        self.assertEqual(len([x for x in self.state()['history'] if x['action'] == 'review']), 2)

    def test_initial_empty_session_baseline(self):
        s = self.complete(final_response_seen=False, baseline_ready=True)
        self.assertEqual(s['phase'], 'reviewing')

    def test_baseline_exception_forbidden_after_first_prompt(self):
        self.ready()
        self.dispatch()
        self.call('completed', ok=False, token=self.token,
                  evidence=self.observation(final_response_seen=False, baseline_ready=True))

    def test_second_tick_cannot_acquire_live_lease(self):
        self.call('acquire', ok=False)

    def test_two_processes_race_for_one_lease(self):
        self.call('release', token=self.token)
        children = [subprocess.Popen(self.command('acquire'), stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True) for _ in range(2)]
        codes = []
        for child in children:
            child.communicate(timeout=10)
            codes.append(child.returncode)
        self.assertEqual(sorted(codes), [0, 2])

    def test_expired_lease_reconciles_but_never_replays_dispatch(self):
        self.ready()
        self.call('submitting', token=self.token, evidence=self.observation())
        self.alter_state(lambda s: s['lease'].update(until=time.time() - 1))
        self.token = self.call('acquire')['lease']['token']
        self.call('submitting', ok=False, token=self.token, evidence=self.observation())
        self.call('invalidate', ok=False, token=self.token, reason='Unknown receipt')
        s = self.call('running', token=self.token, evidence=self.observation())
        self.assertEqual(s['phase'], 'running')

    def test_unknown_send_is_blocked_and_resume_keeps_submitting(self):
        self.ready()
        self.call('submitting', token=self.token, evidence=self.observation())
        self.call('running', ok=False, token=self.token,
                  evidence=self.observation(sent_marker_seen=False))
        self.call('block', token=self.token, reason='Delivery unknown')
        s = self.call('resume', reason='Synthetic user resolved observation access')
        self.assertEqual(s['phase'], 'submitting')
        self.token = self.call('acquire')['lease']['token']
        self.call('prepare', ok=False, token=self.token, prompt=self.base / 'prompt.txt')

    def test_duplicate_receipt_and_duplicate_prepare_are_rejected(self):
        self.ready()
        self.call('prepare', ok=False, token=self.token, prompt=self.base / 'prompt.txt')
        self.dispatch()
        self.call('running', ok=False, token=self.token, evidence=self.observation())

    def test_stop_revokes_lease_and_repeated_stop_preserves_resume(self):
        self.ready()
        self.call('stop', reason='User pause')
        self.call('stop', reason='Still paused')
        self.call('submitting', ok=False, token=self.token, evidence=self.observation())
        self.assertEqual(self.call('resume', reason='User continue')['phase'], 'prepared')
        self.call('renew', ok=False, token=self.token)

    def test_completed_run_cannot_resume_or_be_reclassified_as_stopped(self):
        self.complete()
        self.review(met=True)
        self.assertEqual(self.call('stop', reason='User stop')['phase'], 'complete')
        self.call('resume', ok=False, reason='Try again')

    def test_active_claude_is_not_completed_or_dispatched(self):
        self.call('completed', ok=False, token=self.token, evidence=self.observation(idle=False))
        self.ready()
        self.call('submitting', ok=False, token=self.token, evidence=self.observation(idle=False))

    def test_human_draft_is_preserved(self):
        self.ready()
        self.call('submitting', ok=False, token=self.token,
                  evidence=self.observation(composer_empty=False))

    def test_wrong_target_marker_and_stale_observation(self):
        self.call('completed', ok=False, token=self.token,
                  evidence=self.observation(claude_session='another-session'))
        self.call('completed', ok=False, token=self.token,
                  evidence=self.observation(observed_at=time.time() - 360))
        self.ready()
        self.call('submitting', ok=False, token=self.token,
                  evidence=self.observation(marker='[WRONG-ROUND]'))

    def test_review_detects_changed_files_and_deletions(self):
        self.complete()
        path = self.make_report()
        self.artifact.write_text('changed after review checks')
        self.call('review', ok=False, token=self.token, report=path)
        self.review()
        self.artifact.unlink()
        checkpoint = self.call('reconcile')
        self.assertEqual(checkpoint['changed_since_review'], ['result.txt'])
        self.assertTrue(checkpoint['stale_review'])

    def test_drift_before_prepare_and_send_requires_fresh_review(self):
        self.complete()
        self.review()
        self.artifact.write_text('new evidence')
        prompt = self.base / 'prompt.txt'
        prompt.write_text(self.call('status')['next_marker'] + '\nDo work\n')
        self.call('prepare', ok=False, token=self.token, prompt=prompt)
        self.call('invalidate', token=self.token, reason='Evidence changed')
        self.review()
        self.prepare()
        self.artifact.write_text('another change')
        self.call('submitting', ok=False, token=self.token, evidence=self.observation())
        s = self.call('invalidate', token=self.token, reason='Evidence changed again')
        self.assertEqual(s['round'], 0)
        self.assertEqual(s['phase'], 'reviewing')
        self.assertNotIn('pending', s)
        self.review()
        self.assertEqual(self.prepare()['round'], 1)

    def test_prompt_text_is_frozen_despite_source_edits(self):
        s = self.ready()
        expected = (self.base / 'prompt.txt').read_text()
        (self.base / 'prompt.txt').write_text('mutated source prompt')
        result = subprocess.run(self.command('prompt'), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.stdout, expected)
        self.assertEqual(self.state()['pending']['sha256'], s['pending']['sha256'])

    def test_stale_predecessor_hash_and_dropped_claims_or_issues(self):
        self.complete()
        self.review(issue=True)
        self.prepare()
        self.dispatch()
        self.complete()
        self.call('review', ok=False, token=self.token,
                  report=self.make_report(issue=True, previous_review_sha256=None))
        self.call('review', ok=False, token=self.token,
                  report=self.make_report(issue=True, claims=[]))
        self.call('review', ok=False, token=self.token, report=self.make_report(issues=[]))

    def test_blocking_objection_prevents_success(self):
        self.complete()
        s = self.review(met=True, issue=True)
        self.assertEqual(s['phase'], 'reviewed')
        self.assertTrue(s['enabled'])

    def test_claim_meaning_cannot_drift_under_same_id(self):
        self.ready()
        self.dispatch()
        self.complete()
        self.call('review', ok=False, token=self.token, report=self.make_report(claims=[
            {'id': 'c1', 'statement': 'An easier replacement claim',
             'status': 'accepted', 'evidence': str(self.artifact)}]))

    def test_heartbeat_contains_resolved_paths_and_does_not_schedule(self):
        before = (self.root / 'state.json').read_bytes()
        result = subprocess.run(self.command('heartbeat'), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(SCRIPT), result.stdout)
        self.assertIn(str(self.root / 'CONTROL.md'), result.stdout)
        self.assertEqual((self.root / 'state.json').read_bytes(), before)

    def test_missing_success_criterion_rejected(self):
        self.complete()
        self.call('review', ok=False, token=self.token, report=self.make_report(criteria={}))

    def test_round_limit_stops_without_false_success(self):
        self.alter_state(lambda s: s['config'].update(max_rounds=1))
        self.ready()
        self.dispatch()
        self.complete()
        s = self.review()
        self.assertEqual(s['phase'], 'blocked')
        self.assertIn('Round limit', s['reason'])
        self.call('resume', ok=False, reason='Cannot reset budget')

    def test_success_is_allowed_at_last_round(self):
        self.alter_state(lambda s: s['config'].update(max_rounds=1))
        self.ready()
        self.dispatch()
        self.complete()
        self.assertEqual(self.review(met=True)['phase'], 'complete')

    def test_no_progress_limit(self):
        self.alter_state(lambda s: s['config'].update(max_no_progress_reviews=1))
        self.complete()
        s = self.review(progress=False)
        self.assertEqual(s['phase'], 'blocked')
        self.assertIn('No-progress', s['reason'])

    def test_wall_clock_limit_before_send(self):
        self.ready()
        self.alter_state(lambda s: s.update(deadline=time.time() - 1))
        s = self.call('submitting', token=self.token, evidence=self.observation())
        self.assertFalse(s['enabled'])
        self.assertEqual(s['phase'], 'blocked')

    def test_watched_symlink_cannot_read_outside_project(self):
        outside = self.base / 'outside.txt'
        outside.write_text('outside data')
        (self.project / 'linked.txt').symlink_to(outside)
        self.call('reconcile', ok=False)

    def test_lock_and_state_are_stable_on_read_only_commands(self):
        before = (self.root / 'state.json').read_bytes()
        self.call('status')
        self.call('reconcile')
        self.assertEqual((self.root / 'state.json').read_bytes(), before)

    def test_reinitialization_is_rejected(self):
        self.call('init', ok=False, config=self.base / 'config.json')


if __name__ == '__main__':
    unittest.main()
