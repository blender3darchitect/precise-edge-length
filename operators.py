# SPDX-License-Identifier: GPL-3.0-or-later
"""The Set Edge Length operator."""

from __future__ import annotations

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty

from . import core

ANCHOR_ITEMS = (
    ('AUTO', "Auto",
     "The active vertex stays fixed. Without one, the end carrying more of the "
     "selection moves, or both ends move from the midpoint"),
    ('START', "Start",
     "The edge's start vertex stays fixed. Switch to End to keep the other one"),
    ('END', "End",
     "The edge's end vertex stays fixed. Switch to Start to keep the other one"),
    ('CENTER', "Midpoint", "Both ends move equally from the midpoint"),
    ('CURSOR', "3D Cursor",
     "Scale from the 3D cursor's position along the edge. Snap the cursor to a "
     "vertex to keep that vertex fixed"),
)


def _mesh_objects(context):
    """Objects in Edit Mode with unique mesh data, active object first."""
    objs = [ob for ob in context.objects_in_mode_unique_data if ob.type == 'MESH']
    active = context.edit_object
    objs.sort(key=lambda ob: ob != active)
    return objs


class MESH_OT_precise_edge_length_set(bpy.types.Operator):
    """Set selected edges to an exact length"""
    bl_idname = "mesh.precise_edge_length_set"
    bl_label = "Set Edge Length"
    bl_options = {'REGISTER', 'UNDO'}

    length: FloatProperty(
        name="Length",
        description="Target edge length, in scene units",
        subtype='DISTANCE', unit='LENGTH',
        min=0.0, default=1.0, precision=4,
    )
    anchor: EnumProperty(name="Anchor", items=ANCHOR_ITEMS, default='AUTO')
    world: BoolProperty(
        name="World Space",
        description="Measure with the object's rotation and scale applied, "
                    "like the Global option of the Edge Length overlay",
        default=True,
    )
    carry: BoolProperty(
        name="Carry Selection",
        description="Move the rest of the selection on the moving side by the same "
                    "offset, so faces translate instead of skewing. "
                    "Acts on the active edge only",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        ob = context.edit_object
        return ob is not None and ob.type == 'MESH'

    def invoke(self, context, event):
        # Prefill with the length of the edge that will be measured, so the user
        # edits the current value instead of typing it from scratch.
        for ob in _mesh_objects(context):
            bm = bmesh.from_edit_mesh(ob.data)
            edges = core.selected_edges(bm)
            if not edges:
                continue
            edge = core.target_edge(bm, edges) or edges[0]
            self.length = core.edge_length(core.space_matrix(ob, self.world), edge)
            return context.window_manager.invoke_props_dialog(self)

        self.report({'WARNING'}, "Select at least one edge")
        return {'CANCELLED'}

    def execute(self, context):
        if self.length <= 0.0:
            self.report({'ERROR'}, "Length must be greater than zero")
            return {'CANCELLED'}

        changed = 0
        errors = []
        for ob in _mesh_objects(context):
            bm = bmesh.from_edit_mesh(ob.data)
            edges = core.selected_edges(bm)
            if not edges:
                continue
            try:
                changed += self._apply(context, bm, ob, edges)
            except core.EdgeLengthError as exc:
                errors.append(f"{ob.name}: {exc}")
                continue
            bmesh.update_edit_mesh(ob.data, loop_triangles=True, destructive=False)

        for msg in errors:
            self.report({'ERROR'}, msg)
        if not changed:
            if not errors:
                self.report({'WARNING'}, "Select at least one edge")
            return {'CANCELLED'}
        return {'FINISHED'}

    def _apply(self, context, bm, ob, edges):
        """Validate everything first, then move, so a bad edge leaves the mesh as is."""
        M = core.space_matrix(ob, self.world)
        pivot = None
        if self.anchor == 'CURSOR':
            # The cursor lives in world space; bring it into the measuring space.
            pivot = M @ ob.matrix_world.inverted_safe() @ context.scene.cursor.location

        if self.carry:
            edge = core.target_edge(bm, edges)
            if edge is None:
                raise core.EdgeLengthError(
                    "Carry Selection needs an active edge, or two clicked vertices")
            sides = core.selection_sides(edge)
            ends = core.resolve_ends(bm, edge, self.anchor, sides)
            jobs = [(edge, ends, sides)]
        else:
            core.check_disjoint(edges)
            jobs = [(e, core.resolve_ends(bm, e, self.anchor), None)
                    for e in edges]

        for edge, _ends, _carry in jobs:
            if core.edge_length(M, edge) < core.EPSILON:
                raise core.EdgeLengthError(
                    "Edge has zero length, so its direction is undefined")

        for edge, ends, carry in jobs:
            core.set_edge_length(M, edge, self.length, ends, carry, pivot)
        return len(jobs)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, "length")
        layout.prop(self, "anchor")
        layout.prop(self, "world")
        layout.prop(self, "carry")


classes = (MESH_OT_precise_edge_length_set,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
