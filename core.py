# SPDX-License-Identifier: GPL-3.0-or-later
"""Selection resolution and edge-length math, independent of any operator or UI.

All geometry is measured in the space given by a 4x4 matrix ``M``: the object's
``matrix_world`` for world space, or identity for local space. Because ``M`` is
affine, a vertex moved along the edge line in that space stays on the same line in
local space, so the result is exact for rotated, parented and non-uniformly
scaled objects.
"""

from __future__ import annotations

import bmesh
from mathutils import Matrix

#: Edges shorter than this (in the measuring space) have no usable direction.
EPSILON = 1e-9


class EdgeLengthError(Exception):
    """A selection the operator cannot act on. The message is shown to the user."""


def space_matrix(obj, world):
    return obj.matrix_world.copy() if world else Matrix.Identity(4)


def selected_edges(bm):
    return [e for e in bm.edges if e.select]


def active_vertex(bm):
    act = bm.select_history.active
    if isinstance(act, bmesh.types.BMVert) and act.select:
        return act
    return None


def target_edge(bm, edges):
    """The one edge the user means when several are selected, or ``None``.

    1. An active edge (edge select mode).
    2. The edge joining the last two clicked vertices (vertex select mode).
    3. The only selected edge touching the active vertex.
    4. The only selected edge.
    """
    act = bm.select_history.active
    if isinstance(act, bmesh.types.BMEdge) and act.select:
        return act

    if isinstance(act, bmesh.types.BMVert) and act.select:
        history = list(bm.select_history)
        if len(history) >= 2 and isinstance(history[-2], bmesh.types.BMVert):
            prev = history[-2]
            for e in act.link_edges:
                if e.select and e.other_vert(act) is prev:
                    return e
        touching = [e for e in act.link_edges if e.select]
        if len(touching) == 1:
            return touching[0]

    if len(edges) == 1:
        return edges[0]
    return None


def edge_length(M, edge):
    a, b = edge.verts
    return ((M @ b.co) - (M @ a.co)).length


def selection_sides(edge):
    """Split the selection into the vertices that follow each end of ``edge``.

    Returns ``{end_vertex: set_of_vertices}`` for both ends. Raises if the ends
    are joined by selected geometry, since then there is no way to tell which
    side should move.
    """
    a, b = edge.verts
    side_a, side_b = _side(a, edge), _side(b, edge)
    if side_a & side_b:
        raise EdgeLengthError(
            "Both ends of the edge are connected through the selection, "
            "so it is unclear which side should move")
    return {a: side_a, b: side_b}


def resolve_ends(bm, edge, anchor, sides=None):
    """Return ``(fixed, moving)`` vertices, or ``None`` to scale about a point
    (the midpoint, or the 3D cursor for ``CURSOR``).

    ``AUTO``  -- the active vertex stays put. Without one, and with ``sides`` from
                 :func:`selection_sides`, the end that has more selection attached
                 moves (select a wall's end face plus one edge, and the face
                 moves). Otherwise scale from the midpoint.
    ``START`` -- the edge's first vertex stays put, ``END`` -- its second one.
                 This is Blender's internal vertex order: stable for a given
                 edge, but not visible, so the two are offered as a pair to
                 switch between.
    ``CENTER``-- both ends move symmetrically.
    ``CURSOR``-- scale about the 3D cursor, projected onto the edge line.
    """
    if anchor in {'CENTER', 'CURSOR'}:
        return None
    if anchor == 'START':
        return edge.verts[0], edge.verts[1]
    if anchor == 'END':
        return edge.verts[1], edge.verts[0]

    act = active_vertex(bm)
    if act is not None and act in edge.verts:
        return act, edge.other_vert(act)
    if sides is not None:
        loaded = [v for v in edge.verts if len(sides[v]) > 1]
        if len(loaded) == 1:
            return edge.other_vert(loaded[0]), loaded[0]
    return None


def _side(start, blocked_edge):
    """Selected vertices reachable from ``start`` over selected edges, without
    crossing ``blocked_edge``."""
    seen = {start}
    stack = [start]
    while stack:
        v = stack.pop()
        for e in v.link_edges:
            if e is blocked_edge or not e.select:
                continue
            w = e.other_vert(v)
            if w not in seen:
                seen.add(w)
                stack.append(w)
    return seen


def check_disjoint(edges):
    seen = set()
    for e in edges:
        for v in e.verts:
            if v in seen:
                raise EdgeLengthError(
                    "Selected edges share vertices. Make one edge active and "
                    "enable Carry Selection, or select edges that don't touch")
            seen.add(v)


def set_edge_length(M, edge, length, ends, carry=None, pivot=None):
    """Move vertices so ``edge`` measures ``length`` in the space of ``M``.

    ``ends`` comes from :func:`resolve_ends`. ``carry`` comes from
    :func:`selection_sides`; when given, every vertex on a moving side gets the
    same offset as its end, so whole faces translate instead of skewing. Only
    ends that move take their side along; a fixed end's side stays put.

    When ``ends`` is ``None`` the edge scales about ``pivot`` (a point in the space
    of ``M``, projected onto the edge line), or about its midpoint without one.
    This matches Blender's 3D Cursor pivot: snap the cursor to a vertex and that
    vertex stays put.
    """
    Mi = M.inverted_safe()
    a, b = edge.verts
    pa, pb = M @ a.co, M @ b.co
    d = pb - pa
    if d.length < EPSILON:
        raise EdgeLengthError("Edge has zero length, so its direction is undefined")
    u = d.normalized()

    if ends is None:
        if pivot is None:
            c = (pa + pb) * 0.5
        else:
            c = pa + u * (pivot - pa).dot(u)
        s = length / d.length
        deltas = {
            a: (c + (pa - c) * s) - pa,
            b: (c + (pb - c) * s) - pb,
        }
    else:
        fixed, moving = ends
        pf, pm = M @ fixed.co, M @ moving.co
        direction = (pm - pf).normalized()
        deltas = {moving: (pf + direction * length) - pm}

    for end, delta in deltas.items():
        group = carry[end] if carry and end in carry else {end}
        for v in group:
            v.co = Mi @ ((M @ v.co) + delta)
