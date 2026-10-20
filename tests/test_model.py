import random
import unittest
from pathlib import Path

from hgtsa.model import Instance, decode, read_fjs, repair, random_solution, validate_schedule


def tiny():
    # Two jobs: M1(2)->M2(3), M2(2)->M1(1).
    return Instance.from_jobs('tiny', 2, [[{0: 2}, {1: 3}], [{1: 2}, {0: 1}]])


class ModelTests(unittest.TestCase):
    def test_hand_calculated_times_and_critical_path(self):
        ins = tiny()
        s = decode(ins, ((0, 3), (2, 1)))
        self.assertEqual(s.makespan, 5)
        self.assertEqual(s.start, (0, 2, 0, 2))
        self.assertEqual(s.critical_path(), (0, 1))
        validate_schedule(ins, s)

    def test_cycle_rejected_and_repair_preserves_assignments(self):
        ins = tiny()
        bad = ((3, 0), (1, 2))
        with self.assertRaises(ValueError):
            decode(ins, bad)
        fixed = repair(ins, bad)
        validate_schedule(ins, decode(ins, fixed))
        self.assertEqual(set(fixed[0]), {0, 3})
        self.assertEqual(set(fixed[1]), {1, 2})
        feasible = ((0, 3), (2, 1))
        self.assertEqual(repair(ins, feasible), feasible)

    def test_invalid_chromosomes_rejected(self):
        for bad in (((0, 0, 3), (2, 1)), ((0,), (2, 1)), ((0, 1), (2, 3))):
            with self.assertRaises(ValueError):
                decode(tiny(), bad)

    def test_brandimarte_data_and_random_schedules(self):
        files = sorted(Path('Job_Data/Brandimarte_Data/Text').glob('*.fjs'))
        self.assertEqual(len(files), 10)
        sizes = [(10, 6), (10, 6), (15, 8), (15, 8), (15, 4),
                 (10, 15), (20, 5), (20, 10), (20, 10), (20, 15)]
        for path, size in zip(files, sizes):
            ins = read_fjs(path)
            self.assertEqual((len(ins.jobs), ins.machine_count), size)
            validate_schedule(ins, decode(ins, random_solution(ins, random.Random(17))))

    def test_malformed_input(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'bad.fjs'
            for content in ('1 2\n1 1 3 4\n', '1 2\n1 1 1 0\n', '2 2\n1 1 1 3\n'):
                p.write_text(content)
                with self.assertRaises(ValueError):
                    read_fjs(p)


if __name__ == '__main__':
    unittest.main()
