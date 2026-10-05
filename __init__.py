# SPDX-License-Identifier: GPL-3.0-or-later
"""Precise Edge Length -- type a precise length for mesh edges in Edit Mode.

Packaged as a Blender Extension: metadata lives in ``blender_manifest.toml``, so
there is deliberately no ``bl_info`` here.
"""

from __future__ import annotations

from . import operators, ui

#: Operators must exist before the panel and menus draw buttons for them.
_modules = (operators, ui)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
