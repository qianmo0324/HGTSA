"""FJSP data, machine-sequence chromosomes and exact disjunctive DAG evaluation.

Internal IDs are zero based. Each operation keeps its (job, index) identity:
job numbers alone are ambiguous when a job visits the same machine twice.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
import random

Chromosome = tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class Operation:
    job: int
    index: int
    times: dict[int, int]


@dataclass(frozen=True)
class Instance:
    name: str
    machine_count: int
    jobs: tuple[tuple[int, ...], ...]
    operations: tuple[Operation, ...]
    jp: tuple[int, ...]
    js: tuple[int, ...]

    @classmethod
    def from_jobs(cls, name: str, machines: int, jobs: list) -> Instance:
        if machines < 1 or not jobs or any(not job for job in jobs):
            raise ValueError('Positive machine count and nonempty jobs required')
        ops, routes, jp, js = [], [], [], []
        for j, job in enumerate(jobs):
            route = []
            for k, times in enumerate(job):
                if not times or any(m < 0 or m >= machines or p <= 0 for m, p in times.items()):
                    raise ValueError(f'Invalid processing alternatives for job {j + 1}, operation {k + 1}')
                o = len(ops)
                ops.append(Operation(j, k, dict(times)))
                route.append(o)
                jp.append(o - 1 if k else -1)
                js.append(o + 1 if k + 1 < len(job) else -1)
            routes.append(tuple(route))
        return cls(name, machines, tuple(routes), tuple(ops), tuple(jp), tuple(js))


def read_fjs(path: str | Path) -> Instance:
    """Read the IDSIA format; optional third header field is deliberately ignored."""
    path = Path(path)
    try:
        rows = [line.split() for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        nj, nm = map(int, rows[0][:2])
        if nj < 1 or len(rows) != nj + 1:
            raise ValueError('Job count does not match number of rows')
        jobs = []
        for row in rows[1:]:
            values = list(map(int, row))
            count, pos, job = values[0], 1, []
            if count < 1:
                raise ValueError('Empty job')
            for _ in range(count):
                k = values[pos]
                pos += 1
                if k < 1 or pos + 2 * k > len(values):
                    raise ValueError('Invalid alternative count')
                alternatives = {}
                for _ in range(k):
                    machine, duration = values[pos:pos + 2]
                    pos += 2
                    if machine - 1 in alternatives:
                        raise ValueError('Duplicate machine alternative')
                    alternatives[machine - 1] = duration
                job.append(alternatives)
            if pos != len(values):
                raise ValueError('Unexpected tokens after job')
            jobs.append(job)
        return Instance.from_jobs(path.stem.upper(), nm, jobs)
    except (IndexError, TypeError, ValueError) as exc:
        raise ValueError(f'{path}: invalid FJS data: {exc}') from exc


def assignment(ins: Instance, chromosome: Chromosome) -> tuple[list[int], list[int]]:
    n = len(ins.operations)
    if len(chromosome) != ins.machine_count:
        raise ValueError('Chromosome must have one sequence per machine')
    machines, positions = [-1] * n, [-1] * n
    for m, row in enumerate(chromosome):
        for i, o in enumerate(row):
            if not isinstance(o, int) or o < 0 or o >= n or machines[o] != -1:
                raise ValueError('Unknown or duplicate operation')
            if m not in ins.operations[o].times:
                raise ValueError('Operation assigned to ineligible machine')
            machines[o], positions[o] = m, i
    if -1 in machines:
        raise ValueError('Missing operations')
    return machines, positions


def graph(ins: Instance, chromosome: Chromosome) -> tuple[list[set[int]], list[set[int]]]:
    """Directed job arcs and adjacent oriented machine arcs (transitive reduction)."""
    n = len(ins.operations)
    pred, succ = [set() for _ in range(n)], [set() for _ in range(n)]
    for o, next_o in enumerate(ins.js):
        if next_o >= 0:
            succ[o].add(next_o)
            pred[next_o].add(o)
    for row in chromosome:
        for a, b in zip(row, row[1:]):
            succ[a].add(b)
            pred[b].add(a)
    return pred, succ


@dataclass(frozen=True)
class Schedule:
    chromosome: Chromosome
    machine: tuple[int, ...]
    position: tuple[int, ...]
    duration: tuple[int, ...]
    start: tuple[int, ...]
    end: tuple[int, ...]
    tail: tuple[int, ...]  # longest remaining processing time EXCLUDING this operation
    makespan: int
    pred: tuple[tuple[int, ...], ...]
    succ: tuple[tuple[int, ...], ...]

    def critical_path(self, rng: random.Random | None = None) -> tuple[int, ...]:
        def pick(items):
            return rng.choice(items) if rng else min(items)
        o = pick([i for i, end in enumerate(self.end) if end == self.makespan])
        path = [o]
        while self.pred[o]:
            tight = [p for p in self.pred[o] if self.end[p] == self.start[o]]
            if not tight:
                raise ValueError('Broken longest path')
            o = pick(tight)
            path.append(o)
        return tuple(reversed(path))

    def critical_blocks(self, path: tuple[int, ...] | None = None) -> tuple[tuple[int, ...], ...]:
        path = self.critical_path() if path is None else path
        blocks: list[list[int]] = []
        for o in path:
            if (blocks and self.machine[blocks[-1][-1]] == self.machine[o]
                    and self.position[o] == self.position[blocks[-1][-1]] + 1):
                blocks[-1].append(o)
            else:
                blocks.append([o])
        return tuple(tuple(b) for b in blocks)


def decode(ins: Instance, chromosome: Chromosome) -> Schedule:
    """Earliest start times via Kahn + weighted longest path. Cycles are errors."""
    machines, positions = assignment(ins, chromosome)
    pred, succ = graph(ins, chromosome)
    n = len(ins.operations)
    durations = [ins.operations[o].times[machines[o]] for o in range(n)]
    degree = [len(p) for p in pred]
    queue = deque(o for o in range(n) if not degree[o])
    starts, order = [0] * n, []
    while queue:
        o = queue.popleft()
        order.append(o)
        end = starts[o] + durations[o]
        for nxt in succ[o]:
            starts[nxt] = max(starts[nxt], end)
            degree[nxt] -= 1
            if not degree[nxt]:
                queue.append(nxt)
    if len(order) != n:
        raise ValueError('Cyclic machine/job order: infeasible schedule')
    tails = [0] * n
    for o in reversed(order):
        tails[o] = max((durations[s] + tails[s] for s in succ[o]), default=0)
    ends = [s + p for s, p in zip(starts, durations)]
    return Schedule(tuple(tuple(r) for r in chromosome), tuple(machines), tuple(positions),
                    tuple(durations), tuple(starts), tuple(ends), tuple(tails), max(ends),
                    tuple(tuple(sorted(p)) for p in pred), tuple(tuple(sorted(s)) for s in succ))


def repair(ins: Instance, chromosome: Chromosome) -> Chromosome:
    """Priority topological repair; NOT claimed as a verified Ren & Wang replica.

    Keep assignments. Dispatch a ready machine head when possible; on deadlock
    promote the first job-ready operation nearest its machine head. Each step
    dispatches a job-ready operation, so termination and acyclicity follow.
    """
    assignment(ins, chromosome)
    try:
        decode(ins, chromosome)
        return chromosome
    except ValueError:
        pass
    remaining = [list(row) for row in chromosome]
    result = [[] for _ in remaining]
    done: set[int] = set()
    for _ in ins.operations:
        ready = []
        for m, row in enumerate(remaining):
            for pos, o in enumerate(row):
                if ins.jp[o] < 0 or ins.jp[o] in done:
                    ready.append((pos, m, o))
                    break
        _, m, o = min(ready)
        remaining[m].remove(o)
        result[m].append(o)
        done.add(o)
    return tuple(tuple(row) for row in result)


def random_solution(ins: Instance, rng: random.Random) -> Chromosome:
    """Random ready-operation dispatch, random eligible machine, earliest idle gap."""
    next_index = [0] * len(ins.jobs)
    job_end = [0] * len(ins.jobs)
    timelines: list[list[tuple[int, int, int]]] = [[] for _ in range(ins.machine_count)]
    active = list(range(len(ins.jobs)))
    while active:
        j = rng.choice(active)
        o = ins.jobs[j][next_index[j]]
        m = rng.choice(list(ins.operations[o].times))
        p = ins.operations[o].times[m]
        start = job_end[j]
        row = timelines[m]
        at = 0
        for at, (s, e, _) in enumerate(row):
            if start + p <= s:
                break
            start = max(start, e)
        else:
            at = len(row)
        row.insert(at, (start, start + p, o))
        job_end[j] = start + p
        next_index[j] += 1
        if next_index[j] == len(ins.jobs[j]):
            active.remove(j)
    return tuple(tuple(o for _, _, o in row) for row in timelines)


def validate_schedule(ins: Instance, s: Schedule) -> None:
    """Independent feasibility check of all saved operation intervals."""
    assignment(ins, s.chromosome)
    for o, op in enumerate(ins.operations):
        if s.start[o] < 0 or s.end[o] - s.start[o] != op.times[s.machine[o]]:
            raise ValueError('Incorrect operation interval')
        if ins.jp[o] >= 0 and s.end[ins.jp[o]] > s.start[o]:
            raise ValueError('Job precedence violated')
    for m, row in enumerate(s.chromosome):
        if any(s.machine[o] != m for o in row):
            raise ValueError('Machine assignment mismatch')
        if any(s.end[a] > s.start[b] for a, b in zip(row, row[1:])):
            raise ValueError('Machine overlap')
    if max(s.end) != s.makespan:
        raise ValueError('Incorrect makespan')
