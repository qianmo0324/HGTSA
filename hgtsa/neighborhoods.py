"""N8-style sequencing and exact feasible cross-machine insertion.

N8 follows Xie et al., arXiv:2109.02843, section 3.2: N7 endpoint
insertions inside blocks and critical operation insertions outside blocks.
We evaluate full DAGs instead of approximate evaluation. Optional clipping
of non-improving moves (section 3.3) is not used, allowing TS plateau moves.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
import math
import random
import time
from typing import Iterator

from .model import Chromosome, Instance, Schedule, decode, graph, relocation_makespan


def relocate(chromosome: Chromosome, o: int, target: int, position: int) -> Chromosome:
    """Position is an index in the target row AFTER removal of o."""
    rows = [list(row) for row in chromosome]
    source = next(m for m, row in enumerate(rows) if o in row)
    rows[source].remove(o)
    if not 0 <= position <= len(rows[target]):
        raise ValueError('Insertion position out of range')
    rows[target].insert(position, o)
    return tuple(tuple(row) for row in rows)


def _reachable(adj: list[set[int]], root: int) -> set[int]:
    seen: set[int] = set()
    stack = list(adj[root])
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node)
            stack.extend(adj[node] - seen)
    return seen


def insertion_positions(ins: Instance, s: Schedule, o: int, target: int) -> range:
    """Exact cycle-free interval after removing o's machine arcs.

    Reconnect its old machine neighbors, keep its job arcs, and compute
    ancestors/descendants. Insert after every ancestor and before every
    descendant on the target machine. This explicitly enforces the no-path
    condition underlying Mastrolilli & Gambardella's feasibility theorems,
    rather than using the main paper's ambiguous printed r/t inequalities.
    """
    rows = tuple(tuple(x for x in row if x != o) for row in s.chromosome)
    pred, succ = graph(ins, rows)
    ancestors, descendants = _reachable(pred, o), _reachable(succ, o)
    row = rows[target]
    lo = max((i + 1 for i, x in enumerate(row) if x in ancestors), default=0)
    hi = min((i for i, x in enumerate(row) if x in descendants), default=len(row))
    return range(lo, hi + 1)


@dataclass(frozen=True)
class Move:
    instance: Instance
    chromosome: Chromosome
    makespan: int
    operation: int
    source: int
    target: int
    old_position: int
    key: tuple
    reverse_key: tuple
    kind: str

    @cached_property
    def schedule(self) -> Schedule:
        """Materialise timing, tails and graph only when a move is accepted."""
        return decode(self.instance, self.chromosome)


def neighborhood(ins: Instance, s: Schedule, rng: random.Random,
                 deadline: float = math.inf) -> Iterator[Move]:
    """Union of N8 and k-insertion; discard duplicate and cyclic schedules."""
    path = s.critical_path(rng)
    blocks = s.critical_blocks(path)
    seen = {s.chromosome}

    def candidate(o: int, m: int, position: int, kind: str) -> Move | None:
        chrom = relocate(s.chromosome, o, m, position)
        if chrom in seen:
            return None
        seen.add(chrom)
        cost = relocation_makespan(ins, s, chrom, o, m)
        if cost is None:
            return None
        old_row = s.chromosome[s.machine[o]]
        old_pos = s.position[o]
        old_before = old_row[old_pos - 1] if old_pos else -1
        old_after = old_row[old_pos + 1] if old_pos + 1 < len(old_row) else -1
        new_row = chrom[m]
        before = new_row[position - 1] if position else -1
        after = new_row[position + 1] if position + 1 < len(new_row) else -1
        key = ('insert', o, m, before, after)
        reverse_key = ('insert', o, s.machine[o], old_before, old_after)
        if m == s.machine[o] and abs(position - old_pos) == 1:
            # Both "move A after B" and "move B before A" describe the same
            # adjacent swap. Canonical pair/order attributes forbid either inverse.
            other = old_row[position]
            a, b = sorted((o, other))
            new_first = min((a, b), key=lambda x: chrom[m].index(x))
            old_first = min((a, b), key=lambda x: old_row.index(x))
            key = ('swap', m, a, b, new_first)
            reverse_key = ('swap', m, a, b, old_first)
        return Move(ins, chrom, cost, o, s.machine[o], m, old_pos, key, reverse_key, kind)

    for block in blocks:
        m = s.machine[block[0]]
        row = s.chromosome[m]
        first, last = s.position[block[0]], s.position[block[-1]]
        proposals: set[tuple[int, int, str]] = set()
        # N7: any inner operation to a block boundary, and vice versa.
        if len(block) > 1:
            for o in block:
                proposals.add((o, first, 'n8-inner'))
                proposals.add((o, last, 'n8-inner'))
            for pos in range(first, last + 1):
                proposals.add((block[0], pos, 'n8-inner'))
                proposals.add((block[-1], pos, 'n8-inner'))
        # N8: move each critical operation before/after operations outside block.
        for o in block:
            for pos in range(first):
                anchor = row[pos]
                jp = ins.jp[o]
                # Proposition 2: head[anchor]+p[anchor] >= head[JP[o]].
                if jp < 0 or s.end[anchor] >= s.start[jp]:
                    proposals.add((o, pos, 'n8-outer'))
            for pos in range(last + 1, len(row)):
                anchor = row[pos]
                js = ins.js[o]
                # Proposition 1: p[anchor]+tail[anchor] >= tail[JS[o]].
                if js < 0 or s.duration[anchor] + s.tail[anchor] >= s.tail[js]:
                    proposals.add((o, pos, 'n8-outer'))
        for o, pos, kind in sorted(proposals):
            if time.perf_counter() >= deadline:
                return
            move = candidate(o, m, pos, kind)
            if move:
                yield move

    for o in path:
        for target in ins.operations[o].times:
            if target == s.machine[o]:
                continue
            for position in insertion_positions(ins, s, o, target):
                if time.perf_counter() >= deadline:
                    return
                move = candidate(o, target, position, 'k-insertion')
                if move:
                    yield move
