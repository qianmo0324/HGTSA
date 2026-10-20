"""Roulette selection, path-relinking crossover and critical-path mutations."""
from __future__ import annotations

import math
import random

from .model import Chromosome, Instance, Schedule, assignment, decode, repair
from .neighborhoods import insertion_positions, relocate


def roulette(population: list[Schedule], rng: random.Random) -> Schedule:
    # Reciprocal makespan gives higher probability to smaller objectives.
    return rng.choices(population, weights=[1 / s.makespan for s in population], k=1)[0]


def transformation_path(ins: Instance, start: Chromosome, guide: Chromosome) -> list[Chromosome]:
    """First match assignments, then fix target prefixes with pairwise swaps.

    Raw states may be cyclic. Repair is applied to sampled offspring only,
    leaving the raw transformation path intact so it always reaches guide.
    """
    current = start
    target_machines, _ = assignment(ins, guide)
    machines, _ = assignment(ins, current)
    path = []
    for o, target in enumerate(target_machines):
        if machines[o] != target:
            current = relocate(current, o, target, len(current[target]))
            machines[o] = target
            path.append(current)
    rows = [list(row) for row in current]
    for m, target_row in enumerate(guide):
        for pos, expected in enumerate(target_row):
            if rows[m][pos] != expected:
                other = rows[m].index(expected)
                rows[m][pos], rows[m][other] = rows[m][other], rows[m][pos]
                path.append(tuple(tuple(row) for row in rows))
    return path


def path_relinking(ins: Instance, start: Chromosome, guide: Chromosome) -> list[Chromosome]:
    machines_a, positions_a = assignment(ins, start)
    machines_b, positions_b = assignment(ins, guide)
    sd = sum((a, p) != (b, q) for a, p, b, q in zip(machines_a, positions_a, machines_b, positions_b))
    # The paper does not specify rounding; use ceiling for minimum distances.
    alpha, beta = max(1, math.ceil(sd / 5)), max(2, math.ceil(sd / 10))
    path = transformation_path(ins, start, guide)
    chosen = [repair(ins, path[step - 1]) for step in range(alpha, len(path) - alpha + 1, beta)]
    # Near-identical parents have no interior sampling point.
    if not chosen:
        chosen = [start]
    return list(dict.fromkeys(chosen))


def mutation(ins: Instance, chromosome: Chromosome, rng: random.Random) -> Chromosome:
    s = decode(ins, chromosome)
    path = s.critical_path(rng)
    if rng.randrange(2) == 0:
        pairs = [(a, b) for a, b in zip(path, path[1:])
                 if s.machine[a] == s.machine[b] and s.position[b] == s.position[a] + 1]
        if pairs:
            a, b = rng.choice(pairs)
            rows = [list(row) for row in chromosome]
            m = s.machine[a]
            rows[m][s.position[a]], rows[m][s.position[b]] = b, a
            return repair(ins, tuple(tuple(row) for row in rows))
    else:
        flexible = [o for o in path if len(ins.operations[o].times) > 1]
        if flexible:
            o = rng.choice(flexible)
            target = rng.choice([m for m in ins.operations[o].times if m != s.machine[o]])
            positions = insertion_positions(ins, s, o, target)
            if positions:
                return relocate(chromosome, o, target, rng.choice(positions))
    return chromosome
