# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless smoke test.

Run it with Blender's own Python so ``bpy`` and ``bmesh`` are the real ones the
add-on will meet at runtime:

    blender --background --factory-startup --python dev/smoke_test.py

Exits non-zero on any failure, so it drops straight into CI later.
"""

from __future__ import annotations

import os
import sys

import bmesh
import bpy
from mathutils import Euler, Vector

# --- Make the package importable without installing it -----------------------
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.dirname(REPO)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

PACKAGE = os.path.basename(REPO)
addon = __import__(PACKAGE)

FAILURES = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    suffix = f" -- {detail}" if detail else ""
    print(f"[{status}] {label}{suffix}")
    if not condition:
        FAILURES.append(label)


def close(a, b, tol=1e-4):
    return abs(a - b) < tol


def close_vec(a, b, tol=1e-4):
    return (Vector(a) - Vector(b)).length < tol


def reset():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_cube(name, scale=(1, 1, 1), rotation=(0, 0, 0), location=(0, 0, 0)):
    """A cube with local vertices at +/-1, under an arbitrary transform."""
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=location)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = scale
    ob.rotation_euler = Euler(rotation, 'XYZ')
    bpy.context.view_layer.update()
    return ob


def edit(*objs):
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode='EDIT')


def vert(bm, co):
    bm.verts.ensure_lookup_table()
    return min(bm.verts, key=lambda v: (v.co - Vector(co)).length)


def edge(bm, a, b):
    va, vb = vert(bm, a), vert(bm, b)
    for e in va.link_edges:
        if e.other_vert(va) is vb:
            return e
    raise AssertionError(f"no edge {a} -> {b}")


def select(ob, history=(), extra_faces=()):
    """Select ``history`` elements in order (last is active), plus whole faces."""
    bm = bmesh.from_edit_mesh(ob.data)
    for seq in (bm.verts, bm.edges, bm.faces):
        for elem in seq:
            elem.select = False
    bm.select_history.clear()
    for f in extra_faces:
        f.select_set(True)
    for elem in history:
        elem.select_set(True)
        bm.select_history.add(elem)
    # Clicking two vertices in the viewport also selects the edge between them.
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    return bm


def world_len(ob, e):
    M = ob.matrix_world
    return ((M @ e.verts[1].co) - (M @ e.verts[0].co)).length


def run(**kwargs):
    return bpy.ops.mesh.precise_edge_length_set('EXEC_DEFAULT', **kwargs)


A, B = (-1, -1, -1), (1, -1, -1)   # an edge along local X


def test_world_space_active_anchor():
    reset()
    ob = make_cube("Rotated", scale=(3, 1, 0.5), rotation=(0.3, 0.5, 0.7))
    edit(ob)
    bm = bmesh.from_edit_mesh(ob.data)
    va, vb = vert(bm, A), vert(bm, B)
    bm = select(ob, history=(vb, va))          # va clicked last: it is the anchor
    anchor_world = ob.matrix_world @ va.co.copy()

    result = run(length=2.5)
    bm = bmesh.from_edit_mesh(ob.data)
    va, vb = vert(bm, A), vert(bm, B)
    e = edge(bm, A, B)
    check("world: operator finished", result == {'FINISHED'}, str(result))
    check("world: length is 2.5 under rotation + non-uniform scale",
          close(world_len(ob, e), 2.5), f"{world_len(ob, e):.6f}")
    check("world: active vertex stayed put", close_vec(ob.matrix_world @ va.co, anchor_world))
    check("world: moved vertex stays on the edge line",
          close(vb.co.y, -1) and close(vb.co.z, -1), str(tuple(vb.co)))


def test_local_space():
    reset()
    ob = make_cube("Local", scale=(3, 1, 1))
    edit(ob)
    bm = bmesh.from_edit_mesh(ob.data)
    select(ob, history=(vert(bm, B), vert(bm, A)))
    run(length=0.5, world=False)
    bm = bmesh.from_edit_mesh(ob.data)
    e = edge(bm, A, B)
    check("local: local length is 0.5", close(e.calc_length(), 0.5), f"{e.calc_length():.6f}")


def test_midpoint_start_end():
    reset()
    ob = make_cube("Mid", scale=(2, 1, 1))
    edit(ob)
    bm = bmesh.from_edit_mesh(ob.data)
    select(ob, history=(edge(bm, A, B),))      # active edge, no active vertex
    run(length=1.0)
    bm = bmesh.from_edit_mesh(ob.data)
    e = edge(bm, (-0.25, -1, -1), (0.25, -1, -1))
    mid = (e.verts[0].co + e.verts[1].co) / 2
    check("auto, no active vertex: midpoint kept", close_vec(mid, (0, -1, -1)), str(tuple(mid)))
    check("auto, no active vertex: world length 1.0", close(world_len(ob, e), 1.0))

    # Start and End are opposite ends of the same edge, whatever the active vertex.
    for anchor in ('START', 'END'):
        reset()
        ob = make_cube(anchor)
        edit(ob)
        bm = bmesh.from_edit_mesh(ob.data)
        e = edge(bm, A, B)
        keep = e.verts[0 if anchor == 'START' else 1].co.copy()
        select(ob, history=(vert(bm, B), vert(bm, A)))   # A active, but ignored here
        run(length=3.0, anchor=anchor)
        bm = bmesh.from_edit_mesh(ob.data)
        kept = [v for v in bm.verts if v.select and close_vec(v.co, keep)]
        lens = [world_len(ob, x) for x in bm.edges if x.select]
        check(f"{anchor.lower()}: its vertex stays put", len(kept) == 1, str(tuple(keep)))
        check(f"{anchor.lower()}: length is 3.0", close(lens[0], 3.0), f"{lens[0]:.6f}")


def test_carry_selection():
    reset()
    ob = make_cube("Wall", scale=(4, 0.1, 1.5), rotation=(0, 0, 0.6))
    edit(ob)
    bm = bmesh.from_edit_mesh(ob.data)
    end_face = next(f for f in bm.faces if f.normal.x > 0.9)
    bm = select(ob, history=(edge(bm, A, B),), extra_faces=(end_face,))

    run(length=10.0, carry=True)
    bm = bmesh.from_edit_mesh(ob.data)
    e = edge(bm, A, B)
    xs = sorted(round(v.co.x, 5) for v in bm.verts)
    check("carry: length is 10.0", close(world_len(ob, e), 10.0), f"{world_len(ob, e):.6f}")
    check("carry: start end untouched, whole end face moved together",
          xs[:4] == [-1.0] * 4 and len(set(xs[4:])) == 1, str(xs))
    check("carry: end face moved, not the bare start vertex", xs[4] > 1.0, str(xs[4]))


def test_shared_vertices_rejected():
    reset()
    ob = make_cube("Shared")
    edit(ob)
    bm = bmesh.from_edit_mesh(ob.data)
    e1, e2 = edge(bm, A, B), edge(bm, A, (-1, 1, -1))
    select(ob, history=(e1, e2))
    before = [v.co.copy() for v in bmesh.from_edit_mesh(ob.data).verts]
    try:
        result = run(length=5.0)
    except RuntimeError as exc:                 # ERROR reports raise in background
        result = {'CANCELLED'}
        print(f"       (reported: {str(exc).strip()})")
    after = [v.co.copy() for v in bmesh.from_edit_mesh(ob.data).verts]
    check("shared vertices: cancelled", result == {'CANCELLED'}, str(result))
    check("shared vertices: mesh untouched",
          all(close_vec(a, b) for a, b in zip(before, after)))


def test_multi_edge_and_multi_object():
    reset()
    a = make_cube("ObjA", scale=(2, 1, 1))
    bpy.ops.object.mode_set(mode='OBJECT')
    b = make_cube("ObjB", scale=(1, 3, 1), location=(5, 0, 0))
    edit(a, b)
    for ob in (a, b):
        bm = bmesh.from_edit_mesh(ob.data)
        # Two parallel edges along X that share no vertices.
        select(ob, history=(edge(bm, A, B), edge(bm, (-1, 1, 1), (1, 1, 1))))
    run(length=1.5, anchor='CENTER')
    for ob in (a, b):
        bm = bmesh.from_edit_mesh(ob.data)
        lens = [world_len(ob, e) for e in bm.edges if e.select]
        check(f"multi: {ob.name} both edges at 1.5", all(close(x, 1.5) for x in lens),
              ", ".join(f"{x:.4f}" for x in lens))


def test_cursor_anchor():
    reset()
    ob = make_cube("Cursor", scale=(2, 1, 1), rotation=(0, 0, 0.4))
    edit(ob)
    bm = bmesh.from_edit_mesh(ob.data)
    select(ob, history=(edge(bm, A, B),))
    # Cursor snapped onto vertex B: B must stay put, A moves.
    b_world = ob.matrix_world @ vert(bm, B).co
    bpy.context.scene.cursor.location = b_world
    run(length=1.0, anchor='CURSOR')
    bm = bmesh.from_edit_mesh(ob.data)
    e = edge(bm, (0.5, -1, -1), B)
    check("cursor on a vertex: that vertex stays put",
          close_vec(ob.matrix_world @ vert(bm, B).co, b_world))
    check("cursor on a vertex: world length 1.0", close(world_len(ob, e), 1.0),
          f"{world_len(ob, e):.6f}")

    # Cursor off the edge line: its projection onto the line is the fixed point.
    reset()
    ob = make_cube("CursorOff")
    edit(ob)
    bm = bmesh.from_edit_mesh(ob.data)
    select(ob, history=(edge(bm, A, B),))
    bpy.context.scene.cursor.location = (0.5, 3.0, 7.0)   # projects to x = 0.5
    run(length=4.0, anchor='CURSOR')
    bm = bmesh.from_edit_mesh(ob.data)
    xs = sorted(v.co.x for v in bm.verts if v.select)
    check("cursor off the line: scaled about its projection",
          close(xs[0], 0.5 - 1.5 * 2) and close(xs[1], 0.5 + 0.5 * 2), str(xs))


def pick_edge(ob, a, b):
    """Select one edge and keep no BMesh reference afterwards, like the real UI.

    The panel must cope with the edit-mode BMesh being freed between redraws; a test
    that holds ``bm`` itself would hide that.
    """
    bm = bmesh.from_edit_mesh(ob.data)
    select(ob, history=(edge(bm, a, b),))


def test_panel_field():
    reset()
    ob = make_cube("Panel", scale=(2.5, 1, 1))
    edit(ob)
    pick_edge(ob, A, B)
    settings = bpy.context.window_manager.precise_edge_length
    settings.world = True
    check("panel: shows world length", close(settings.length, 5.0), f"{settings.length:.4f}")
    settings.world = False
    check("panel: shows local length", close(settings.length, 2.0), f"{settings.length:.4f}")
    settings.world = True

    settings.length = 3.0
    check("panel: keeps a typed value", close(settings.length, 3.0), f"{settings.length:.4f}")
    run(length=settings.length)
    check("panel: shows the new length after Set", close(settings.length, 3.0),
          f"{settings.length:.4f}")

    settings.length = 7.0
    pick_edge(ob, (-1, 1, 1), (1, 1, 1))
    check("panel: a new selection drops the typed value", close(settings.length, 5.0),
          f"{settings.length:.4f}")


def test_scale_notes():
    notes_of = sys.modules[PACKAGE + ".ui"].scale_notes

    def icons(ob, world=True):
        bpy.context.view_layer.update()
        return [icon for icon, _text in notes_of(ob, world)]

    reset()
    ob = make_cube("Notes")
    check("notes: none at scale 1", icons(ob) == [], str(icons(ob)))
    ob.scale = (2, 2, 2)
    check("notes: uniform scale is noted too", icons(ob)[:1] == ['INFO'], str(icons(ob)))
    ob.scale = (2.5, 1, 1)
    check("notes: info in World Space", icons(ob)[:1] == ['INFO'], str(icons(ob)))
    check("notes: warning in Local Space", icons(ob, world=False)[:1] == ['ERROR'],
          str(icons(ob, world=False)))
    ob.scale = (-1, 1, 1)
    check("notes: mirror-only scale warns once", icons(ob) == ['ERROR'], str(icons(ob)))
    ob.scale = (1, 0, 1)
    check("notes: zero scale warns", icons(ob)[:1] == ['ERROR'], str(icons(ob)))

    ob.scale = (1, 1, 1)
    bpy.ops.object.empty_add()
    parent = bpy.context.active_object
    parent.scale = (3, 3, 3)
    ob.parent = parent
    check("notes: scale inherited from a parent counts", icons(ob)[:1] == ['INFO'],
          str(icons(ob)))


def main():
    print(f"Blender {bpy.app.version_string}")
    addon.register()
    try:
        for test in (test_world_space_active_anchor, test_local_space,
                     test_midpoint_start_end, test_carry_selection,
                     test_shared_vertices_rejected, test_multi_edge_and_multi_object,
                     test_cursor_anchor, test_panel_field, test_scale_notes):
            try:
                test()
            except Exception as exc:  # noqa: BLE001 -- report and keep going
                import traceback
                traceback.print_exc()
                check(f"{test.__name__} raised", False, repr(exc))
    finally:
        reset()
        addon.unregister()

    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)


main()
