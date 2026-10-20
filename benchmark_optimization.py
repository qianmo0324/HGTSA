"""Compare exact search behavior and time against a saved pre-change package.

Example: python benchmark_optimization.py --reference-dir tmp/optimization_baseline
The reference directory must contain hgtsa/. Neither implementation uses a time
limit: equal work, objective, chromosome, iteration count and improvement history
are checked before reporting speedups. This is a short diagnostic, not paper DOE.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import random
import statistics
import sys
import time

from hgtsa.model import decode, random_solution, read_fjs, validate_schedule
from hgtsa.neighborhoods import neighborhood
from hgtsa.solver import Config, solve


def load_reference(directory):
    package = Path(directory).resolve() / 'hgtsa'
    spec = importlib.util.spec_from_file_location(
        '_hgtsa_reference', package / '__init__.py',
        submodule_search_locations=[str(package)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    from _hgtsa_reference.solver import solve as reference_solve, Config as ReferenceConfig
    from _hgtsa_reference.neighborhoods import neighborhood as reference_neighborhood
    return reference_solve, ReferenceConfig, reference_neighborhood


def search_signature(result):
    return (result.schedule, result.initial_best, result.generations,
            result.ts_iterations, result.stop_reason,
            [(h['generation'], h['stage'], h['makespan']) for h in result.history])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-dir', type=Path, required=True)
    parser.add_argument('--instances', nargs='+', default=[f'MK{i:02d}' for i in range(1, 11)])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', type=Path, default=Path('results/optimization/benchmark.json'))
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    reference_solve, ReferenceConfig, reference_neighborhood = load_reference(args.reference_dir)
    cfg = Config(population_size=2, small_iter=2, large_iter=3, max_generations=1)
    results = []
    for name in args.instances:
        ins = read_fjs(Path('Job_Data/Brandimarte_Data/Text') / f'{name.title()}.fjs')
        initial = decode(ins, random_solution(ins, random.Random(17)))
        neighbor_times = {'before': [], 'after': []}
        expected = None
        for repeat in range(args.repeats):
            # Alternate order to reduce systematic warmup/load bias.
            order = [('before', reference_neighborhood), ('after', neighborhood)]
            for label, function in order[::1 if repeat % 2 == 0 else -1]:
                began = time.perf_counter()
                moves = list(function(ins, initial, random.Random(23)))
                costs = [(m.schedule.chromosome, m.schedule.makespan, m.key, m.reverse_key, m.kind)
                         if label == 'before' else
                         (m.chromosome, m.makespan, m.key, m.reverse_key, m.kind) for m in moves]
                neighbor_times[label].append(time.perf_counter() - began)
                if expected is None:
                    expected = costs
                elif costs != expected:
                    raise AssertionError(f'{name}: neighborhood changed')
        runs = {}
        for label, function, config in (
                ('before', reference_solve, ReferenceConfig(**asdict(cfg))),
                ('after', solve, cfg)):
            result = function(ins, config, seed=314159, lower_bound=0)
            validate_schedule(ins, result.schedule)
            runs[label] = result
        # Dataclass equality is class-sensitive across separately loaded packages.
        before, after = runs['before'], runs['after']
        a, b = search_signature(before), search_signature(after)
        if asdict(a[0]) != asdict(b[0]) or a[1:] != b[1:]:
            raise AssertionError(f'{name}: fixed-seed search changed')
        row = {
            'instance': name, 'neighbors': len(expected),
            'neighborhood_before_seconds': statistics.median(neighbor_times['before']),
            'neighborhood_after_seconds': statistics.median(neighbor_times['after']),
            'solve_before_seconds': before.elapsed, 'solve_after_seconds': after.elapsed,
            'solve_speedup': before.elapsed / after.elapsed,
            'makespan': after.schedule.makespan, 'ts_iterations': after.ts_iterations,
            'same_neighborhood_and_search': True,
        }
        results.append(row)
        print(f"{name}: {before.elapsed:.3f}s -> {after.elapsed:.3f}s "
              f"({row['solve_speedup']:.2f}x), identical search", flush=True)
    def digest(directory):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(Path(directory).glob('*.py'))}
    output = {'python': sys.version, 'platform': platform.platform(),
              'config': asdict(cfg), 'seed': 314159, 'repeats_neighborhood': args.repeats,
              'note': 'Short fixed-work diagnostic; not the 10-run paper protocol. Solve timed once per version.',
              'baseline_sha256': digest(args.reference_dir / 'hgtsa'),
              'optimized_sha256': digest(Path('hgtsa')), 'instances': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(f'Saved {args.output.resolve()}')


if __name__ == '__main__':
    main()
