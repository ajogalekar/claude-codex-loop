"""Windows-specific controller checks (msvcrt lock, junctions, drive globs, PowerShell heartbeat)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'control.py'
sys.path.insert(0, str(SCRIPT.parent))
import control  # noqa: E402


@unittest.skipUnless(os.name == 'nt', 'Windows-only checks')
class WindowsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()  # long path; TEMP may be 8.3 short form
        self.project = self.base / 'project'
        self.project.mkdir()
        (self.project / 'result.txt').write_text('ok\n')
        self.root = self.base / 'supervisor'
        self.config = {
            'project': str(self.project), 'claude_title': 't', 'claude_session': 's',
            'goal': 'g', 'authorization': 'test only',
            'success_criteria': [{'id': 'c', 'description': 'd'}],
            'watch': ['**/*.txt'], 'max_rounds': 1, 'max_hours': 1,
            'max_no_progress_reviews': 1, 'lease_minutes': 10}

    def run_cli(self, *args, config=None):
        cfg = self.base / 'config.json'
        cfg.write_text(json.dumps(config or self.config), encoding='utf-8')
        cmd = [sys.executable, str(SCRIPT), '--root', str(self.root), *args]
        if args[0] == 'init':
            cmd += ['--config', str(cfg)]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    def junction(self, link, target):
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
                       check=True, capture_output=True)

    def test_lock_blocks_second_process_until_released(self):
        self.assertEqual(self.run_cli('init').returncode, 0)
        with control.ledger_lock(self.root / 'ledger.lock'):
            child = subprocess.Popen([sys.executable, str(SCRIPT), '--root', str(self.root), 'status'],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            time.sleep(1.5)
            self.assertIsNone(child.poll(), 'second process ran while lock was held')
        out, err = child.communicate(timeout=10)
        self.assertEqual(child.returncode, 0, err)

    def test_lock_released_for_sequential_holders(self):
        lock = self.base / 'x.lock'
        for _ in range(3):  # release must actually unlock, else 2nd entry spins forever
            with control.ledger_lock(lock):
                pass

    def test_junction_detected_where_is_symlink_is_not(self):
        outside = self.base / 'outside'
        outside.mkdir()
        self.junction(self.project / 'linked', outside)
        if sys.version_info < (3, 12):  # the gap the patch closes
            self.assertFalse((self.project / 'linked').is_symlink())
        self.assertTrue(control.is_link(self.project / 'linked'))
        self.assertFalse(control.is_link(self.project))

    def test_junction_dir_outside_project_not_hashed(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'secret.txt').write_text('outside data')
        self.junction(self.project / 'linked', outside)
        self.assertEqual(self.run_cli('init').returncode, 0)
        result = self.run_cli('reconcile')
        self.assertEqual(result.returncode, 0, result.stderr)
        changed = json.loads(result.stdout)['changed_since_review']
        self.assertEqual(changed, ['result.txt'])

    def test_drive_absolute_watch_glob_rejected(self):
        for bad in ('C:/elsewhere/*.txt', 'C:\\elsewhere\\*.txt', '\\elsewhere\\*.txt'):
            config = dict(self.config, watch=[bad])
            result = self.run_cli('init', config=config)
            self.assertEqual(result.returncode, 2, bad)
            self.assertIn('watch must contain relative', result.stderr)

    def test_backslash_watch_glob_normalized_and_matches(self):
        (self.project / 'sub').mkdir()
        (self.project / 'sub' / 'a.txt').write_text('x')
        self.assertEqual(self.run_cli('init', config=dict(self.config, watch=['sub\\*.txt'])).returncode, 0)
        state = json.loads((self.root / 'state.json').read_text(encoding='utf-8'))
        self.assertEqual(state['config']['watch'], ['sub/*.txt'])
        changed = json.loads(self.run_cli('reconcile').stdout)['changed_since_review']
        self.assertEqual(changed, ['sub/a.txt'])

    def test_heartbeat_command_is_powershell_invocation(self):
        self.assertEqual(self.run_cli('init').returncode, 0)
        out = self.run_cli('heartbeat').stdout
        self.assertIn(f"& '{sys.executable}' '{SCRIPT}' '--root' '{self.root}' 'status'", out)


if __name__ == '__main__':
    unittest.main()
