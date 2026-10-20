import random
import unittest

from hgtsa.model import Instance, decode, random_solution, validate_schedule
from hgtsa.neighborhoods import insertion_positions, neighborhood, relocate
from hgtsa.genetics import mutation, path_relinking, transformation_path, roulette
from hgtsa.solver import Config, solve, tabu_search


def flexible():
    return Instance.from_jobs('flex', 2, [
        [{0: 2, 1: 3}, {0: 4, 1: 2}],
        [{0: 3, 1: 1}, {0: 1, 1: 4}],
    ])


class SearchTests(unittest.TestCase):
    def test_adjacent_swap_reverse_cannot_bypass_tabu_via_other_operation(self):
        ins = Instance.from_jobs('tabu', 2, [
            [{1: 5}, {0: 3}], [{1: 4}, {0: 3}], [{1: 5}, {0: 3}],
        ])
        original = decode(ins, ((3, 1, 5), (2, 0, 4)))
        moved = next(m for m in neighborhood(ins, original, random.Random(0))
                     if m.schedule.chromosome == ((3, 5, 1), (2, 0, 4)))
        reverse = [m for m in neighborhood(ins, moved.schedule, random.Random(0))
                   if m.schedule.chromosome == original.chromosome]
        self.assertTrue(reverse)
        self.assertTrue(all(m.key == moved.reverse_key for m in reverse))

    def test_insertion_windows_match_exhaustive_cycle_detection(self):
        ins = flexible()
        for seed in range(12):
            s = decode(ins, random_solution(ins, random.Random(seed)))
            for o in range(4):
                target = 1 - s.machine[o]
                expected = []
                for pos in range(len(s.chromosome[target]) + 1):
                    try:
                        decode(ins, relocate(s.chromosome, o, target, pos))
                        expected.append(pos)
                    except ValueError:
                        pass
                self.assertEqual(list(insertion_positions(ins, s, o, target)), expected)

    def test_neighborhoods_are_feasible_unique_and_tabu_inverse_matches(self):
        ins = flexible()
        s = decode(ins, ((0, 3), (2, 1)))
        moves = list(neighborhood(ins, s, random.Random(2)))
        self.assertTrue(any(m.kind == 'k-insertion' for m in moves))
        self.assertEqual(len({m.schedule.chromosome for m in moves}), len(moves))
        for move in moves:
            validate_schedule(ins, move.schedule)
            back = relocate(move.schedule.chromosome, move.operation, move.source, move.old_position)
            self.assertEqual(back, s.chromosome)
            self.assertNotEqual(move.key, move.reverse_key)

    def test_n8_reaches_outside_critical_blocks(self):
        ins = Instance.from_jobs('outer', 2, [[{0: 1}, {1: 10}, {0: 1}], [{0: 2}], [{0: 2}]])
        s = decode(ins, ((0, 3, 4, 2), (1,)))
        moves = list(neighborhood(ins, s, random.Random(0)))
        self.assertTrue(any(m.kind == 'n8-outer' for m in moves))

    def test_relinking_reaches_guide_and_children_stay_feasible(self):
        ins = flexible()
        for seed in range(15):
            rng = random.Random(seed)
            a, b = random_solution(ins, rng), random_solution(ins, rng)
            path = transformation_path(ins, a, b)
            self.assertEqual(path[-1] if path else a, b)
            for child in path_relinking(ins, a, b):
                validate_schedule(ins, decode(ins, child))
            validate_schedule(ins, decode(ins, mutation(ins, a, rng)))

    def test_seed_reproducibility_and_improvement(self):
        ins = flexible()
        cfg = Config(population_size=3, max_generations=2, small_iter=3, large_iter=5)
        a, b = solve(ins, cfg, 22), solve(ins, cfg, 22)
        self.assertEqual(a.schedule.chromosome, b.schedule.chromosome)
        self.assertLessEqual(a.schedule.makespan, a.initial_best)
        validate_schedule(ins, a.schedule)
        s = decode(ins, ((0, 1, 2, 3), ()))
        improved, _ = tabu_search(ins, s, random.Random(3), 8, 0)
        self.assertLess(improved.makespan, s.makespan)

    def test_time_limit_returns_feasible_and_invalid_config_rejected(self):
        ins = flexible()
        result = solve(ins, Config(time_limit=1e-9), 3)
        self.assertEqual(result.stop_reason, 'time_limit')
        validate_schedule(ins, result.schedule)
        with self.assertRaises(ValueError):
            Config(population_size=0)
        with self.assertRaises(ValueError):
            Config(mutation_rate=1.1)
        with self.assertRaises(ValueError):
            Config(time_limit=float('nan'))

    def test_roulette_minimizes_makespan(self):
        ins = flexible()
        good = decode(ins, ((0, 3), (2, 1)))
        bad = decode(ins, ((0, 1, 2, 3), ()))
        rng = random.Random(4)
        count = sum(roulette([good, bad], rng) is good for _ in range(500))
        self.assertGreater(count, 330)


if __name__ == '__main__':
    unittest.main()
