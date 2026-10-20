"""Polish saved reports without changing solver sources or checkpoint fingerprints.

Usage: python format_results.py results/paper
Statistics are recalculated from validated independent-run checkpoints.
"""
from __future__ import annotations

import argparse
import csv
from html import escape
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from hgtsa.reporting import _svg, _text
from plot_results import regenerate
from run_experiments import DEFAULT_DATA


def uniform_gantt(path: Path) -> None:
    ns = '{http://www.w3.org/2000/svg}'
    ET.register_namespace('', ns[1:-1])
    root = ET.parse(path).getroot()
    for rect in root.iter(ns + 'rect'):
        if rect.get('id', '').startswith('operation-'):
            rect.set('stroke', '#536174')
            rect.set('stroke-width', '0.7')
    for text in root.iter(ns + 'text'):
        if text.text and text.text.startswith('Jx.y ='):
            text.text = 'Jx.y = job.operation'
    path.write_text(ET.tostring(root, encoding='unicode'), encoding='utf-8')


def comparison(summary: dict, path: Path) -> None:
    rows = summary['instances']
    width, height = 1200, 570
    left, right, top, bottom = 90, 1105, 120, 445
    ymax = max(r['mean'] for r in rows) * 1.18
    step = (right - left) / len(rows)
    colors = ['#bdc9d7', '#4b7fca', '#6bb4a5']
    body = [_text(left, 35, 'BRdata | ' + ', '.join(r['instance'] for r in rows), 22),
            _text(right, 35, f"b-MRE {summary['b_mre_percent']:.2f}%   av-MRE {summary['av_mre_percent']:.2f}%", 14, 'end')]
    # A compact legend for the three makespan series.
    body.append('<g id="legend" aria-label="Series legend">')
    for x, label, color in zip([390, 550, 710], ['LB', 'Best', 'Mav'], colors):
        body.append(f'<rect x="{x}" y="65" width="23" height="14" rx="2" fill="{color}"/>')
        body.append(_text(x + 33, 77, label, 14))
    body.append('</g>')
    for tick in range(6):
        y = bottom - (bottom - top) * tick / 5
        body += [f'<line class="grid" x1="{left}" y1="{y}" x2="{right}" y2="{y}"/>',
                 _text(left - 13, y + 4, f'{ymax*tick/5:.0f}', 12, 'end')]
    for i, row in enumerate(rows):
        center = left + step * (i + 0.5)
        bar = min(40, step / 5)
        for j, (key, color) in enumerate(zip(['lb', 'best', 'mean'], colors)):
            h = row[key] / ymax * (bottom - top)
            x = center + (j - 1.5) * bar
            body.append(f'<rect x="{x}" y="{bottom-h}" width="{bar-3}" height="{h}" fill="{color}">'
                        f'<title>{row["instance"]} {key}: {row[key]:g}</title></rect>')
            # One centered value when all three bars coincide; otherwise label each.
            if len({row['lb'], row['best'], row['mean']}) > 1:
                body.append(_text(x + (bar - 3) / 2, bottom - h - 8, f'{row[key]:g}', 11, 'middle'))
        if row['lb'] == row['best'] == row['mean']:
            body.append(_text(center, bottom - row['mean'] / ymax * (bottom-top) - 9,
                              f'{row["mean"]:g}', 13, 'middle'))
        body += [_text(center, bottom + 27, row['instance'], 15, 'middle'),
                 _text(center, bottom + 49, f"RE {row['best_re_percent']:.2f}% | n={row['runs']}", 11, 'middle')]
    body += [_text(left, top - 14, 'Makespan', 13),
             f'<line class="axis" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}"/>']
    path.write_text(_svg(width, height, body), encoding='utf-8')


def format_results(output: Path, data_dir: Path = DEFAULT_DATA) -> dict:
    summary = regenerate(output, data_dir)
    rows = summary['instances']
    for row in rows:
        uniform_gantt(output / 'gantt' / f'{row["instance"]}.svg')
    comparison(summary, output / 'comparison.svg')
    headers = ['Instance', 'UB（本机）', 'UB（原paper）', 'LB', 'Best', 'Mav', 'b-MRE (%)', 'av-MRE (%)']
    values = [[r['instance'], r['best'], r['known_ub_paper'], r['lb'], r['best'], f"{r['mean']:.2f}", '—', '—']
              for r in rows]
    values.append(['Overall', '—', '—', '—', '—', '—',
                   f"{summary['b_mre_percent']:.2f}", f"{summary['av_mre_percent']:.2f}"])
    with (output / 'experiment_table.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(values)
    table = '<table><thead><tr>' + ''.join(f'<th>{escape(h)}</th>' for h in headers) + '</tr></thead><tbody>'
    for cells in values:
        table += '<tr>' + ''.join(f'<td>{escape(str(v))}</td>' for v in cells) + '</tr>'
    table += '</tbody></table>'
    scope = ', '.join(r['instance'] for r in rows)
    counts = '；'.join(f"{r['instance']}：{r['runs']} 次" for r in rows)
    note = ('本机 UB 为本次已完成运行中的最好可行解，因此等于 Best。'
            'b-MRE 和 av-MRE 是跨算例平均指标，仅在 Overall 行列出，统计范围为上述已完成算例。'
            '单个算例的误差可查 summary.csv 中的 best_re_percent 和 mean_re_percent。')
    style = ('<style>body{font:15px Arial,"Microsoft YaHei",sans-serif;color:#26384c;max-width:1240px;'
             'margin:36px auto;padding:0 24px}h1{font-size:25px}p{line-height:1.8;color:#566477}'
             'table{width:100%;border-collapse:collapse;margin:24px 0}th,td{padding:13px 15px;border:1px solid #dce3eb;'
             'text-align:center}th{background:#edf2f8}tbody tr:last-child{background:#f3f6fa;font-weight:bold}'
             'img{max-width:100%}a{color:#356dac}li{margin:10px 0}</style>')
    html = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>HGTSA 实验结果</title>' + style
            + f'<h1>HGTSA 实验结果 · {scope}</h1><p>{counts}</p>' + table
            + '<p>' + note + '</p><p><a href="experiment_table.csv">下载统计表 CSV</a></p>'
            + '<img src="comparison.svg" alt="LB、Best、Mav 与运行时间对比图">'
            + '<h2>甘特图</h2><ul>'
            + ''.join(f'<li><a href="gantt/{r["instance"]}.svg">{r["instance"]} · Makespan {r["best"]}</a></li>' for r in rows)
            + '</ul><p>所有工序采用相同细边框。原始运行记录、参数与详细统计保存在 runs、manifest.json 和 summary.csv。</p></html>')
    (output / 'index.html').write_text(html, encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
    args = parser.parse_args()
    result = format_results(args.output, args.data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
