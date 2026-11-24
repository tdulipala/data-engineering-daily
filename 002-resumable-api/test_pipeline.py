import copy
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from pipeline import ingest, http_page


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'events.db')
        self.pages = {n: json.loads((Path(__file__).parent / 'fixtures' / f'page{n}.json').read_text()) for n in (1, 2)}

    def test_resume_after_fetch_failure_and_skip_completed(self):
        def broken(n):
            if n == 2:
                raise TimeoutError('simulated interruption')
            return self.pages[n]
        with self.assertRaises(TimeoutError):
            ingest(self.db, broken, 'v1')
        requested = []
        def resumed(n):
            requested.append(n)
            return self.pages[n]
        result = ingest(self.db, resumed, 'v1')
        self.assertEqual(requested, [2])
        self.assertEqual(result['totals'], [dict(category='books', events=2, amount_cents=2000), dict(category='games', events=1, amount_cents=2500)])
        self.assertEqual(ingest(self.db, lambda n: self.fail('should not fetch'), 'v1')['pages_committed'], 0)

    def test_bad_page_rolls_back_rows_and_cursor(self):
        bad = copy.deepcopy(self.pages)
        bad[1]['items'][1]['amount_cents'] = True
        with self.assertRaises(ValueError):
            ingest(self.db, bad.__getitem__, 'v1')
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT next_page FROM checkpoint').fetchone()[0], 1)
        self.assertEqual(ingest(self.db, self.pages.__getitem__, 'v1')['pages_committed'], 2)

    def test_conflict_and_cursor_loop_fail(self):
        bad = copy.deepcopy(self.pages)
        bad[2]['items'][0]['amount_cents'] = 1
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            ingest(self.db, bad.__getitem__, 'v1')
        bad[2]['next_page'] = 2
        with self.assertRaisesRegex(ValueError, 'advance'):
            ingest(self.db, bad.__getitem__, 'v1')
        self.assertEqual(ingest(self.db, self.pages.__getitem__, 'v1')['pages_committed'], 1)

    def test_source_binding(self):
        ingest(self.db, self.pages.__getitem__, 'v1')
        with self.assertRaisesRegex(ValueError, 'another source'):
            ingest(self.db, self.pages.__getitem__, 'v2')

    def test_http_retry_and_nonretryable_error(self):
        error = HTTPError('http://example.test', 503, 'Unavailable', {}, None)
        response = io.BytesIO(json.dumps(self.pages[1]).encode())
        with patch('pipeline.urlopen', side_effect=[error, response]) as request:
            delays = []
            self.assertEqual(http_page('http://example.test', 1, sleep=delays.append), self.pages[1])
            self.assertEqual(delays, [0.5])
            self.assertEqual(request.call_count, 2)
        with patch('pipeline.urlopen', side_effect=HTTPError('http://example.test', 404, 'Missing', {}, None)) as request:
            with self.assertRaises(HTTPError):
                http_page('http://example.test', 1, sleep=lambda _: None)
            self.assertEqual(request.call_count, 1)

    def test_retry_exhaustion(self):
        with patch('pipeline.urlopen', side_effect=TimeoutError) as request:
            with self.assertRaises(TimeoutError):
                http_page('http://example.test', 1, sleep=lambda _: None)
            self.assertEqual(request.call_count, 3)


if __name__ == '__main__':
    unittest.main()
