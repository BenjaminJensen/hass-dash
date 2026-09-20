"""The one failure type the panel raises.

Its own module so that `render/epd.py` and `render/panel/` can both name it
without either importing the other. `render.epd.PanelError` re-exports it, and
that name is the one the rest of the project has always used.
"""

from __future__ import annotations


class PanelError(RuntimeError):
    """The frame did not reach the glass.

    Raised for a panel that would not initialise, a plane the panel cannot
    accept, a panel that stopped answering, and a refresh class the renderer
    has no path for. The loop catches it like any other target failure: the
    cycle is not recorded, so the floor, the keep-alive and the partial budget
    all behave as though it never happened, and the next tick tries again.

    That is exactly the semantics a BUSY timeout needs, which is why the
    deadline in `driver.py` raises this rather than inventing its own.
    """
