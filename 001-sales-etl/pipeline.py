"""Load validated sales into SQLite; safe to rerun with the same input."""
import argparse
import csv
import json
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


def run(source, database, rejects):
    rejected = []
    inserted = duplicates = 0
    with sqlite3.connect(database) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS sales (
            order_id TEXT PRIMARY KEY, order_date TEXT NOT NULL,
            product TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents >= 0))''')
        with open(source, newline='', encoding='utf-8') as stream:
            reader = csv.DictReader(stream)
            required = {'order_id', 'order_date', 'product', 'quantity', 'unit_price'}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError('CSV must contain: ' + ', '.join(sorted(required)))
            for line, row in enumerate(reader, 2):
                try:
                    order_id = row['order_id'].strip()
                    product = row['product'].strip()
                    day = date.fromisoformat(row['order_date']).isoformat()
                    quantity = int(row['quantity'])
                    price = Decimal(row['unit_price']) * 100
                    if not order_id or not product or quantity <= 0:
                        raise ValueError('ID/product required; quantity must be positive')
                    if not price.is_finite() or price < 0 or price != price.to_integral_value():
                        raise ValueError('Price must be nonnegative with at most two decimals')
                    cents = int(price)
                    if quantity > 2**31 - 1 or cents > (2**63 - 1) // quantity:
                        raise ValueError('Value exceeds supported integer range')
                    values = (order_id, day, product, quantity, cents)
                    previous = conn.execute('SELECT * FROM sales WHERE order_id=?', (order_id,)).fetchone()
                    if previous:
                        if previous != values:
                            raise ValueError('Conflicting values for existing order_id')
                        duplicates += 1
                    else:
                        conn.execute('INSERT INTO sales VALUES (?, ?, ?, ?, ?)', values)
                        inserted += 1
                except (ValueError, InvalidOperation, TypeError, AttributeError) as error:
                    rejected.append({'line': line, 'reason': str(error), 'row': row})
        report = conn.execute('''SELECT product, SUM(quantity), SUM(quantity * unit_price_cents)
            FROM sales GROUP BY product ORDER BY product''').fetchall()
    Path(rejects).write_text(json.dumps(rejected, indent=2) + '\n', encoding='utf-8')
    return {'inserted': inserted, 'duplicates': duplicates, 'rejected': len(rejected),
            'product_totals': [{'product': p, 'units': q, 'revenue_cents': r} for p, q, r in report]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', default='sales.csv')
    parser.add_argument('--database', default='sales.db')
    parser.add_argument('--rejects', default='rejects.json')
    args = parser.parse_args()
    print(json.dumps(run(args.input, args.database, args.rejects), indent=2))
