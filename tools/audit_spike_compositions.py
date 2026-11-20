"""Read cached UPbR26XML tracer blocks with xlrd, without modifying workbooks.

Usage: python tools/audit_spike_compositions.py book.xls [book2.xls ...]
The output groups every populated fraction by its exact rows 150–171.
Rows 172–173 are spike amounts for a fraction, not solution compositions.
"""
import argparse
import json
from pathlib import Path

import xlrd


def audit(path):
    book = xlrd.open_workbook(str(path), on_demand=True)
    try:
        if 'Data Reduction Engine' not in book.sheet_names():
            return []
        raw = book.sheet_by_name('Raw Data Input')
        engine = book.sheet_by_name('Data Reduction Engine')
        groups = {}
        for col in range(4, raw.ncols):
            if raw.cell_type(4, col) != xlrd.XL_CELL_NUMBER or not raw.cell_value(4, col):
                continue
            ec = col - 2
            composition = tuple(engine.cell_value(r - 1, ec) for r in range(150, 172))
            key = (raw.cell_value(7, col), composition)
            groups.setdefault(key, []).append({
                'fraction': raw.cell_value(3, col), 'column': xlrd.formula.colname(ec)})
        return [{'file': str(path), 'spike': spike, 'fractions': fractions,
                 'rows': dict(zip(map(str, range(150, 172)), values))}
                for (spike, values), fractions in groups.items()]
    finally:
        book.release_resources()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbooks', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = json.dumps([group for p in args.workbooks for group in audit(p)], indent=2) + '\n'
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end='')


if __name__ == '__main__':
    main()
