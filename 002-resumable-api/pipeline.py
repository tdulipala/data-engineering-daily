"""Ingest a stable paginated JSON snapshot, committing rows and cursor together."""
import argparse
import json
import sqlite3
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def http_page(base, page, attempts=3, sleep=time.sleep):
    for attempt in range(attempts):
        try:
            with urlopen(f'{base.rstrip("/")}/page{page}.json', timeout=10) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            retryable = not isinstance(exc, HTTPError) or exc.code in (429, 500, 502, 503, 504)
            if not retryable or attempt == attempts - 1:
                raise
            sleep(0.5 * 2 ** attempt)


def ingest(db, fetch, source):
    """One writer per DB. Each DB is bound to one immutable source snapshot."""
    conn = sqlite3.connect(db)
    pages = 0
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, category TEXT NOT NULL,
                amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0));
            CREATE TABLE IF NOT EXISTS checkpoint (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                source TEXT NOT NULL, next_page INTEGER);
        ''')
        with conn:
            conn.execute('INSERT OR IGNORE INTO checkpoint VALUES (1, ?, 1)', (source,))
        saved_source, page = conn.execute('SELECT source, next_page FROM checkpoint').fetchone()
        if source != saved_source:
            raise ValueError('Database belongs to another source; use a new database')
        while page is not None:
            payload = fetch(page)
            if not isinstance(payload, dict) or not isinstance(payload.get('items'), list) or 'next_page' not in payload:
                raise ValueError('Expected items list and next_page')
            next_page = payload['next_page']
            if next_page is not None and (type(next_page) is not int or next_page != page + 1):
                raise ValueError('next_page must advance by one or be null')
            # A malformed record or conflicting duplicate rolls back the whole page.
            with conn:
                for item in payload['items']:
                    if not isinstance(item, dict):
                        raise ValueError('Event must be an object')
                    event_id, category, amount = item.get('id'), item.get('category'), item.get('amount_cents')
                    if not isinstance(event_id, str) or not event_id.strip() or not isinstance(category, str) or not category.strip():
                        raise ValueError('Nonempty string id and category required')
                    if type(amount) is not int or not 0 <= amount <= 10**12:
                        raise ValueError('amount_cents must be an integer between 0 and 10^12')
                    values = (event_id, category, amount)
                    old = conn.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
                    if old is not None and old != values:
                        raise ValueError(f'Conflicting event: {event_id}')
                    conn.execute('INSERT OR IGNORE INTO events VALUES (?, ?, ?)', values)
                conn.execute('UPDATE checkpoint SET next_page=? WHERE singleton=1', (next_page,))
            pages += 1
            page = next_page
        rows = conn.execute('SELECT category, COUNT(*), SUM(amount_cents) FROM events GROUP BY category ORDER BY category').fetchall()
        return {'pages_committed': pages, 'totals': [dict(category=c, events=n, amount_cents=a) for c, n, a in rows]}
    finally:
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default='events.db')
    parser.add_argument('--base-url', help='HTTP endpoint serving page1.json, page2.json, etc.')
    args = parser.parse_args()
    if args.base_url:
        source = args.base_url.rstrip('/')
        if not source.startswith(('http://', 'https://')):
            parser.error('base-url must use HTTP or HTTPS')
        fetch = lambda page: http_page(source, page)
    else:
        fixtures = Path(__file__).with_name('fixtures')
        source = 'synthetic-orders-v1'
        fetch = lambda page: json.loads((fixtures / f'page{page}.json').read_text())
    print(json.dumps(ingest(args.database, fetch, source), indent=2))
