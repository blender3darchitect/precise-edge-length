# Precise Edge Length

A Blender extension (4.2 LTS and newer) for typing an exact length for mesh edges in
Edit Mode.

- **World space by default.** Lengths are measured with the object's rotation, parenting
  and scale applied, including non-uniform scale, so the number you type is the number
  the Edge Length overlay shows in Global mode. Turn off *World Space* to work in local
  coordinates.
- **Scene units.** The length field follows the scene's unit system and unit scale, so
  you can type `12' 6"`, `3.6m` or `250mm`.
- **Predictable anchor.** The active vertex stays fixed. If no vertex is active, both
  ends move equally from the midpoint. Switch between *Start* and *End* to choose
  which end stays fixed, or use *3D Cursor* to scale from the cursor's position along the
  edge (snap the cursor to a vertex with Shift+S to keep that vertex fixed).
- **Carry Selection.** Selected geometry attached to the moving end moves with it, so
  you can lengthen a wall by selecting its end face plus one edge along its length.
- **Several edges at once.** With Carry Selection off, every selected edge is set to the
  same length. The edges must not share vertices.
- **Multi-object Edit Mode.** Each object uses its own transform.

## Usage

1. In Edit Mode, select an edge. To keep one end fixed, select the vertex to move first
   and the vertex to keep last, so that the second one is active.
2. Open **Sidebar (N) > Item > Edge Length**. The **Length** field shows the selected
   edge's current length.
3. Type a new length and click **Set Length**. Change the options afterwards with
   **Adjust Last Operation** (F9) if needed.

The operator is also in **Edge > Set Edge Length...** and the right-click menu, where it
opens a dialog prefilled with the current length.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
