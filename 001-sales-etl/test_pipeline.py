import csv
import tempfile
import unittest
from pathlib import Path
from pipeline import run


class PipelineTests(unittest.TestCase):
    def test_sample_and_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, rejects = Path(tmp) / 'sales.db', Path(tmp) / 'rejects.json'
            source = Path(__file__).with_name('sales.csv')
            first = run(source, db, rejects)
            self.assertEqual((first['inserted'], first['duplicates'], first['rejected']), (3, 1, 3))
            self.assertEqual(first['product_totals'], [
                {'product': 'Coffee', 'units': 3, 'revenue_cents': 1350},
                {'product': 'Tea', 'units': 3, 'revenue_cents': 900}])
            second = run(source, db, rejects)
            self.assertEqual(second['inserted'], 0)
            self.assertEqual(second['duplicates'], 4)
            self.assertEqual(second['product_totals'], first['product_totals'])

    def test_invalid_prices_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'input.csv'
            with source.open('w', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['order_id', 'order_date', 'product', 'quantity', 'unit_price'])
                for i, price in enumerate(['NaN', 'Infinity', '-1', '1.001']):
                    writer.writerow([str(i), '2026-11-01', 'Tea', 1, price])
            result = run(source, Path(tmp) / 'db', Path(tmp) / 'rejects')
            self.assertEqual(result['rejected'], 4)
            self.assertEqual(result['inserted'], 0)


if __name__ == '__main__':
    unittest.main()
