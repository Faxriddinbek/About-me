"""Portfolio backend application package.

A production-grade FastAPI backend serving a bilingual (Uzbek default, English
secondary) personal portfolio site. The package is organised in layers —
``api`` -> ``services`` -> ``repositories`` -> ``db`` — so that HTTP concerns,
business logic, and persistence stay decoupled and independently testable.
"""
