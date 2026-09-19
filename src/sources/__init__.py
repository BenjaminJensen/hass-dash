"""Where Home Assistant lives, and the only place it is allowed to live.

Everything above this package speaks in domain objects (INTENT.md section 6).
An `EntityRef` comes in from the configuration, a `Snapshot` goes out, and no
layer above learns that an entity id, an attribute name or a REST endpoint
exists. `tests/test_source_boundary.py` enforces that mechanically rather than
by discipline.
"""
