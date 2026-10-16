"""Offline tests only: temporary files, synthetic snapshots and owned children."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


counter = module('counter_probe')
summary = module('terminal_summary')


class FakeClock:
    def __init__(self):
        self.value = 0.

    def now(self):
        return self.value

    def sleep(self, duration):
        self.value += duration


class CounterTests(unittest.TestCase):
    def observe(self, snapshots):
        clock = FakeClock()
        iterator = iter(snapshots)
        return counter.observe(lambda: next(iterator), duration=2., interval=1.,
                               clock=clock.now, sleep=clock.sleep)

    def row(self, rx, identity=6):
        return {'identity': {'ifindex': identity, 'boot_id': 'synthetic'},
                'values': {'rx': rx, 'tx': 20, 'rx_errors': 0}}

    def test_growth_is_only_counter_evidence(self):
        r = self.observe([self.row(1000), self.row(2000), self.row(3000)])
        self.assertTrue(r['receiving'])
        self.assertEqual(r['deltas'], {'rx': 2000, 'tx': 0, 'rx_errors': 0})
        self.assertFalse(r['proves_joint_freshness_or_motion'])
        self.assertEqual(r['elapsed_s'], 2.)

    def test_no_growth_is_not_a_hardware_diagnosis(self):
        r = self.observe([self.row(1000)] * 3)
        self.assertIs(r['receiving'], False)
        self.assertEqual(r['reason'], 'no_growth_in_window')

    def test_identity_change_even_with_higher_counter_is_unknown(self):
        r = self.observe([self.row(1000), self.row(2000, 7)])
        self.assertIsNone(r['receiving'])
        self.assertIsNone(r['deltas'])
        self.assertEqual(r['reason'], 'identity_changed')

    def test_counter_reset_without_identity_change_is_unknown(self):
        r = self.observe([self.row(1000), self.row(12)])
        self.assertEqual(r['reason'], 'counter_decreased_or_reset')
        self.assertIsNone(r['receiving'])

    def test_missing_file_is_not_false(self):
        def missing():
            raise FileNotFoundError('synthetic missing counter')
        r = counter.observe(missing)
        self.assertEqual(r['status'], 'unknown')
        self.assertIsNone(r['receiving'])

    def test_setup_delay_does_not_replace_observation_window(self):
        clock = FakeClock()
        state = {'calls': 0}
        def read():
            if state['calls'] == 0:
                clock.value += 3.
            state['calls'] += 1
            return self.row(state['calls']*100)
        r = counter.observe(read, 2., 1., clock.now, clock.sleep)
        self.assertEqual(r['elapsed_s'], 5.)
        self.assertEqual(r['observed_s'], 2.)
        self.assertTrue(r['receiving'])

    def test_generic_files_and_fifo_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'counter').write_text('42\n')
            (root/'identity').write_text('fixture-A')
            self.assertEqual(counter.file_snapshot(root/'counter', root/'identity')['values']['rx'], 42)
            (root/'counter').write_text('-1')
            with self.assertRaises(ValueError):
                counter.unsigned(root/'counter')
            os.mkfifo(root/'fifo')
            with self.assertRaises(ValueError):
                counter.small_text(root/'fifo')


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value):
        path = self.root/name
        path.write_text(value)
        return path

    def test_error_in_middle_of_100001_lines_is_retained_in_small_summary(self):
        path = self.write('large.log', 'progress ok\n'*50000 + 'ERROR middle failure\n' + 'progress ok\n'*50000)
        r = summary.inspect_file(path, 'log')
        self.assertTrue(r['complete'])
        self.assertEqual(r['lines_in_snapshot'], 100001)
        errors = r['categories']['error_words']
        self.assertEqual(errors['matching_lines'], 1)
        self.assertEqual(errors['examples'][0]['line'], 50001)
        self.assertLess(len(json.dumps(r)), 2000)

    def test_long_line_error_not_hidden_by_excerpt_prefix(self):
        path = self.write('long.log', 'x'*100000 + ' ERROR late\n')
        r = summary.inspect_file(path, 'log')
        self.assertIn('ERROR', r['categories']['error_words']['examples'][0]['excerpt'])
        self.assertLessEqual(len(r['categories']['error_words']['examples'][0]['excerpt']), 160)

    def test_many_matches_counted_but_examples_bounded(self):
        path = self.write('errors.log', 'ERROR failed\n'*10000)
        r = summary.inspect_file(path, 'log', matches=['failed'], examples=2)
        self.assertEqual(r['categories']['error_words']['matching_lines'], 10000)
        self.assertEqual(len(r['categories']['error_words']['examples']), 2)
        self.assertEqual(r['categories']['match_1']['matching_lines'], 10000)

    def test_limit_cannot_report_whole_file_success(self):
        path = self.write('limited.log', 'ok\n'*1000 + 'ERROR beyond budget\n')
        r = summary.inspect_file(path, 'log', max_bytes=20)
        self.assertEqual(r['status'], 'partial')
        self.assertFalse(r['complete'])
        self.assertTrue(r['byte_limit_hit'])

    def test_selected_json_fields_not_full_arrays(self):
        path = self.write('data.json', json.dumps({'summary': {'count': 10000}, 'samples': list(range(10000))}))
        r = summary.inspect_file(path, 'json', fields=['/summary/count', '/samples', '/absent'])
        self.assertEqual(r['fields']['/summary/count']['value'], 10000)
        self.assertEqual(r['fields']['/samples'], {'found': True, 'type': 'list', 'length': 10000})
        self.assertFalse(r['fields']['/absent']['found'])
        self.assertLess(len(json.dumps(r)), 1500)

    def test_json_array_field_aggregation_missing_null_and_boolean(self):
        path = self.write('array.json', '[{"x":2,"ok":true},{"x":4,"ok":false},{"x":null},{}]')
        r = summary.inspect_file(path, 'json', fields=['/x', '/ok'])
        self.assertEqual(r['records'], 4)
        self.assertEqual((r['fields']['/x']['min'], r['fields']['/x']['max']), (2, 4))
        self.assertEqual(r['fields']['/x']['missing'], 1)
        self.assertEqual(r['fields']['/x']['null'], 1)
        self.assertEqual((r['fields']['/ok']['true'], r['fields']['/ok']['false']), (1, 1))

    def test_json_pointer_escapes_and_invalid_shape(self):
        self.assertEqual(summary.pointer({'a/b': {'~': [9]}}, '/a~1b/~0/0'), 9)
        with self.assertRaises(ValueError):
            summary.pointer({}, '/bad~escape')
        with self.assertRaises(KeyError):
            summary.pointer(None, '/x')

    def test_jsonl_invalid_records_not_silently_skipped(self):
        path = self.write('rows.jsonl', '{"gap":3}\ninvalid\n{"gap":5}\n')
        r = summary.inspect_file(path, 'jsonl', fields=['/gap'])
        self.assertEqual(r['status'], 'invalid_records')
        self.assertEqual((r['records'], r['invalid_records'], r['invalid_line_examples']), (2, 1, [2]))
        self.assertEqual(r['fields']['/gap']['max'], 5)

    def test_jsonl_cut_record_is_not_counted(self):
        path = self.write('cut.jsonl', '{"n":1}\n{"n":2222}\n')
        r = summary.inspect_file(path, 'jsonl', fields=['/n'], max_bytes=12)
        self.assertFalse(r['complete'])
        self.assertEqual(r['records'], 1)

    def test_malformed_json_and_nonfinite_json_are_errors(self):
        for name, value in [('bad', '{'), ('nan', '{"x":NaN}')]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                summary.inspect_file(self.write(name, value), 'json')

    def test_oversized_json_not_parsed_as_complete(self):
        r = summary.inspect_file(self.write('big.json', '[1,2,3,4]'), 'json', max_bytes=3)
        self.assertFalse(r['complete'])
        self.assertNotIn('root', r)

    def test_csv_aggregation(self):
        path = self.write('rows.csv', 'opening,note\n28,ok\n29,ok\n30,done\n')
        r = summary.inspect_file(path, 'csv', fields=['opening', 'missing'])
        self.assertEqual(r['records'], 3)
        self.assertEqual((r['fields']['opening']['min'], r['fields']['opening']['max']), (28., 30.))
        self.assertEqual(r['fields']['missing']['missing'], 3)

    def test_csv_duplicate_columns_or_extra_cells_rejected(self):
        for content in ['x,x\n1,2\n', 'x\n1,2\n']:
            with self.subTest(content=content), self.assertRaises(ValueError):
                summary.inspect_file(self.write('bad.csv', content), 'csv')

    def test_pipe_is_rejected_without_waiting_for_writer(self):
        fifo = self.root/'fifo'
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            summary.file_bytes(fifo, 1024)

    def test_emit_bounds_unicode_or_large_keys_without_false_success(self):
        out = io.StringIO()
        with redirect_stdout(out):
            summary.emit({'status': 'ok', 'unbounded_key_fixture': 'x'*100000})
        self.assertLess(len(out.getvalue().encode()), summary.OUTPUT_LIMIT)
        self.assertEqual(json.loads(out.getvalue())['status'], 'unknown')


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_child(self, code, **kwargs):
        return summary.run_command([sys.executable, '-c', code], self.root/'raw.log',
                                   timeout=kwargs.pop('timeout', 3.), **kwargs)

    def test_success_preserves_raw_and_does_not_treat_error_word_as_exit_failure(self):
        r = self.run_child('print("0 errors; 12 passed")', matches=['passed'])
        self.assertEqual(r['status'], 'completed')
        self.assertEqual(r['child_returncode'], 0)
        self.assertTrue(r['complete_output'])
        self.assertIn('12 passed', (self.root/'raw.log').read_text())

    def test_nonzero_real_return_code_preserved(self):
        r = self.run_child('print("ERROR synthetic"); raise SystemExit(7)')
        self.assertEqual(r['status'], 'child_failed')
        self.assertEqual(r['child_returncode'], 7)
        self.assertEqual(r['log_summary']['categories']['error_words']['matching_lines'], 1)

    def test_timeout_kills_term_ignoring_owned_child(self):
        r = self.run_child('import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(10)',
                           timeout=.2, grace=.05)
        self.assertEqual(r['status'], 'timeout')
        self.assertTrue(r['timed_out'])
        self.assertEqual(r['child_returncode'], -9)
        self.assertIn('SIGKILL', r['cleanup_signals'])
        self.assertLess(r['elapsed_s'], 3.)

    def test_output_flood_is_bounded_on_disk_and_not_success(self):
        r = self.run_child('import os; os.write(1,b"x"*1000000)', max_bytes=2048)
        self.assertEqual(r['status'], 'output_limit')
        self.assertEqual((self.root/'raw.log').stat().st_size, 2048)
        self.assertFalse(r['complete_output'])

    def test_existing_log_not_overwritten_and_child_not_started(self):
        log = self.root/'raw.log'
        log.write_text('original')
        sentinel = self.root/'must-not-exist'
        r = self.run_child(f'from pathlib import Path; Path({str(sentinel)!r}).touch()')
        self.assertEqual(r['status'], 'error')
        self.assertIsNone(r['child_returncode'])
        self.assertEqual(log.read_text(), 'original')
        self.assertFalse(sentinel.exists())

    def test_missing_program_not_no_data(self):
        r = summary.run_command(['/nonexistent/synthetic-program'], self.root/'raw.log', 1.)
        self.assertEqual(r['status'], 'error')
        self.assertIsNone(r['child_returncode'])

    def test_cli_high_output_only_returns_summary(self):
        result = subprocess.run([sys.executable, str(SCRIPTS/'terminal_summary.py'), 'run',
            '--log', str(self.root/'raw.log'), '--timeout', '5', '--', sys.executable, '-c',
            'print("ok\\n"*50000); print("ERROR in middle"); print("ok\\n"*50000)'],
            capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(len(result.stdout), summary.OUTPUT_LIMIT)
        r = json.loads(result.stdout)
        self.assertEqual(r['child_returncode'], 0)
        self.assertGreater(r['log_summary']['lines_in_snapshot'], 100000)
        self.assertEqual(r['log_summary']['categories']['error_words']['matching_lines'], 1)

    def test_cli_preserves_failure_and_handles_malformed_data(self):
        result = subprocess.run([sys.executable, str(SCRIPTS/'terminal_summary.py'), 'run',
            '--log', str(self.root/'fail.log'), '--timeout', '2', '--', sys.executable, '-c',
            'raise SystemExit(7)'], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 7)
        path = self.root/'bad.json'
        path.write_text('bad')
        result = subprocess.run([sys.executable, str(SCRIPTS/'terminal_summary.py'), 'data', str(path)],
                                capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['status'], 'error')

    def test_cli_counter_with_only_temporary_files(self):
        c, identity = self.root/'count', self.root/'identity'
        c.write_text('20'); identity.write_text('fixture')
        result = subprocess.run([sys.executable, str(SCRIPTS/'counter_probe.py'), '--counter-file', str(c),
            '--identity-file', str(identity), '--duration', '.02', '--interval', '.01'],
            capture_output=True, timeout=2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIs(json.loads(result.stdout)['receiving'], False)

    def test_cli_summary_overflow_is_unknown_and_nonzero(self):
        keys = [str(i)+'界'*150 for i in range(8)]
        path = self.root/'unicode.json'
        path.write_text(json.dumps({key: 'value' for key in keys}))
        argv = [sys.executable, str(SCRIPTS/'terminal_summary.py'), 'data', str(path)]
        for key in keys:
            argv.extend(['--field', '/'+key])
        result = subprocess.run(argv, capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 2)
        self.assertLess(len(result.stdout), summary.OUTPUT_LIMIT)
        self.assertEqual(json.loads(result.stdout)['status'], 'unknown')

    def test_cli_run_summary_overflow_preserves_child_status_without_traceback(self):
        argv = [sys.executable, str(SCRIPTS/'terminal_summary.py'), 'run',
                '--log', str(self.root/'unicode.log'), '--timeout', '3']
        for i in range(6):
            argv.extend(['--match', str(i)])
        argv.extend(['--', sys.executable, '-c',
                     'for i in range(6):\n for j in range(2): print(str(i)+"界"*200)'])
        result = subprocess.run(argv, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2, result.stderr)
        r = json.loads(result.stdout)
        self.assertEqual(r['status'], 'unknown')
        self.assertEqual(r['child_returncode'], 0)
        self.assertLess(len(result.stdout), summary.OUTPUT_LIMIT)
        self.assertNotIn(b'Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
