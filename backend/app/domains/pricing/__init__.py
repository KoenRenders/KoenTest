"""Pricing domain (prices over time, regular and member).

This file exists so the package is a regular package rather than an implicit
namespace package: `pkgutil.walk_packages` does not descend into the latter, so
without it `check_imports.py` would silently skip the whole domain.
"""
