"""Two-level tabu search embedded in the paper's genetic algorithm framework."""
from __future__ import annotations

from dataclasses import dataclass
import math
import random
import time
from typing import Callable

from .genetics import mutation, path_relinking, roulette
from .model import Instance, Schedule, decode, random_solution, validate_schedule
from .neighborhoods import neighborhood


@dataclass(frozen=True)
class Config:
    population_size: int = 30
    crossover_rate: float = 0.9
    mutation_rate: float = 0.1
    small_iter: int = 1200
    large_iter: int = 15000
    max_generations: int = 100  # Not specified by the paper; explicit experiment choice.
    time_limit: float | None = None

    def __post_init__(self):
        if any(not isinstance(x, int) or x < 1 for x in
               (self.population_size, self.small_iter, self.large_iter, self.max_generations)):
            raise ValueError('Population, iteration counts and generations must be positive integers')
        if not all(math.isfinite(x) and 0 <= x <= 1 for x in (self.crossover_rate, self.mutation_rate)):
            raise ValueError('Probabilities must be in [0,1]')
        if self.time_limit is not None and (not math.isfinite(self.time_limit) or self.time_limit <= 0):
            raise ValueError('Time limit must be positive and finite')


@dataclass(frozen=True)
class Result:
    schedule: Schedule
    initial_best: int
    elapsed: float
    generations: int
    ts_iterations: int
    stop_reason: str
    history: tuple[dict, ...]


def tabu_search(ins: Instance, initial: Schedule, rng: random.Random, not_improve: int,
                lower_bound: int, deadline: float = math.inf,
                aspiration_bound: int | None = None) -> tuple[Schedule, int]:
    """Best admissible move, inverse-context tabu, strict incumbent aspiration.

    Consecutive non-improvement counter resets only on improvement of TS best.
    Tabu tenure is ceil(15 + jobs / machines). If all moves are tabu, advance
    one tabu clock step instead of silently accepting a forbidden transition.
    """
    current = best = initial
    tenure = math.ceil(15 + len(ins.jobs) / ins.machine_count)
    tabu: dict[tuple, int] = {}
    stalled, iteration = 0, 0
    while stalled < not_improve and best.makespan > lower_bound and time.perf_counter() < deadline:
        chosen = None
        ties = 0
        threshold = min(best.makespan, aspiration_bound if aspiration_bound is not None else best.makespan)
        for move in neighborhood(ins, current, rng, deadline):
            cost = move.makespan
            if tabu.get(move.key, 0) > iteration and cost >= threshold:
                continue
            if chosen is None or cost < chosen.makespan:
                chosen, ties = move, 1
            elif cost == chosen.makespan:
                ties += 1
                if rng.randrange(ties) == 0:
                    chosen = move
        if time.perf_counter() >= deadline:
            # Preserve any fully evaluated improvement before the budget expired.
            if chosen and chosen.makespan < best.makespan:
                best = chosen.schedule
            break
        iteration += 1
        stalled += 1
        if chosen is None:
            if not tabu:
                break
        else:
            current = chosen.schedule
            # At iteration t this blocks the reverse for the next tenure selections.
            tabu[chosen.reverse_key] = iteration + tenure
            if current.makespan < best.makespan:
                best, stalled = current, 0
        tabu = {k: expiry for k, expiry in tabu.items() if expiry > iteration}
    return best, iteration


def solve(ins: Instance, cfg: Config, seed: int, lower_bound: int = 0,
          progress: Callable[[dict], None] | None = None) -> Result:
    began = time.perf_counter()
    deadline = began + cfg.time_limit if cfg.time_limit else math.inf
    rng = random.Random(seed)
    # At least one feasible solution is always returned, even for tiny budgets.
    population = [decode(ins, random_solution(ins, rng))]
    while len(population) < cfg.population_size and time.perf_counter() < deadline:
        if min(s.makespan for s in population) <= lower_bound:
            break
        population.append(decode(ins, random_solution(ins, rng)))
    population.sort(key=lambda s: s.makespan)
    best = population[0]
    initial_best = best.makespan
    history: list[dict] = []
    iterations, generations = 0, 0

    def record(generation, stage):
        item = {'generation': generation, 'stage': stage, 'makespan': best.makespan,
                'seconds': time.perf_counter() - began}
        history.append(item)
        if progress:
            progress(item)

    record(0, 'initial')
    for generation in range(1, cfg.max_generations + 1):
        if best.makespan <= lower_bound or time.perf_counter() >= deadline:
            break
        children = []
        while len(children) < cfg.population_size and time.perf_counter() < deadline:
            father, mother = roulette(population, rng), roulette(population, rng)
            candidates = (path_relinking(ins, father.chromosome, mother.chromosome)
                          if rng.random() < cfg.crossover_rate else [father.chromosome])
            improved = []
            for chrom in candidates:
                if time.perf_counter() >= deadline:
                    break
                if rng.random() < cfg.mutation_rate:
                    chrom = mutation(ins, chrom, rng)
                s, used = tabu_search(ins, decode(ins, chrom), rng, cfg.small_iter,
                                      lower_bound, deadline, best.makespan)
                iterations += used
                improved.append(s)
                if s.makespan < best.makespan:
                    best = s
                    record(generation, 'small_ts')
                if best.makespan <= lower_bound:
                    break
            if improved:
                children.append(min(improved, key=lambda s: s.makespan))
            if best.makespan <= lower_bound:
                break
        for index, child in enumerate(children):
            if best.makespan <= lower_bound or time.perf_counter() >= deadline:
                break
            s, used = tabu_search(ins, child, rng, cfg.large_iter,
                                  lower_bound, deadline, best.makespan)
            iterations += used
            children[index] = s
            if s.makespan < best.makespan:
                best = s
                record(generation, 'large_ts')
        population = sorted(population + children, key=lambda s: s.makespan)[:cfg.population_size]
        generations = generation
    stop = ('lower_bound' if best.makespan <= lower_bound else
            'time_limit' if time.perf_counter() >= deadline else 'max_generations')
    validate_schedule(ins, best)
    return Result(best, initial_best, time.perf_counter() - began, generations,
                  iterations, stop, tuple(history))
