"""Run existing MK01–MK10 data; every completed independent run is checkpointed."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys

from hgtsa import __version__
from hgtsa.model import decode, read_fjs, validate_schedule
from hgtsa.reporting import DEVIATIONS, PAPER, gantt_svg, serialize_result, write_json, write_reports
from hgtsa.solver import Config, solve

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / 'Job_Data/Brandimarte_Data/Text'


def _code_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted((ROOT / 'hgtsa').glob('*.py')) + [Path(__file__).resolve()]:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load_checkpoint(path: Path, ins, name: str, run_index: int, seed: int):
    """Validate saved identity and objective against the exact decoded schedule."""
    r = json.loads(path.read_text(encoding='utf-8'))
    if (r['instance'], r['run_index'], r['seed']) != (name, run_index, seed):
        raise ValueError(f'Invalid run identity in {path}')
    s = decode(ins, tuple(tuple(row) for row in r['machine_sequences']))
    validate_schedule(ins, s)
    if r['makespan'] != s.makespan:
        raise ValueError(f'Inconsistent makespan in {path}')
    return r, s


def run_batch(data_dir: Path, names: list[str], repetitions: int, cfg: Config,
              base_seed: int, output: Path, resume: bool = False) -> dict:
    if repetitions < 1 or not names or len(set(names)) != len(names) or any(n not in PAPER for n in names):
        raise ValueError('Select distinct MK01-MK10 instances and a positive run count')
    files = {p.stem.upper(): p for p in data_dir.glob('*.fjs')}
    missing = set(names) - set(files)
    if missing:
        raise ValueError(f'Dataset files missing: {sorted(missing)} in {data_dir}')
    instances = {name: read_fjs(files[name]) for name in names}
    signature = {
        'schema_version': 1, 'version': __version__, 'code_sha256': _code_digest(),
        'instances': sorted(names), 'repetitions': repetitions,
        'config': asdict(cfg), 'base_seed': base_seed,
        'data_sha256': {name: hashlib.sha256(files[name].read_bytes()).hexdigest() for name in sorted(names)},
    }
    output = Path(output)
    manifest_path = output / 'manifest.json'
    if manifest_path.exists():
        if not resume:
            raise ValueError('Output already contains an experiment; use --resume or another --output')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest['signature'] != signature:
            raise ValueError('Resume refused: configuration, selected data, seeds or source code changed')
    else:
        if output.exists() and any(output.iterdir()):
            raise ValueError('Output directory is not empty and has no matching manifest')
        manifest = {
            'signature': signature, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'python': sys.version, 'platform': platform.platform(), 'deviations': DEVIATIONS,
            'reference': 'Supplied paper, Tables 5 and 6 (historical LB/UB and Java results)',
            'seed_rule': 'base_seed + instance_number * 1000000 + run_index (1-based)',
            'paper_parameter_values_used': cfg.population_size == 30 and cfg.crossover_rate == 0.9
            and cfg.mutation_rate == 0.1 and cfg.small_iter == 1200 and cfg.large_iter == 15000,
        }
        write_json(manifest_path, manifest)
    runs = []
    best_by_name = {}
    # Load and validate completed checkpoints before starting any new work.
    for name in sorted(names):
        ins = instances[name]
        for run_index in range(1, repetitions + 1):
            path = output / 'runs' / f'{name}_{run_index:02d}.json'
            if path.exists():
                expected_seed = base_seed + int(name[2:]) * 1000000 + run_index
                r, s = load_checkpoint(path, ins, name, run_index, expected_seed)
                runs.append(r)
                if name not in best_by_name or s.makespan < best_by_name[name].makespan:
                    best_by_name[name] = s
    completed = {(r['instance'], r['run_index']) for r in runs}
    try:
        for name in sorted(names):
            ins = instances[name]
            for run_index in range(1, repetitions + 1):
                if (name, run_index) in completed:
                    continue
                seed = base_seed + int(name[2:]) * 1000000 + run_index
                print(f'{name} run {run_index}/{repetitions}, seed={seed}', flush=True)

                def progress(item):
                    print(f"  {item['stage']}: best={item['makespan']} at {item['seconds']:.2f}s", flush=True)

                result = solve(ins, cfg, seed, PAPER[name]['lb'], progress)
                record = serialize_result(ins, result, run_index, seed)
                write_json(output / 'runs' / f'{name}_{run_index:02d}.json', record)
                runs.append(record)
                if name not in best_by_name or result.schedule.makespan < best_by_name[name].makespan:
                    best_by_name[name] = result.schedule
                print(f'  done: makespan={result.schedule.makespan}, {result.elapsed:.3f}s, '
                      f'stop={result.stop_reason}', flush=True)
                write_reports(output, runs, repetitions)
    finally:
        for name, s in best_by_name.items():
            gantt_svg(instances[name], s, output / 'gantt' / f'{name}.svg')
        summary = write_reports(output, sorted(runs, key=lambda r: (r['instance'], r['run_index'])), repetitions)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['paper', 'smoke'], default='paper')
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--instances', nargs='+', choices=list(PAPER), default=list(PAPER))
    parser.add_argument('--runs', type=int, help='Independent runs per instance (paper:10; smoke:1)')
    parser.add_argument('--seed', type=int, default=20261019)
    parser.add_argument('--output', type=Path, default=ROOT / 'results' / 'paper')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--population-size', type=int)
    parser.add_argument('--crossover-rate', type=float)
    parser.add_argument('--mutation-rate', type=float)
    parser.add_argument('--small-iter', type=int)
    parser.add_argument('--large-iter', type=int)
    parser.add_argument('--max-generations', type=int)
    parser.add_argument('--time-limit', type=float, help='Seconds per run; no cap in paper profile by default')
    args = parser.parse_args(argv)
    settings = (asdict(Config()) if args.profile == 'paper' else
                asdict(Config(population_size=4, small_iter=5, large_iter=12, max_generations=2, time_limit=3)))
    for key in settings:
        value = getattr(args, key)
        if value is not None:
            settings[key] = value
    repetitions = args.runs if args.runs is not None else (10 if args.profile == 'paper' else 1)
    try:
        cfg = Config(**settings)
        summary = run_batch(args.data_dir, args.instances, repetitions, cfg, args.seed, args.output, args.resume)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    except KeyboardInterrupt:
        print('\nInterrupted. Completed runs saved; repeat the same command with --resume.', file=sys.stderr)
        return 130
    print(f"Results: {args.output.resolve() / 'index.html'}")
    print(f"b-MRE={summary['b_mre_percent']:.4f}%, av-MRE={summary['av_mre_percent']:.4f}%")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
