"""Media domain (images, uploads, extraction).

This file exists so the package is a regular package rather than an implicit
namespace package: `pkgutil.walk_packages` does not descend into the latter, so
without it `check_imports.py` silently skipped the entire media domain (#583).
Every other domain already had one — media was the exception.
"""
