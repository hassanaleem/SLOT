
python3 -c 'import csv; r=csv.DictReader(open("time_breakdown.csv")); cols=[c for c in r.fieldnames if c in ("benchmark") or c.endswith("_total_seconds")]; w=csv.DictWriter(open("time_totals.csv","w",newline=""), fieldnames=cols); w.writeheader(); w.writerows({c: row.get(c,"") for c in cols} for row in r)'

python3 generate_colored_table.py
rm -rf time_totals.csv