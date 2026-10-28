"""Plot final plan vs starting plan for two strategies, by constraint type.

Two panels (personal constraints, commonsense). In each, one stacked bar per strategy splits
its queries by whether repair left them with more, the same, or fewer checks passing than
their starting plan, with the start -> final pass rate under the bar. The runs start from
different initial plans, so the bars compare each strategy's change, not its final level.

Reads only the per-query test reporting (test_result_analysis/<strategy>/per_query.csv):
pc_passed_initial/final and pc_total for personal constraints, cs_passed_initial/final and
cs_total for commonsense.

Usage:
  python scripts/result_analysis/plot_r0_vs_r2_outcomes.py \
      [--left R0] [--right R2] [--reporting-dir test_result_analysis] \
      [--output results/analysis/ablation_comparisons/r0_vs_r2/outcomes_by_constraint_type.png]
"""
import argparse
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

LABELS = {'R0': 'No Rollback', 'R1': 'Targeted', 'R2': 'Rollback Protection',
          'R3': 'Adaptive Scope', 'R4': 'Matrix-guided'}
COLORS = {'worse': '#e34948', 'same': '#d6d5d0', 'better': '#2a78d6'}
INK, INK_2 = '#0b0b0b', '#52514e'
## (title, note, column prefix); the note says which strategy protects the type.
PANELS = [('Personal constraints', 'protected by R2', 'pc'),
          ('Commonsense', 'not protected', 'cs')]


## ---------- per-query evidence ----------

def outcome_counts(per_query, prefix):
    """Queries better / same / worse than their start, plus pooled start and final passes."""
    delta = per_query[f'{prefix}_passed_final'] - per_query[f'{prefix}_passed_initial']
    return {
        'worse': int((delta < 0).sum()),
        'same': int((delta == 0).sum()),
        'better': int((delta > 0).sum()),
        'start': int(per_query[f'{prefix}_passed_initial'].sum()),
        'end': int(per_query[f'{prefix}_passed_final'].sum()),
        'total': int(per_query[f'{prefix}_total'].sum()),
        'queries': len(per_query),
    }


## ---------- figure ----------

def plot(strategies, reporting_dir, output):
    data = {s: pd.read_csv(reporting_dir / s / 'per_query.csv') for s in strategies}
    n = max(len(df) for df in data.values())

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), facecolor='white')
    fig.subplots_adjust(left=0.05, right=0.98, top=0.66, bottom=0.20, wspace=0.12)
    fig.text(0.05, 0.95, 'Final plan vs starting plan, by constraint type',
             fontsize=14, fontweight='bold', color=INK)
    fig.text(0.05, 0.925, textwrap.fill(f'{n} held-out test queries per strategy. Each bar splits the queries '
             'by whether repair left them with more, the same, or fewer checks passing than '
             'their starting plan.', 130), fontsize=9.5, color=INK_2, va='top')
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLORS[k]) for k in ('better', 'same', 'worse')]
    fig.legend(handles, ['More checks passing', 'Unchanged', 'Fewer checks passing'],
               loc='upper left', bbox_to_anchor=(0.045, 0.865), ncol=3, frameon=False,
               fontsize=9.5, handlelength=1.1, columnspacing=1.6)

    for ax, (title, note, prefix) in zip(axes, PANELS):
        counts = {s: outcome_counts(data[s], prefix) for s in strategies}
        total = next(iter(counts.values()))['total']
        ax.set_title(f'{title}\n', loc='left', fontsize=11.5, fontweight='bold', color=INK, pad=4)
        ax.text(0, 1.02, f'{total} checks · {note}', transform=ax.transAxes,
                fontsize=9, color=INK_2, va='bottom')
        for row, s in enumerate(strategies):
            c, y, left = counts[s], len(strategies) - 1 - row, 0
            for key in ('worse', 'same', 'better'):
                width = c[key]
                if not width:
                    continue
                ax.barh(y, width, left=left, height=0.5, color=COLORS[key], edgecolor='white',
                        linewidth=1.5)
                ## Label a segment only when it is wide enough to hold the number.
                if width >= 2:
                    ax.text(left + width / 2, y, str(width), ha='center', va='center',
                            fontsize=9.5, fontweight='bold',
                            color=INK if key == 'same' else 'white')
                left += width
            zero = '0 worse · ' if c['worse'] == 0 else ''
            ax.text(0, y - 0.38, f"{zero}pass rate {100 * c['start'] / c['total']:.1f}% → "
                    f"{100 * c['end'] / c['total']:.1f}%", fontsize=8.5, color=INK_2, va='top')
        ax.set_yticks(range(len(strategies)), [s for s in reversed(strategies)],
                      fontsize=11, fontweight='bold', color=INK)
        ax.set_xlim(0, n)
        ax.set_xticks([0, n // 2, n])
        ax.set_ylim(-0.85, len(strategies) - 0.55)
        ax.tick_params(axis='x', labelsize=8.5, colors=INK_2, length=0)
        ax.tick_params(axis='y', length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)

    names = ' and '.join(strategies)
    fig.text(0.05, 0.075, textwrap.fill(f"R2's rollback guards personal constraints only; commonsense checks are "
             f'not protected by either strategy. {names} start from different initial plans, so '
             'compare the change, not the final level. One run per strategy.', 150),
             fontsize=8.5, color=INK_2, va='top')

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=200, facecolor='white')
    fig.savefig(output.with_suffix('.svg'), facecolor='white')
    plt.close(fig)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--left', default='R0')
    parser.add_argument('--right', default='R2')
    parser.add_argument('--reporting-dir', type=Path, default=ROOT / 'test_result_analysis')
    parser.add_argument('--output', type=Path, default=ROOT / 'results/analysis/ablation_comparisons'
                        / 'r0_vs_r2/outcomes_by_constraint_type.png')
    args = parser.parse_args()
    plot([args.left, args.right], args.reporting_dir, args.output)
    print(f'Wrote {args.output} and {args.output.with_suffix(".svg")}')


if __name__ == '__main__':
    main()
