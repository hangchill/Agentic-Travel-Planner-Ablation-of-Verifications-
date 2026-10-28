"""Render the full R4 training matrix as a slide-ready heatmap.

From the repository root:
    python scripts/matrix_building/plot_main_matrix.py

Dependencies: matplotlib and numpy. The source CSV is read without modification.
Defaults are anchored to this script, so it also works from another directory.
PNG, SVG and PDF exports use the same figure. Numbers are probabilities on the
0-1 scale, matching the slide example; smaller numbers are count/support.
"""

import argparse
import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Rectangle
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "r4/main_matrix_from_subset_train_r0_r3_10x10.csv"
FAMILIES = (
    "trip_specification", "party_resources", "monetary_budget",
    "accommodation", "dining", "attraction", "transport_mode",
    "travel_extent", "schedule_order", "commonsense_repair",
)
LABELS = (
    "Trip\nspecification", "Party\nresources", "Monetary\nbudget",
    "Accommodation", "Dining", "Attraction", "Transport\nmode",
    "Travel\nextent", "Schedule\norder", "Commonsense\nrepair",
)


def load_matrix(path):
    """Require all 100 unique cells and check the plotted count/support ratios."""
    cells = {}
    required = {
        "source_family", "destination_family", "regression_count",
        "support_count", "support_query_count", "regression_probability",
        "evidence_status",
    }
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"{path}: expected the long-format R4 main matrix")
        for row in reader:
            source, destination = row["source_family"], row["destination_family"]
            key = source, destination
            if source not in FAMILIES or destination not in FAMILIES or key in cells:
                raise ValueError(f"Unknown or duplicate matrix cell: {key}")
            raw_probability = row["regression_probability"].strip()
            probability = float(raw_probability) if raw_probability else None
            count = int(row["regression_count"]) if row["regression_count"] else None
            support = int(row["support_count"]) if row["support_count"] else None
            queries = int(row["support_query_count"]) if row["support_query_count"] else None
            status = row["evidence_status"]
            if source == destination:
                if status != "structural_diagonal" or probability is not None or count or support:
                    raise ValueError(f"Expected an unsupported structural diagonal: {key}")
            elif probability is not None:
                if status not in ("observed", "observed_partial"):
                    raise ValueError(f"Measured probability has invalid status: {key}")
                if (not math.isfinite(probability) or not 0 <= probability <= 1
                        or support is None or support <= 0 or count is None
                        or not 0 <= count <= support
                        or not math.isclose(probability, count / support, abs_tol=1e-9)
                        or queries is None or not 1 <= queries <= support):
                    raise ValueError(f"Invalid probability/count/support: {key}")
            elif status not in ("unobserved", "unavailable") or count or support:
                raise ValueError(f"Missing probability has inconsistent evidence: {key}")
            cells[key] = dict(probability=probability, count=count, support=support,
                              queries=queries, status=status)
    expected = {(source, destination) for source in FAMILIES for destination in FAMILIES}
    if set(cells) != expected:
        raise ValueError(f"Expected all 100 cells; missing {len(expected - set(cells))}")
    return cells


def draw_heatmap(cells, decimals=3):
    """Keep unknown evidence separate from observed zero and structural cells."""
    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none",
                         "pdf.fonttype": 42, "axes.unicode_minus": False})
    fig = plt.figure(figsize=(18, 11), facecolor="white")
    ax = fig.add_axes((0.17, 0.22, 0.72, 0.60))
    color_ax = fig.add_axes((0.915, 0.25, 0.014, 0.54))
    cmap = LinearSegmentedColormap.from_list(
        "regression_red", ["#fff8f6", "#f9d5cb", "#ed9c8c", "#cf5d50", "#942d2d"]
    )
    cmap.set_bad("#e4e8ed")
    values = np.array([
        [np.nan if cells[source, dest]["probability"] is None
         else cells[source, dest]["probability"] for dest in FAMILIES]
        for source in FAMILIES
    ])
    plot = ax.imshow(np.ma.masked_invalid(values), cmap=cmap,
                     norm=Normalize(0, 1), aspect="auto", interpolation="nearest")
    for i, source in enumerate(FAMILIES):
        for j, destination in enumerate(FAMILIES):
            cell = cells[source, destination]
            probability = cell["probability"]
            if i == j:
                ax.add_patch(Rectangle((j - 0.5, i - 0.5), 1, 1,
                                       facecolor="#f3f4f6", edgecolor="none"))
                ax.text(j, i, "\u2014", ha="center", va="center", fontsize=17, color="#576270")
            elif probability is None:
                ax.text(j, i, "N/A", ha="center", va="center", fontsize=12, color="#586373")
            else:
                foreground = "white" if probability >= 0.65 else "#262b32"
                marker = "\u2020" if cell["status"] == "observed_partial" else ""
                ax.text(j, i - 0.12, f"{probability:.{decimals}f}{marker}",
                        ha="center", va="center", fontsize=13, color=foreground,
                        fontweight="semibold" if probability > 0 else "normal")
                ax.text(j, i + 0.23, f"{cell['count']}/{cell['support']}",
                        ha="center", va="center", fontsize=9.5, color=foreground)
    ax.set_xticks(range(10), LABELS, fontsize=11.5)
    ax.set_yticks(range(10), [label.replace("\n", " ") for label in LABELS], fontsize=12)
    ax.xaxis.tick_top()
    ax.xaxis.set_label_position("top")
    ax.set_xlabel("Affected family (passing before repair)", fontsize=13, labelpad=19)
    ax.set_ylabel("Repair target family", fontsize=13, labelpad=20)
    ax.tick_params(axis="both", which="major", length=0, pad=10)
    ax.set_xticks(np.arange(-0.5, 10, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 10, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.6)
    ax.tick_params(which="minor", bottom=False, left=False, top=False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    colorbar = fig.colorbar(plot, cax=color_ax, ticks=np.linspace(0, 1, 6))
    colorbar.set_label("Regression probability (0\u20131)", fontsize=12, labelpad=12)
    colorbar.ax.tick_params(labelsize=10, length=0, pad=6)
    colorbar.outline.set_visible(False)
    observed = sum(cell["probability"] is not None for cell in cells.values())
    positive = sum(cell["probability"] is not None and cell["probability"] > 0
                   for cell in cells.values())
    fig.text(0.17, 0.965, "Training regression-risk matrix used by R4",
             fontsize=24, fontweight="bold", color="#202936")
    fig.text(0.17, 0.925,
             f"R0\u2013R3 pooled training evidence  |  Candidate repairs  |  "
             f"{observed}/90 off-diagonal pairs observed; {positive} non-zero",
             fontsize=12.5, color="#586373")
    fig.text(0.17, 0.17,
             "Cell: regression probability; smaller text: regressions / eligible attempts.",
             fontsize=12, color="#303946")
    fig.text(0.17, 0.135,
             "N/A = no measured probability     \u2014 = structural diagonal     "
             "0.000 = no observed regressions in eligible attempts",
             fontsize=11, color="#586373")
    small_sample = [(source, dest, cell) for (source, dest), cell in cells.items()
                    if cell["probability"] == 1 and cell["queries"] == 1]
    if small_sample:
        names = dict(zip(FAMILIES, [label.replace("\n", " ") for label in LABELS]))
        examples = "; ".join(f"{names[source]} \u2192 {names[dest]} ({cell['count']}/{cell['support']})"
                             for source, dest, cell in small_sample)
        fig.text(0.17, 0.10, f"Small samples: {examples} each come from one query.",
                 fontsize=10.5, color="#586373")
    if any(cell["status"] == "observed_partial" for cell in cells.values()):
        fig.text(0.17, 0.067, "\u2020 Partial strategy coverage. Observed rates are historical estimates, not guarantees.",
                 fontsize=10.5, color="#586373")
    return fig


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, help="Default: a heatmaps/ folder beside the input")
    parser.add_argument("--formats", nargs="+", choices=("png", "svg", "pdf"),
                        default=["png", "svg", "pdf"])
    parser.add_argument("--dpi", type=int, default=240)
    parser.add_argument("--decimals", type=int, choices=range(1, 7), default=3)
    args = parser.parse_args(argv)
    if args.dpi <= 0:
        parser.error("--dpi must be positive")
    cells = load_matrix(args.input)
    figure = draw_heatmap(cells, args.decimals)
    output_dir = args.output_dir or args.input.parent / "heatmaps"
    output_dir.mkdir(parents=True, exist_ok=True)
    for extension in dict.fromkeys(args.formats):
        output = output_dir / f"{args.input.stem}_heatmap.{extension}"
        figure.savefig(output, dpi=args.dpi, facecolor="white")
        print(f"Saved: {output.resolve()}")
    plt.close(figure)
    observed = [cell for cell in cells.values() if cell["probability"] is not None]
    print(f"Validated 100 cells: {sum(cell['probability'] > 0 for cell in observed)} positive, "
          f"{sum(cell['probability'] == 0 for cell in observed)} observed zero, "
          f"{90 - len(observed)} unavailable, 10 diagonal.")


if __name__ == "__main__":
    main()
