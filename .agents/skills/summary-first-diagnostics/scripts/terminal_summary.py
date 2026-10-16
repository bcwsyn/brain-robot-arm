#!/usr/bin/env python3
"""Bounded local log/data inspection and command capture; compact JSON only.

Standard library only. Commands are NOT sandboxed or made read-only: callers
must already have authority. Never use this wrapper to authorize robot actions.
"""
import argparse
import csv
import io
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

OUTPUT_LIMIT = 8192
TEXT_LIMIT = 160
DEFAULT_BYTES = 16 * 1024 * 1024
ERROR = re.compile(r'\b(?:errors?|fatal|exception|traceback|fail(?:ed|ures?)?)\b', re.I)
WARNING = re.compile(r'\bwarn(?:ing)?\b', re.I)


def brief(value):
    if value is None or isinstance(value, (bool, int)):
        return {'type': type(value).__name__, 'value': value}
    if isinstance(value, float):
        return {'type': 'float', 'value': value if math.isfinite(value) else None,
                'finite': math.isfinite(value)}
    if isinstance(value, str):
        return {'type': 'str', 'length': len(value), 'preview': value[:TEXT_LIMIT],
                'preview_cut': len(value) > TEXT_LIMIT}
    if isinstance(value, dict):
        return {'type': 'dict', 'length': len(value),
                'keys_preview': [str(k)[:80] for k in list(value)[:12]]}
    return {'type': type(value).__name__, 'length': len(value)}


def emit(result):
    try:
        encoded = json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
        if len(encoded.encode()) > OUTPUT_LIMIT:
            result = {'status': 'unknown', 'reason': 'summary_output_limit',
                      'complete': False, 'child_returncode': result.get('child_returncode'),
                      'timed_out': result.get('timed_out', False),
                      'output_limit_hit': result.get('output_limit_hit', False),
                      'log': str(result.get('log'))[:200]}
            encoded = json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
    except (ValueError, TypeError, OverflowError):
        result = {'status': 'unknown', 'reason': 'summary_encoding_failed', 'complete': False}
        encoded = json.dumps(result, separators=(',', ':'))
    print(encoded)
    return result


def file_bytes(path, max_bytes):
    """Reject FIFOs/devices, bound allocation, and expose incomplete snapshots."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        first = os.fstat(stream.fileno())
        if not stat.S_ISREG(first.st_mode):
            raise ValueError('Expected a regular file, not a device/pipe')
        data = stream.read(max_bytes + 1)
        last = os.fstat(stream.fileno())
    changed = (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns) != (
        last.st_dev, last.st_ino, last.st_size, last.st_mtime_ns)
    limited = len(data) > max_bytes
    return data[:max_bytes], {'initial_size_bytes': first.st_size,
        'read_bytes': min(len(data), max_bytes), 'byte_limit_hit': limited,
        'source_changed_during_read': changed, 'complete': not limited and not changed}


def log_stats(data, matches=(), examples=2):
    buckets = {name: {'matching_lines': 0, 'examples': []}
               for name in ['error_words', 'warning_words', *[f'match_{i+1}' for i in range(len(matches))]]}
    lines = data.decode('utf-8', errors='replace').splitlines()
    for number, line in enumerate(lines, 1):
        hits = {'error_words': ERROR.search(line), 'warning_words': WARNING.search(line)}
        hits.update({f'match_{i+1}': line.find(pattern) for i, pattern in enumerate(matches)})
        for name, hit in hits.items():
            if hit is None or (isinstance(hit, int) and hit < 0):
                continue
            bucket = buckets[name]
            bucket['matching_lines'] += 1
            if len(bucket['examples']) < examples:
                position = hit if isinstance(hit, int) else hit.start()
                begin = max(0, position - 60)
                bucket['examples'].append({'line': number, 'excerpt': line[begin:begin+TEXT_LIMIT],
                    'excerpt_cut': begin > 0 or len(line) > begin + TEXT_LIMIT})
    return {'lines_in_snapshot': len(lines), 'counts_are_matching_lines_not_failures': True,
            'matches': {f'match_{i+1}': pattern for i, pattern in enumerate(matches)}, 'categories': buckets}


def pointer(value, field):
    if not field.startswith('/'):
        raise ValueError('JSON fields must be JSON pointers, e.g. /summary/saved_frames')
    for piece in field[1:].split('/'):
        if re.search(r'~(?![01])', piece):
            raise ValueError('Invalid JSON pointer escape')
        key = piece.replace('~1', '/').replace('~0', '~')
        if isinstance(value, dict):
            value = value[key]
        elif isinstance(value, list) and key.isascii() and key.isdecimal():
            value = value[int(key)]
        else:
            raise KeyError(key)
    return value


def aggregate(rows, fields, is_csv=False):
    statistics = {field: {'present': 0, 'missing': 0, 'null': 0,
        'numeric_count': 0, 'min': None, 'max': None, 'true': 0, 'false': 0,
        'types': {}} for field in fields}
    count = 0
    for row in rows:
        count += 1
        for field, summary in statistics.items():
            try:
                value = row[field] if is_csv else pointer(row, field)
            except (KeyError, IndexError):
                summary['missing'] += 1
                continue
            summary['present'] += 1
            name = type(value).__name__
            summary['types'][name] = summary['types'].get(name, 0) + 1
            if value is None:
                summary['null'] += 1
            elif isinstance(value, bool):
                summary['true' if value else 'false'] += 1
            else:
                number = value
                if is_csv:
                    try:
                        number = float(value)
                    except (ValueError, TypeError):
                        number = None
                if isinstance(number, (float, int)):
                    try:
                        finite = math.isfinite(number)
                    except OverflowError:
                        finite = False
                    if finite:
                        summary['numeric_count'] += 1
                        summary['min'] = number if summary['min'] is None else min(summary['min'], number)
                        summary['max'] = number if summary['max'] is None else max(summary['max'], number)
    return count, statistics


def json_load(text):
    def invalid_constant(_):
        raise ValueError('Non-finite JSON constant')
    return json.loads(text, parse_constant=invalid_constant)


def inspect_file(path, kind, fields=(), matches=(), examples=2, max_bytes=DEFAULT_BYTES):
    data, meta = file_bytes(path, max_bytes)
    result = {'status': 'ok' if meta['complete'] else 'partial', 'format': kind, **meta}
    if kind == 'log':
        result.update(log_stats(data, matches, examples))
    elif kind == 'json':
        if not meta['complete']:
            result['reason'] = 'JSON_not_parsed_from_incomplete_snapshot'
            return result
        document = json_load(data)
        result['root'] = brief(document)
        if isinstance(document, list):
            result['records'], result['fields'] = aggregate(document, fields)
        else:
            selected = {}
            for field in fields:
                try:
                    selected[field] = {'found': True, **brief(pointer(document, field))}
                except (KeyError, IndexError):
                    selected[field] = {'found': False}
            result['fields'] = selected
    elif kind == 'jsonl':
        invalid = {'count': 0, 'examples': []}
        # Do not interpret a byte-cut final line as a complete record.
        usable = data.rsplit(b'\n', 1)[0] if meta['byte_limit_hit'] and not data.endswith(b'\n') else data
        def records():
            for number, line in enumerate(io.BytesIO(usable), 1):
                if not line.strip():
                    continue
                try:
                    yield json_load(line)
                except (ValueError, UnicodeError):
                    invalid['count'] += 1
                    if len(invalid['examples']) < 3:
                        invalid['examples'].append(number)
        result['records'], result['fields'] = aggregate(records(), fields)
        result['invalid_records'] = invalid['count']
        result['invalid_line_examples'] = invalid['examples']
        if invalid['count']:
            result['status'] = 'invalid_records'
    elif kind == 'csv':
        if not meta['complete']:
            result['reason'] = 'CSV_not_parsed_from_incomplete_snapshot'
            return result
        reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')), strict=True)
        result['columns_preview'] = [str(v)[:80] for v in (reader.fieldnames or [])[:12]]
        if reader.fieldnames and len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('Duplicate CSV columns')
        def records():
            for row in reader:
                if None in row:
                    raise ValueError('CSV row contains undeclared extra columns')
                yield row
        result['records'], result['fields'] = aggregate(records(), fields, True)
    return result


def run_command(argv, log, timeout, grace=.5, max_bytes=DEFAULT_BYTES, matches=(), examples=2):
    """Capture one explicitly authorized finite command; no implicit shell."""
    start = time.monotonic()
    result = {'status': 'unknown', 'log': str(log), 'timed_out': False,
              'output_limit_hit': False, 'child_returncode': None, 'cleanup_signals': [],
              'captured_bytes': 0, 'elapsed_s': 0.}
    process = None
    selector = selectors.DefaultSelector()
    try:
        # Exclusive creation refuses an existing artifact before spawning.
        with Path(log).open('xb') as stream:
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       start_new_session=True, shell=False)
            selector.register(process.stdout, selectors.EVENT_READ)
            reason, deadline = None, start + timeout
            while selector.get_map() or process.poll() is None:
                now = time.monotonic()
                if reason is None and now >= deadline:
                    reason = 'timeout'
                    result['timed_out'] = True
                if reason is not None:
                    break
                for key, _ in selector.select(min(.05, max(0., deadline-now))):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    remaining = max_bytes - result['captured_bytes']
                    kept = chunk[:remaining]
                    stream.write(kept)
                    result['captured_bytes'] += len(kept)
                    if len(chunk) > remaining:
                        result['output_limit_hit'] = True
                        reason = 'output_limit'
                        break
            result['status'] = reason or 'completed'
    except KeyboardInterrupt:
        result['status'] = 'interrupted'
    except (OSError, ValueError) as exc:
        result['status'] = 'error'
        result['reason'] = type(exc).__name__ + ': ' + str(exc)[:180]
    finally:
        selector.close()
        if process is not None:
            # Also stop same-group children holding a pipe after the parent exits.
            try:
                os.killpg(process.pid, signal.SIGTERM)
                result['cleanup_signals'].append('SIGTERM')
            except ProcessLookupError:
                pass
            if result['cleanup_signals']:
                end = time.monotonic() + grace
                while time.monotonic() < end:
                    if process.poll() is not None:
                        # The leader may have exited while a grandchild remains.
                        try:
                            os.killpg(process.pid, 0)
                        except ProcessLookupError:
                            break
                    time.sleep(.01)
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    result['cleanup_signals'].append('SIGKILL')
                except ProcessLookupError:
                    pass
            try:
                result['child_returncode'] = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                result['status'] = 'cleanup_unconfirmed'
            if process.stdout is not None:
                process.stdout.close()
        result['elapsed_s'] = round(time.monotonic() - start, 6)
    if process is not None:
        if result['status'] == 'completed' and result['child_returncode'] != 0:
            result['status'] = 'child_failed'
        captured, meta = file_bytes(log, max_bytes)
        result['log_summary'] = log_stats(captured, matches, examples)
        result['complete_output'] = (meta['complete'] and not result['output_limit_hit']
                                     and result['status'] in ('completed', 'child_failed'))
    return result


def main():
    started = time.monotonic()
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='mode', required=True)
    for name in ['log', 'data', 'run']:
        parser = sub.add_parser(name)
        parser.add_argument('--max-bytes', type=int, default=DEFAULT_BYTES)
        if name != 'data':
            parser.add_argument('--match', action='append', default=[], help='Literal substring, repeat <=6')
            parser.add_argument('--examples', type=int, default=2)
        if name == 'data':
            parser.add_argument('--format', choices=['json', 'jsonl', 'csv'], default='json')
            parser.add_argument('--field', action='append', default=[], help='JSON pointer or CSV column, repeat <=8')
        if name == 'run':
            parser.add_argument('--log', required=True, type=Path, help='New artifact path, never overwritten')
            parser.add_argument('--timeout', required=True, type=float)
            parser.add_argument('--kill-grace', type=float, default=.5)
            parser.add_argument('command', nargs=argparse.REMAINDER)
        else:
            parser.add_argument('path', type=Path)
    args = ap.parse_args()
    if not 1 <= args.max_bytes <= 128 * 1024 * 1024:
        ap.error('max-bytes must be 1..134217728')
    if hasattr(args, 'match') and (len(args.match) > 6 or any(not m or len(m) > 120 for m in args.match)
                                   or not 0 <= args.examples <= 3):
        ap.error('Use <=6 nonempty matches of <=120 characters and 0..3 examples')
    if hasattr(args, 'field') and (len(args.field) > 8 or any(len(f) > 160 for f in args.field)):
        ap.error('Use <=8 fields of <=160 characters')
    try:
        if args.mode == 'run':
            command = args.command[1:] if args.command[:1] == ['--'] else args.command
            if not command:
                ap.error('A command after -- is required')
            if not (math.isfinite(args.timeout) and 0 < args.timeout <= 86400 and
                    math.isfinite(args.kill_grace) and 0 <= args.kill_grace <= 5):
                ap.error('timeout must be (0,86400]s and kill-grace [0,5]s')
            result = run_command(command, args.log, args.timeout, args.kill_grace,
                                 args.max_bytes, args.match, args.examples)
        else:
            result = inspect_file(args.path, args.format if args.mode == 'data' else 'log',
                getattr(args, 'field', ()), getattr(args, 'match', ()),
                getattr(args, 'examples', 2), args.max_bytes)
        result.setdefault('elapsed_s', round(time.monotonic()-started, 6))
        result = emit(result)
        if args.mode == 'run':
            if result.get('timed_out'):
                return 124
            if result.get('output_limit_hit'):
                return 125
            child = result.get('child_returncode')
            if result['status'] in ('completed', 'child_failed') and child is not None:
                return child if 0 <= child <= 255 else min(255, 128 + abs(child))
        return 0 if result['status'] == 'ok' else 2
    except (OSError, ValueError, UnicodeError, csv.Error, RecursionError) as exc:
        emit({'status': 'error', 'complete': False,
              'reason': type(exc).__name__ + ': ' + str(exc)[:180]})
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
