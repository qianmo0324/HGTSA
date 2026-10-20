import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree

from hgtsa.reporting import aggregate, write_reports, gantt_svg, serialize_result
from hgtsa.model import decode, validate_schedule, read_fjs
from hgtsa.solver import Config, solve
from run_experiments import run_batch


class ExperimentTests(unittest.TestCase):
    def test_every_gantt_block_has_a_visible_operation_label(self):
        from hgtsa.model import Instance
        # A one-unit operation beside a thousand-unit operation used to lose its label.
        ins = Instance.from_jobs('narrow', 1, [[{0: 1}], [{0: 1000}]])
        s = decode(ins, ((0, 1),))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'gantt.svg'
            gantt_svg(ins, s, p)
            root = ElementTree.parse(p).getroot()
            texts = [e.text for e in root.iter('{http://www.w3.org/2000/svg}text')]
            self.assertIn('J1.1', texts)
            self.assertIn('J2.1', texts)

    def test_metrics_are_computed_from_observations(self):
        runs = [
            {'instance': 'MK01', 'makespan': 40, 'seconds': 2, 'jobs': 10, 'machines': 6},
            {'instance': 'MK01', 'makespan': 44, 'seconds': 4, 'jobs': 10, 'machines': 6},
            {'instance': 'MK10', 'makespan': 193, 'seconds': 8, 'jobs': 20, 'machines': 15},
            {'instance': 'MK10', 'makespan': 196, 'seconds': 10, 'jobs': 20, 'machines': 15},
        ]
        summary = aggregate(runs, expected_runs=10)
        a, b = summary['instances']
        self.assertEqual((a['best'], a['mean'], a['mean_seconds']), (40, 42, 3))
        self.assertEqual(a['best_re_percent'], 0)
        self.assertEqual(a['mean_re_percent'], 5)
        self.assertAlmostEqual(b['best_re_percent'], 400 / 189)
        self.assertAlmostEqual(summary['b_mre_percent'], 200 / 189)
        self.assertAlmostEqual(summary['av_mre_percent'], (5 + 550 / 189) / 2)
        self.assertFalse(summary['complete_br10'])
        self.assertEqual(summary['scope'], ['MK01', 'MK10'])

    def test_batch_output_roundtrip_resume_and_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            data = Path('Job_Data/Brandimarte_Data/Text')
            cfg = Config(population_size=2, small_iter=1, large_iter=1, max_generations=1)
            summary = run_batch(data, ['MK01'], 1, cfg, 7, out)
            self.assertEqual(len(summary['instances']), 1)
            saved = out / 'runs/MK01_01.json'
            original = saved.read_bytes()
            record = json.loads(original)
            ins = read_fjs(data / 'Mk01.fjs')
            chrom = tuple(tuple(row) for row in record['machine_sequences'])
            s = decode(ins, chrom)
            validate_schedule(ins, s)
            self.assertEqual(s.makespan, record['makespan'])
            self.assertEqual(len(record['operations']), len(ins.operations))
            run_batch(data, ['MK01'], 1, cfg, 7, out, resume=True)
            self.assertEqual(saved.read_bytes(), original)
            with self.assertRaises(ValueError):
                run_batch(data, ['MK01'], 1, cfg, 8, out, resume=True)
            with self.assertRaises(ValueError):
                run_batch(data, ['MK01'], 1, cfg, 7, out)
            for p in [out / 'comparison.svg', out / 'gantt/MK01.svg']:
                ElementTree.parse(p)
            self.assertTrue((out / 'summary.csv').is_file())

    def test_modified_data_invalidates_resume(self):
        from plot_results import regenerate
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / 'Mk01.fjs'
            source.write_bytes(Path('Job_Data/Brandimarte_Data/Text/Mk01.fjs').read_bytes())
            cfg = Config(population_size=1, small_iter=1, large_iter=1, max_generations=1)
            run_batch(root, ['MK01'], 1, cfg, 7, root / 'out')
            source.write_bytes(source.read_bytes() + b'\n')
            with self.assertRaises(ValueError):
                run_batch(root, ['MK01'], 1, cfg, 7, root / 'out', resume=True)
            before = (root / 'out/summary.csv').read_bytes()
            with self.assertRaises(ValueError):
                regenerate(root / 'out', root)
            self.assertEqual((root / 'out/summary.csv').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
