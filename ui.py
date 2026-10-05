# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panel and menu entries.

The panel's Length field is a ``FloatProperty`` with ``subtype='DISTANCE'``, so
Blender formats and parses it exactly like the operator's input: same unit system,
same ``scale_length``.

The field follows the selection. Its getter returns the selected edge's live length,
unless the user has typed a value for that same edge, in its current shape, and not
yet applied it. The typed value is kept in module state rather than in an ID
property, because panels may not write ID data while drawing.
"""

from __future__ import annotations

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty

from . import core
from .operators import ANCHOR_ITEMS, MESH_OT_precise_edge_length_set

#: The last typed value and the edge it was typed for. See ``_edge_key``.
_typed = {"key": None, "value": 0.0}


def _readout(context, world):
    """``(key, length, selected_count)`` for the edge the panel reports.

    That is the active edge, or the only one, or else the first selected edge.
    ``key`` is ``None`` when nothing is selected.

    Everything is read inside this function on purpose: the edit-mode BMesh is
    freed as soon as the last Python reference to it goes away, and that
    invalidates every BMEdge/BMVert taken from it. Returning an edge to the caller
    would leave it pointing at freed data.
    """
    ob = context.edit_object
    if ob is None or ob.type != 'MESH':
        return None, 0.0, 0
    bm = bmesh.from_edit_mesh(ob.data)
    edges = core.selected_edges(bm)
    if not edges:
        return None, 0.0, 0
    edge = core.target_edge(bm, edges) or edges[0]
    length = core.edge_length(core.space_matrix(ob, world), edge)
    return _edge_key(ob, edge, world), length, len(edges)


def _edge_key(ob, edge, world):
    """Identifies an edge *and its current shape*, so the typed value is dropped as
    soon as the selection changes or the edge is edited (including by Set Length)."""
    coords = tuple(round(c, 6) for v in edge.verts for c in v.co)
    return (ob.name, world, coords)


def _get_length(self):
    # ``self`` is the settings group. Runs on every redraw, so it only reads.
    key, length, _count = _readout(bpy.context, self.world)
    if key is not None and _typed["key"] == key:
        return _typed["value"]
    return length


def _set_length(self, value):
    key, _length, _count = _readout(bpy.context, self.world)
    _typed["key"] = key
    _typed["value"] = value


def scale_notes(ob, world):
    """``[(icon, text), ...]`` describing unapplied object scale, or ``[]``.

    Uses the full world matrix, so scale inherited from parents counts too. In
    World Space the lengths are still correct, so that case is informational; in
    Local Space the typed number is not the real size, so it is a warning.
    Negative (mirrored) and zero scale are always warnings.
    """
    mw = ob.matrix_world
    det = mw.to_3x3().determinant()
    scale = mw.to_scale()
    notes = []

    if abs(det) < 1e-12:
        notes.append(('ERROR', "Zero scale on an axis"))
        notes.append(('BLANK1', "Edges along it can't be resized"))
        return notes
    if det < 0.0:
        notes.append(('ERROR', "Negative scale: object is mirrored"))

    if any(abs(abs(c) - 1.0) > 1e-5 for c in scale):  # mirroring alone keeps lengths
        values = ", ".join(f"{c:.4g}" for c in scale)
        if world:
            notes.append(('INFO', f"Unapplied scale: {values}"))
            notes.append(('BLANK1', "Lengths include it (World Space)"))
        else:
            notes.append(('ERROR', f"Unapplied scale: {values}"))
            notes.append(('BLANK1', "Local lengths differ from real size"))
    return notes


class PreciseEdgeLengthSettings(bpy.types.PropertyGroup):
    length: FloatProperty(
        name="Length",
        description="Length of the selected edge. Type a new value and click "
                    "Set Length to apply it",
        subtype='DISTANCE', unit='LENGTH', min=0.0, precision=4,
        get=_get_length, set=_set_length,
    )
    anchor: EnumProperty(name="Anchor", items=ANCHOR_ITEMS, default='AUTO')
    world: BoolProperty(
        name="World Space",
        description="Measure with the object's rotation and scale applied",
        default=True,
    )
    carry: BoolProperty(
        name="Carry Selection",
        description="Move the rest of the selection on the moving side by the same "
                    "offset, so faces translate instead of skewing",
        default=False,
    )


class VIEW3D_PT_precise_edge_length(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Item"
    bl_label = "Edge Length"
    bl_context = "mesh_edit"

    @classmethod
    def poll(cls, context):
        ob = context.edit_object
        return ob is not None and ob.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        settings = context.window_manager.precise_edge_length

        key, _length, count = _readout(context, settings.world)
        col = layout.column()
        col.enabled = key is not None
        col.prop(settings, "length")
        if count > 1:
            col.label(text=f"{count} edges selected", icon='INFO')

        # Apply straight away with the panel's values instead of opening the dialog.
        # F9 still adjusts the result afterwards.
        row = col.row()
        row.scale_y = 1.4
        row.operator_context = 'EXEC_DEFAULT'
        op = row.operator(MESH_OT_precise_edge_length_set.bl_idname, text="Set Length",
                          icon='DRIVER_DISTANCE')
        op.length = settings.length
        op.anchor = settings.anchor
        op.world = settings.world
        op.carry = settings.carry

        notes = scale_notes(context.edit_object, settings.world)
        if notes:
            box = layout.box().column(align=True)
            for icon, text in notes:
                box.label(text=text, icon=icon)

        layout.separator()
        layout.prop(settings, "anchor")
        layout.prop(settings, "world")
        layout.prop(settings, "carry")


def _menu_entry(self, context):
    self.layout.separator()
    self.layout.operator(MESH_OT_precise_edge_length_set.bl_idname, text="Set Edge Length...")


_menus = (
    bpy.types.VIEW3D_MT_edit_mesh_edges,
    bpy.types.VIEW3D_MT_edit_mesh_context_menu,
)

classes = (PreciseEdgeLengthSettings, VIEW3D_PT_precise_edge_length)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.precise_edge_length = PointerProperty(
        type=PreciseEdgeLengthSettings)
    for menu in _menus:
        menu.append(_menu_entry)


def unregister():
    for menu in reversed(_menus):
        menu.remove(_menu_entry)
    del bpy.types.WindowManager.precise_edge_length
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
