"""Report the values the lower layer actually used, for `confirm` (spec 5章 with と confirm).

    from ponte.report import report, lr_of, batch_of
    report(lr=lr_of(optimizer), batch=batch_of(loader), pretrained=weights_loaded)

Read each value from the thing that uses it (the optimizer, the data loader, the client),
not from the arguments you meant to pass. That is what catches a value that was silently dropped.

This file imports nothing else from Ponte, so it can be copied into any project as it is.
Inside Ponte the reports are collected in memory; when the environment variable PONTE_REPORT names
a file (a separate process, such as a training script), each report is also appended there as one JSON line.
"""
from __future__ import annotations

import json
import os
import threading

_local = threading.local()


def report(**values) -> None:
    """Record the values actually in use. Call it once per run, or several times (later calls add or overwrite)."""
    store = getattr(_local, "values", None)
    if store is not None:
        store.update(values)
    path = os.environ.get("PONTE_REPORT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(values, default=str, ensure_ascii=False) + "\n")


def lr_of(optimizer) -> float:
    """The learning rate the optimizer really has (its first parameter group)."""
    return optimizer.param_groups[0]["lr"]


def batch_of(loader) -> int:
    """The batch size the data loader really uses."""
    return loader.batch_size


class collect:
    """Inside Ponte: `with collect() as got: body(...)` gathers what the body reported."""

    def __enter__(self) -> dict:
        self.prev = getattr(_local, "values", None)
        _local.values = {}
        return _local.values

    def __exit__(self, *exc) -> None:
        _local.values = self.prev
