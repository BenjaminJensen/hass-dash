"""Pure layout: domain objects in, a declarative draw list out.

No PIL, no hardware, no clock. A layout function is a function of its
arguments, which is what lets the tests assert on content, position, colour and
update class without a display (INTENT.md section 6).
"""
