from __future__ import annotations

"""UI dialogs package.

Keep this package init lightweight so importing one dialog submodule doesn't
force eager imports of all other dialogs and their optional dependencies.
"""

__all__: list[str] = []
