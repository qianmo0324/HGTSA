"""Rebuild CSV, statistics and SVG figures from saved independent runs."""
import argparse
import hashlib
import json
from pathlib import Path

from hgtsa.model import decode, read_fjs, validate_schedule
from hgtsa.reporting import gantt_svg, write_reports
from run_experiments import DEFAULT_DATA, load_checkpoint


def regenerate(output: Path, data_dir: Path = DEFAULT_DATA):
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    signature = manifest['signature']
    files = {f.stem.upper(): f for f in data_dir.glob('*.fjs')}
    runs, best_schedules, instances = [], {}, {}
    # Validate ALL input before rewriting any figure or report. Rendering with
    # fixed plotting code is allowed, but data/seed/cost mismatches are not.
    for name in signature['instances']:
        if name not in files or hashlib.sha256(files[name].read_bytes()).hexdigest() != signature['data_sha256'][name]:
            raise ValueError(f'Dataset mismatch for {name}; reports were not rewritten')
        ins = instances[name] = read_fjs(files[name])
        for index in range(1, signature['repetitions'] + 1):
            path = output / 'runs' / f'{name}_{index:02d}.json'
            if path.exists():
                seed = signature['base_seed'] + int(name[2:]) * 1000000 + index
                record, schedule = load_checkpoint(path, ins, name, index, seed)
                runs.append(record)
                if name not in best_schedules or schedule.makespan < best_schedules[name].makespan:
                    best_schedules[name] = schedule
    if not runs:
        raise ValueError('No completed runs')
    for name, s in best_schedules.items():
        gantt_svg(instances[name], s, output / 'gantt' / f'{name}.svg')
    return write_reports(output, runs, signature['repetitions'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
    args = p.parse_args()
    try:
        regenerate(args.output, args.data_dir)
    except (ValueError, OSError, KeyError) as exc:
        p.error(str(exc))
    print(args.output.resolve() / 'index.html')


if __name__ == '__main__':
    main()
