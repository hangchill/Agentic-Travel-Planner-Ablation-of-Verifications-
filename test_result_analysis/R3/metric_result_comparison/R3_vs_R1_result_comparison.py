"""Build the compiled R1 vs R3 effectiveness table (All queries) from the merged tables.

Writes <output-dir>/R1_vs_R3_effectiveness_compiled.csv with the columns
metric, R1, R3, source. Reads only test_result_analysis/merged/table*.csv
(written by scripts/result_analysis/build_test_result_tables.py); run that script first.

R3_vs_R0_result_comparison.py uses main() from this file with the other method R0.

Usage (from the repository root):
  python test_result_analysis/R3/R3_vs_R1_result_comparison.py
"""
import argparse
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
MERGED = HERE.parent / "merged"
GROUP = "All"


def load(table):
    path = MERGED / f"{table}.csv"
    if not path.is_file():
        raise SystemExit(f"{path} is missing; run scripts/result_analysis/build_test_result_tables.py first")
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def value(tables, table, metric_prefix, label):
    """The All-group value of the first metric in <table> that starts with metric_prefix."""
    for row in tables[table]:
        if row["metric"].startswith(metric_prefix):
            column = f"{GROUP} {label}"
            if column not in row:
                raise SystemExit(f"merged/{table}.csv has no column {column!r}")
            return row[column]
    raise SystemExit(f"merged/{table}.csv has no metric starting with {metric_prefix!r}")


def number(text):
    return float(text) if "." in text else int(text)


def compiled_rows(labels):
    tables = {name: load(name) for name in ("table1_pc", "table2_cs", "table3_repair_process", "table4_eval_exp")}
    get = lambda table, prefix, label: value(tables, table, prefix, label)

    def at_most_two_cs(label):
        return sum(number(get("table2_cs", f"Final plans with {n} failed CS check", label)) for n in (0, 1, 2))

    def all_pass(label):
        ratio = number(get("table4_eval_exp", "All-pass ratio (%)", label))
        queries = number(get("table1_pc", "Queries (n)", label))
        return f"{round(ratio * queries / 100)} ({ratio:.1f}%)"

    specs = [
        ("Avg % CS checks passed: change (pp)",
         lambda l: get("table2_cs", "Avg % CS checks passed per query - change (percentage points)", l),
         "table2_cs: Avg % CS checks passed per query - change (percentage points)"),
        ("Final plans with at most 2 CS checks failed", at_most_two_cs,
         "table2_cs: Final plans with 0 + 1 + 2 failed CS checks"),
        ("Commonsense macro (%)",
         lambda l: get("table4_eval_exp", "Commonsense macro (%)", l),
         "table4_eval_exp: Commonsense macro (%) - plans passing every CS check"),
        ("Avg % PC passed: change (pp)",
         lambda l: get("table1_pc", "Avg % PC passed per query - change (percentage points)", l),
         "table1_pc: Avg % PC passed per query - change (percentage points)"),
        ("Final plans with all PCs passed",
         lambda l: get("table1_pc", "Final plans with 0 failed PC", l),
         "table1_pc: Final plans with 0 failed PC"),
        ("Final plans with 1 failed PC only",
         lambda l: get("table1_pc", "Final plans with 1 failed PC", l),
         "table1_pc: Final plans with 1 failed PC"),
        ("Logical macro (%)",
         lambda l: get("table4_eval_exp", "Logical macro (%)", l),
         "table4_eval_exp: Logical macro (%) - plans passing every personal constraint"),
        ("All-pass (schema + CS + PC)", all_pass,
         "table4_eval_exp: All-pass ratio (%); count = ratio x table1_pc Queries (n)"),
        ("Avg tokens per query",
         lambda l: get("table3_repair_process", "[per query] Avg tokens spent per query (queries with complete token data)", l),
         "table3_repair_process: [per query] Avg tokens spent per query (queries with complete token data)"),
        ("Avg repair time per query (s)",
         lambda l: get("table3_repair_process", "[per query] Avg repair time per query (s)", l),
         "table3_repair_process: [per query] Avg repair time per query (s)"),
    ]
    return [{"metric": f"{name} ({GROUP})", **{label: func(label) for label in labels}, "source": source}
            for name, func, source in specs]


def main(argv=None, other="R1"):
    filename = f"{other}_vs_R3_effectiveness_compiled.csv" if other == "R1" else f"{other}vsR3_effectiveness_compiled.csv"
    parser = argparse.ArgumentParser(description=f"Build {filename} from the merged tables.")
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args(argv)

    labels = (other, "R3")
    rows = compiled_rows(labels)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / filename
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("metric", *labels, "source"))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} rows -> {path}")


if __name__ == "__main__":
    main()
