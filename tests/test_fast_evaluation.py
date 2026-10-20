"""Exact move costs must agree with the independent full DAG decoder."""
import random
import unittest
from pathlib import Path

from hgtsa import model
from hgtsa.neighborhoods import relocate


class FastEvaluationTests(unittest.TestCase):
    def test_move_cost_handles_duplicate_job_machine_arcs_and_cycles(self):
        evaluate = getattr(model, 'relocation_makespan', None)
        self.assertIsNotNone(evaluate, 'Exact lightweight move evaluator is missing')
        ins = model.Instance.from_jobs('tiny', 2, [
            [{0: 2, 1: 3}, {0: 4, 1: 3}],
            [{0: 2, 1: 2}, {0: 1, 1: 3}],
        ])
        s = model.decode(ins, ((0, 1, 2, 3), ()))
        self.assertEqual(evaluate(ins, s, s.chromosome, 0, 0), 9)
        cyclic = ((1, 0, 2, 3), ())
        self.assertIsNone(evaluate(ins, s, cyclic, 0, 0))

    def test_all_relocations_match_full_decoder_on_all_brandimarte_instances(self):
        evaluate = getattr(model, 'relocation_makespan', None)
        self.assertIsNotNone(evaluate, 'Exact lightweight move evaluator is missing')
        for path in sorted(Path('Job_Data/Brandimarte_Data/Text').glob('*.fjs')):
            ins = model.read_fjs(path)
            for seed in (7, 19):
                s = model.decode(ins, model.random_solution(ins, random.Random(seed)))
                # Sample both critical and noncritical operations; enumerate every position.
                operations = set(s.critical_path()) | set(range(0, len(ins.operations), 17))
                for o in sorted(operations):
                    for m in ins.operations[o].times:
                        length = len(s.chromosome[m]) - (m == s.machine[o])
                        for pos in range(length + 1):
                            chrom = relocate(s.chromosome, o, m, pos)
                            try:
                                expected = model.decode(ins, chrom).makespan
                            except ValueError:
                                expected = None
                            with self.subTest(instance=ins.name, seed=seed, op=o, machine=m, pos=pos):
                                self.assertEqual(evaluate(ins, s, chrom, o, m), expected)
