"""Reporting domain (#832, CR-06): the universe and the engine over it.

Reads from every other domain through the `reporting` views its own migrations
create, and is imported by none of them — a one-way dependency the import gate
enforces. Its public surface is `api.py`.
"""
