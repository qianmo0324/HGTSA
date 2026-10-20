"""Observed-run statistics and standalone SVG figures; standard library only."""
from __future__ import annotations

import csv
from dataclasses import asdict
from html import escape
import json
from pathlib import Path
import statistics

from .model import Instance, Schedule
from .solver import Result

# Historical reference ONLY: supplied paper, Tables 5 and 6, not live records.
PAPER = {
    'MK01': {'lb': 40, 'ub': 40, 'best': 40, 'mean': 40, 'seconds': 0.07},
    'MK02': {'lb': 26, 'ub': 26, 'best': 26, 'mean': 26, 'seconds': 0.55},
    'MK03': {'lb': 204, 'ub': 204, 'best': 204, 'mean': 204, 'seconds': 0.36},
    'MK04': {'lb': 60, 'ub': 60, 'best': 60, 'mean': 60, 'seconds': 0.41},
    'MK05': {'lb': 172, 'ub': 172, 'best': 172, 'mean': 172, 'seconds': 1.27},
    'MK06': {'lb': 57, 'ub': 57, 'best': 57, 'mean': 57, 'seconds': 168.82},
    'MK07': {'lb': 139, 'ub': 139, 'best': 139, 'mean': 139, 'seconds': 187.48},
    'MK08': {'lb': 523, 'ub': 523, 'best': 523, 'mean': 523, 'seconds': 0.27},
    'MK09': {'lb': 307, 'ub': 307, 'best': 307, 'mean': 307, 'seconds': 2.51},
    'MK10': {'lb': 189, 'ub': 193, 'best': 193, 'mean': 194.5, 'seconds': 477.08},
}

DEVIATIONS = [
    'Only BRdata MK01-MK10; use final paper parameters, no DPdata 06a DOE.',
    'Unique operation IDs disambiguate the job-ID machine strings.',
    'Priority topological repair; Ren-Wang 2012 step-by-step fidelity unverified.',
    'N8 uses exact DAG evaluation; no approximate evaluation or non-improving-move clipping.',
    'k-insertion uses exact ancestor/descendant feasibility windows instead of printed time inequalities.',
    'ceil rounding for alpha, beta and tabu tenure; max_generations is user configurable (paper unspecified).',
    'Optional time cap and smoke settings alter the paper protocol and are recorded in config.',
]


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def serialize_result(ins: Instance, result: Result, run_index: int, seed: int) -> dict:
    s = result.schedule
    return {
        'instance': ins.name, 'run_index': run_index, 'seed': seed,
        'jobs': len(ins.jobs), 'machines': ins.machine_count,
        'makespan': s.makespan, 'initial_best': result.initial_best,
        'seconds': result.elapsed, 'generations': result.generations,
        'ts_iterations': result.ts_iterations, 'stop_reason': result.stop_reason,
        'history': list(result.history),
        'machine_sequences': s.chromosome,
        'job_sequences_1based': [[ins.operations[o].job + 1 for o in row] for row in s.chromosome],
        'operations': [
            {'id': o, 'job': op.job + 1, 'operation': op.index + 1,
             'machine': s.machine[o] + 1, 'start': s.start[o], 'end': s.end[o],
             'duration': s.duration[o]} for o, op in enumerate(ins.operations)
        ],
        'critical_path': s.critical_path(), 'critical_blocks': s.critical_blocks(),
    }


def aggregate(runs: list[dict], expected_runs: int = 10) -> dict:
    rows = []
    for name in sorted({r['instance'] for r in runs}):
        group = [r for r in runs if r['instance'] == name]
        ref = PAPER[name]
        costs = [r['makespan'] for r in group]
        best, avg = min(costs), statistics.mean(costs)
        rows.append({
            'instance': name, 'size': f"{group[0]['jobs']}x{group[0]['machines']}",
            'runs': len(group), 'expected_runs': expected_runs,
            'lb': ref['lb'], 'known_ub_paper': ref['ub'],
            'best': best, 'mean': avg, 'std': statistics.stdev(costs) if len(costs) > 1 else 0,
            'mean_seconds': statistics.mean(r['seconds'] for r in group),
            'known_ub_re_percent': 100 * (ref['ub'] - ref['lb']) / ref['lb'],
            'best_re_percent': 100 * (best - ref['lb']) / ref['lb'],
            'mean_re_percent': 100 * (avg - ref['lb']) / ref['lb'],
            'paper_best': ref['best'], 'paper_mean': ref['mean'], 'paper_seconds': ref['seconds'],
            'best_gap_to_paper': best - ref['best'], 'mean_gap_to_paper': avg - ref['mean'],
            'lower_bound_hits': sum(c == ref['lb'] for c in costs),
            'time_limit_runs': sum(r.get('stop_reason') == 'time_limit' for r in group),
        })
    return {
        'scope': [r['instance'] for r in rows],
        'complete_br10': len(rows) == 10 and all(r['runs'] == 10 for r in rows),
        'note': 'MRE is computed over the listed completed instances only. Paper bounds are historical.',
        'b_mre_percent': statistics.mean(r['best_re_percent'] for r in rows) if rows else None,
        'av_mre_percent': statistics.mean(r['mean_re_percent'] for r in rows) if rows else None,
        'instances': rows,
    }


def _svg(width: int, height: int, body: list[str]) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img">'
            '<style>text{font-family:Arial,sans-serif;fill:#203047} '
            '.grid{stroke:#e3e9f0;stroke-width:1} .axis{stroke:#718198}</style>'
            '<rect width="100%" height="100%" fill="#fff"/>' + ''.join(body) + '</svg>')


def _text(x, y, text, size=13, anchor='start', fill=None):
    return (f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}"'
            + (f' style="fill:{fill}"' if fill else '') + f'>{escape(str(text))}</text>')


def gantt_svg(ins: Instance, schedule: Schedule, path: Path) -> None:
    width = 1600
    left, right, top = 85, 45, 95
    plot_width = width - left - right
    scale = plot_width / schedule.makespan
    critical = set(schedule.critical_path())
    palette = ['#7ba7f7', '#73c7b3', '#f6cd50', '#b29cdb', '#eb9db4',
               '#93a4bb', '#f2957b', '#82d3ed', '#c5d988', '#e9b677',
               '#9dcbdf', '#ceace1', '#b7c6ec', '#9dd4b5', '#e8b8a4',
               '#d3cf91', '#e0a9d1', '#91bfc0', '#c2b2a1', '#bfc6d1']
    font_size = 12
    # Lay out short-operation labels above the bars. Lane packing reserves
    # disjoint text boxes, without changing the time scale or bar durations.
    layouts = []
    cursor = top
    for row in schedule.chromosome:
        labels = []
        lane_right = []
        for o in row:
            op = ins.operations[o]
            label = f'J{op.job+1}.{op.index+1}'
            text_width = len(label) * font_size * 0.65 + 10
            bar_width = schedule.duration[o] * scale
            center = left + (schedule.start[o] + schedule.duration[o] / 2) * scale
            if bar_width >= text_width:
                labels.append((o, label, center, text_width, -1))
                continue
            center = max(left + text_width / 2, min(width - right - text_width / 2, center))
            x0 = center - text_width / 2
            lane = next((i for i, edge in enumerate(lane_right) if edge + 7 <= x0), len(lane_right))
            if lane == len(lane_right):
                lane_right.append(center + text_width / 2)
            else:
                lane_right[lane] = center + text_width / 2
            labels.append((o, label, center, text_width, lane))
        bar_y = cursor + len(lane_right) * 22
        layouts.append((bar_y, labels))
        cursor = bar_y + 53
    height = cursor + 65
    body = [_text(left, 32, f'{ins.name} | Makespan = {schedule.makespan}', 23),
            _text(left, 57, 'Jx.y = job.operation; short bars use labels above with leader lines; dark outline = critical path', 14)]
    for tick in range(11):
        t = schedule.makespan * tick / 10
        x = left + t * scale
        body += [f'<line class="grid" x1="{x}" y1="{top-8}" x2="{x}" y2="{cursor-13}"/>',
                 _text(x, height - 28, f'{t:g}', 12, 'middle')]
    for m, row in enumerate(schedule.chromosome):
        y, labels = layouts[m]
        body.append(_text(left - 15, y + 21, f'M{m+1}', 15, 'end'))
        for o in row:
            op = ins.operations[o]
            x, w = left + schedule.start[o] * scale, schedule.duration[o] * scale
            title = f'J{op.job+1}.{op.index+1} | M{m+1} | {schedule.start[o]} - {schedule.end[o]}'
            body.append(f'<rect id="operation-{o}" x="{x:.3f}" y="{y}" width="{w:.3f}" height="32" '
                        f'fill="{palette[op.job % len(palette)]}" stroke="{"#17283e" if o in critical else "#fff"}" '
                        f'stroke-width="{2 if o in critical else 0.7}"><title>{escape(title)}</title></rect>')
        # Draw all leaders before their white-backed labels so lines never
        # obscure text in a lower lane.
        for o, label, cx, tw, lane in labels:
            if lane >= 0:
                label_y = y - 9 - lane * 22
                bar_center = left + (schedule.start[o] + schedule.duration[o] / 2) * scale
                body.append(f'<path d="M {cx:.3f} {label_y+3} L {bar_center:.3f} {y-2}" '
                            'stroke="#65768b" stroke-width="0.9" fill="none"/>')
        for o, label, cx, tw, lane in labels:
            label_y = y + 21 if lane < 0 else y - 9 - lane * 22
            if lane >= 0:
                body.append(f'<rect x="{cx-tw/2:.3f}" y="{label_y-13}" width="{tw}" '
                            'height="16" fill="#fff" fill-opacity="0.95"/>')
            body.append(_text(cx, label_y, label, font_size, 'middle'))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_svg(width, height, body), encoding='utf-8')


def comparison_svg(summary: dict, path: Path) -> None:
    rows = summary['instances']
    if not rows:
        return
    width, height = 1280, 670
    left, right, top, bottom = 85, 1180, 125, 490
    max_cost = max(r['mean'] for r in rows) * 1.14
    max_time = max(max(r['mean_seconds'] for r in rows) * 1.14, 0.001)
    scale_cost, scale_time = (bottom - top) / max_cost, (bottom - top) / max_time
    step = (right - left) / len(rows)
    body = [_text(left, 34, 'BRdata | observed results', 24),
            _text(left, 62, f"b-MRE = {summary['b_mre_percent']:.3f}%   av-MRE = {summary['av_mre_percent']:.3f}%   "
                  f"scope = {len(rows)} instances", 15),
            _text(left, 89, 'Bars: lower bound / best / mean      Line: mean runtime (right axis)', 13)]
    for tick in range(6):
        y = bottom - (bottom - top) * tick / 5
        body += [f'<line class="grid" x1="{left}" y1="{y}" x2="{right}" y2="{y}"/>',
                 _text(left - 12, y + 4, f'{max_cost*tick/5:.0f}', 12, 'end'),
                 _text(right + 12, y + 4, f'{max_time*tick/5:.2f}', 12)]
    points = []
    for i, r in enumerate(rows):
        center = left + step * (i + 0.5)
        bar_w = min(23, step / 5)
        for j, (key, color) in enumerate([('lb', '#b8c4d4'), ('best', '#427cdb'), ('mean', '#64b6ad')]):
            h = r[key] * scale_cost
            x = center + (j - 1.5) * bar_w
            body.append(f'<rect x="{x}" y="{bottom-h}" width="{bar_w-1}" height="{h}" fill="{color}">'
                        f'<title>{r["instance"]} {key}: {r[key]:g}</title></rect>')
        y = bottom - r['mean_seconds'] * scale_time
        points.append((center, y))
        body += [_text(center, bottom + 24, r['instance'], 13, 'middle'),
                 _text(center, bottom + 45, f"RE {r['best_re_percent']:.2f}%", 11, 'middle'),
                 _text(center, bottom + 64, f"n={r['runs']}", 11, 'middle')]
    coords = ' '.join(f'{x},{y}' for x, y in points)
    body.append(f'<polyline points="{coords}" fill="none" stroke="#dd6b35" stroke-width="2.5"/>')
    for (x, y), r in zip(points, rows):
        body.append(f'<circle cx="{x}" cy="{y}" r="4" fill="#dd6b35"><title>{r["mean_seconds"]:.3f}s</title></circle>')
    body += [_text(left, 113, 'Makespan', 12), _text(right, 113, 'Seconds', 12, 'end'),
             _text(left, 604, 'RE labels use observed best versus paper LB; MRE averages the displayed instances equally.', 13),
             _text(left, 628, 'See manifest.json for parameters/time caps; paper Java runtimes are reference values only.', 13)]
    path.write_text(_svg(width, height, body), encoding='utf-8')


def write_reports(output: Path, runs: list[dict], expected_runs: int = 10) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    summary = aggregate(runs, expected_runs)
    write_json(output / 'summary.json', summary)
    rows = summary['instances']
    if not rows:
        return summary
    with (output / 'summary.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fields = ['instance', 'run_index', 'seed', 'makespan', 'seconds', 'initial_best',
              'generations', 'ts_iterations', 'stop_reason']
    with (output / 'raw_runs.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(runs)
    comparison_svg(summary, output / 'comparison.svg')
    header = '<tr>' + ''.join(f'<th>{h}</th>' for h in
        ('Instance', 'Size', 'Runs', 'LB', 'Paper UB', 'Best', 'Mean', 'Seconds', 'Best RE %', 'Gantt')) + '</tr>'
    table = []
    for r in rows:
        cells = [r['instance'], r['size'], r['runs'], r['lb'], r['known_ub_paper'], r['best'],
                 f"{r['mean']:.2f}", f"{r['mean_seconds']:.3f}", f"{r['best_re_percent']:.3f}"]
        table.append('<tr>' + ''.join(f'<td>{escape(str(c))}</td>' for c in cells)
                     + f'<td><a href="gantt/{r["instance"]}.svg">Open</a></td></tr>')
    html = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>HGTSA results</title>'
            '<style>body{font:15px Arial,sans-serif;margin:32px;color:#203047}table{border-collapse:collapse}'
            'td,th{padding:10px;border:1px solid #d5dde8;text-align:right}th{background:#edf2f8}'
            'img{max-width:100%}li{margin:8px 0}</style>'
            '<h1>HGTSA · MK01–MK10 实验结果</h1>'
            '<p>以下为实际完成的运行结果。参数、时间上限和实现差异见 manifest.json；不表示已达到论文指标。</p>'
            '<p>先查看运行次数，满 10 个算例各 10 次后，才具备所要求的样本数量。运行时间包含初始化与搜索，不包含绘图和文件保存。</p>'
            '<img src="comparison.svg" alt="Makespan and runtime comparison">'
            '<table>' + header + ''.join(table) + '</table><h2>实现差异</h2><ul>'
            + ''.join(f'<li>{escape(d)}</li>' for d in DEVIATIONS) + '</ul></html>')
    (output / 'index.html').write_text(html, encoding='utf-8')
    return summary
