"""In-memory registry of tables, keyed by room code."""

from __future__ import annotations

import secrets

from .table import Table

# Unambiguous alphabet: no O/0, I/1/L confusion.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 4


class Rooms:
    """Holds tables for the lifetime of the process.

    State is intentionally in memory: a home game is ephemeral, and this keeps
    deployment (and the Docker image) trivial. See docs/DECISIONS.md.
    """

    def __init__(self) -> None:
        self._tables: dict[str, Table] = {}

    def create(self) -> Table:
        code = self._new_code()
        table = Table(code)
        self._tables[code] = table
        return table

    def get(self, code: str) -> Table | None:
        return self._tables.get(code.upper())

    def remove(self, code: str) -> None:
        self._tables.pop(code.upper(), None)

    def __len__(self) -> int:
        return len(self._tables)

    def _new_code(self) -> str:
        for _ in range(100):
            code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
            if code not in self._tables:
                return code
        raise RuntimeError("could not allocate a unique room code")


# Process-wide registry shared by the HTTP and WebSocket layers.
rooms = Rooms()
