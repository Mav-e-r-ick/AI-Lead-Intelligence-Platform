"""Cross-cutting, framework-level plumbing: settings and logging setup.

Unlike domain/application/infrastructure/interfaces, `core` is not a Clean
Architecture "layer" — it's small, shared, low-level utility code that
every other layer is allowed to import (e.g. everyone needs to read
settings and write log lines).
"""
