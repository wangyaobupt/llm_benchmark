"""Bounded storage primitives for full-cohort cleaning acceptance audits."""

from __future__ import annotations

from collections import Counter, OrderedDict
import json
from pathlib import Path
import tempfile
from typing import Any, Iterable

import duckdb
import pyarrow as pa

from ..event_cleaning.ids import build_source_row_id, canonical_json
from ..event_cleaning.source_catalog import SOURCE_CATALOG


class JsonlRecordStore:
    """Line-number lookup backed by byte offsets into an immutable JSONL file."""

    def __init__(self, path: Path, *, cache_size: int = 8):
        self.path = Path(path).resolve()
        if cache_size < 1:
            raise ValueError("cache_size must be positive")
        self._cache_size = cache_size
        self._offsets: dict[int, tuple[int, int]] = {}
        self._cache: OrderedDict[int, dict[str, Any]] = OrderedDict()
        offset = 0
        with self.path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, 1):
                length = len(raw_line)
                if raw_line.strip():
                    self._offsets[line_number] = (offset, length)
                offset += length
        self._handle = self.path.open("rb")

    def _remember(self, line_number: int, value: dict[str, Any]) -> None:
        self._cache.pop(line_number, None)
        self._cache[line_number] = value
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def get(self, line_number: int, default: Any = None) -> Any:
        if line_number in self._cache:
            value = self._cache.pop(line_number)
            self._cache[line_number] = value
            return value
        location = self._offsets.get(line_number)
        if location is None:
            return default
        offset, length = location
        self._handle.seek(offset)
        value = json.loads(self._handle.read(length))
        if not isinstance(value, dict):
            raise ValueError(
                f"JSONL line {line_number} is not an object: {self.path}"
            )
        self._remember(line_number, value)
        return value

    def items(self) -> Iterable[tuple[int, dict[str, Any]]]:
        with self.path.open("rb") as handle:
            for line_number, (offset, length) in self._offsets.items():
                handle.seek(offset)
                value = json.loads(handle.read(length))
                if not isinstance(value, dict):
                    raise ValueError(
                        f"JSONL line {line_number} is not an object: {self.path}"
                    )
                self._remember(line_number, value)
                yield line_number, value

    def __iter__(self):
        return iter(self._offsets)

    def __len__(self) -> int:
        return len(self._offsets)

    def close(self) -> None:
        self._cache.clear()
        self._handle.close()

    def __enter__(self) -> "JsonlRecordStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class SourceIdentityResolver:
    """Resolve frozen source IDs on demand with a small admission-level cache."""

    def __init__(
        self,
        records: JsonlRecordStore,
        input_name: str,
        raw_ref_pattern: Any,
        *,
        admission_cache_size: int = 2,
    ):
        if admission_cache_size < 1:
            raise ValueError("admission_cache_size must be positive")
        self._records = records
        self._input_name = input_name
        self._pattern = raw_ref_pattern
        self._cache_size = admission_cache_size
        self._cache: OrderedDict[int, dict[str, str]] = OrderedDict()

    def _identities(self, line_number: int) -> dict[str, str] | None:
        if line_number in self._cache:
            value = self._cache.pop(line_number)
            self._cache[line_number] = value
            return value
        admission = self._records.get(line_number)
        if admission is None:
            return None
        identities: dict[str, str] = {}
        for spec in SOURCE_CATALOG:
            occurrences: Counter[str] = Counter()
            rows = admission[spec.module][spec.table]
            for index, row in enumerate(rows):
                ordinal = 0
                if spec.identity_strategy == "canonical_row_hash_with_occurrence":
                    identity = canonical_json(row)
                    ordinal = occurrences[identity]
                    occurrences[identity] += 1
                raw_ref = (
                    f"{self._input_name}#L{line_number}/"
                    f"{spec.module}.{spec.table}[{index}]"
                )
                identities[raw_ref] = build_source_row_id(
                    spec,
                    row,
                    duplicate_occurrence_ordinal=ordinal,
                )
        self._cache[line_number] = identities
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return identities

    def get(self, raw_ref: str, default: Any = None) -> Any:
        match = self._pattern.fullmatch(raw_ref)
        if match is None:
            return default
        parts = match.groupdict()
        if parts["filename"] != self._input_name:
            return default
        identities = self._identities(int(parts["line"]))
        if identities is None:
            return default
        return identities.get(raw_ref, default)

    def __getitem__(self, raw_ref: str) -> str:
        value = self.get(raw_ref)
        if value is None:
            raise KeyError(raw_ref)
        return str(value)

    def close(self) -> None:
        self._cache.clear()


class AuditIndex:
    """Bulk, disk-backed relational checks for identities and source coverage."""

    _SCHEMAS = {
        "events": pa.schema(
            [
                ("event_id", pa.string()),
                ("table_id", pa.int16()),
                ("source_id", pa.string()),
            ]
        ),
        "rejected": pa.schema(
            [("table_id", pa.int16()), ("source_id", pa.string())]
        ),
        "supports": pa.schema(
            [("table_id", pa.int16()), ("source_id", pa.string())]
        ),
        "sources": pa.schema(
            [
                ("table_id", pa.int16()),
                ("source_id", pa.string()),
                ("role", pa.string()),
                ("expected_events", pa.int16()),
            ]
        ),
    }

    def __init__(self, work_directory: Path | None, *, batch_size: int = 50_000):
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        root = Path(work_directory).resolve() if work_directory else Path(tempfile.gettempdir())
        root.mkdir(parents=True, exist_ok=True)
        self._temporary = tempfile.TemporaryDirectory(
            prefix="event-cleaning-audit-", dir=root
        )
        temporary = Path(self._temporary.name)
        (temporary / "duckdb-temp").mkdir()
        self._connection = duckdb.connect(str(temporary / "audit.duckdb"))
        escaped_temp = str(temporary / "duckdb-temp").replace("'", "''")
        self._connection.execute(f"SET temp_directory='{escaped_temp}'")
        self._connection.execute("SET preserve_insertion_order=false")
        self._batch_size = batch_size
        self._buffers: dict[str, list[tuple[Any, ...]]] = {
            name: [] for name in self._SCHEMAS
        }
        self._table_ids = {
            spec.source_table: index for index, spec in enumerate(SOURCE_CATALOG)
        }
        self._table_names = {value: key for key, value in self._table_ids.items()}
        for name, schema in self._SCHEMAS.items():
            empty = pa.Table.from_arrays(
                [pa.array([], type=field.type) for field in schema], schema=schema
            )
            view_name = f"_{name}_schema"
            self._connection.register(view_name, empty)
            self._connection.execute(
                f"CREATE TABLE {name} AS SELECT * FROM {view_name}"
            )
            self._connection.unregister(view_name)

    def _append(self, name: str, row: tuple[Any, ...]) -> None:
        buffer = self._buffers[name]
        buffer.append(row)
        if len(buffer) >= self._batch_size:
            self._flush(name)

    def _flush(self, name: str) -> None:
        rows = self._buffers[name]
        if not rows:
            return
        schema = self._SCHEMAS[name]
        columns = list(zip(*rows))
        batch = pa.Table.from_arrays(
            [
                pa.array(column, type=field.type)
                for column, field in zip(columns, schema)
            ],
            schema=schema,
        )
        view_name = f"_{name}_batch"
        self._connection.register(view_name, batch)
        self._connection.execute(f"INSERT INTO {name} SELECT * FROM {view_name}")
        self._connection.unregister(view_name)
        rows.clear()

    def add_event(self, event_id: str, source_table: str, source_id: str) -> None:
        self._append(
            "events", (event_id, self._table_ids[source_table], source_id)
        )

    def add_rejected(self, source_table: str, source_id: str) -> None:
        self._append("rejected", (self._table_ids[source_table], source_id))

    def add_support(self, source_table: str, source_id: str) -> None:
        self._append("supports", (self._table_ids[source_table], source_id))

    def add_source(
        self,
        source_table: str,
        source_id: str,
        role: str,
        expected_events: int,
    ) -> None:
        self._append(
            "sources",
            (self._table_ids[source_table], source_id, role, expected_events),
        )

    def _flush_all(self) -> None:
        for name in self._buffers:
            self._flush(name)

    def _counts_by_table(self, table: str, expression: str = "count(*)") -> dict[str, int]:
        rows = self._connection.execute(
            f"SELECT table_id, {expression} FROM {table} GROUP BY table_id"
        ).fetchall()
        return {self._table_names[int(table_id)]: int(count) for table_id, count in rows}

    def _issue(self, query: str) -> tuple[int, list[str]]:
        count = int(self._connection.execute(f"SELECT count(*) FROM ({query})").fetchone()[0])
        rows = self._connection.execute(
            f"{query} ORDER BY 1, 2 LIMIT 20"
        ).fetchall()
        examples = [
            f"{self._table_names[int(table_id)]}:{source_id}"
            for table_id, source_id in rows
        ]
        return count, examples

    def analyze(self) -> dict[str, Any]:
        self._flush_all()
        duplicate_event_ids = int(
            self._connection.execute(
                """
                SELECT coalesce(sum(n - 1), 0)
                FROM (
                    SELECT event_id, count(*) AS n
                    FROM events
                    WHERE event_id IS NOT NULL
                    GROUP BY event_id HAVING count(*) > 1
                )
                """
            ).fetchone()[0]
        )
        duplicate_examples = [
            str(row[0])
            for row in self._connection.execute(
                """
                SELECT event_id FROM events WHERE event_id IS NOT NULL
                GROUP BY event_id HAVING count(*) > 1
                ORDER BY event_id LIMIT 20
                """
            ).fetchall()
        ]
        accepted = self._counts_by_table("events", "count(DISTINCT source_id)")
        rejected = self._counts_by_table("rejected", "count(DISTINCT source_id)")
        inputs = self._counts_by_table("sources")
        events = self._counts_by_table("events")
        linked = dict(
            (
                self._table_names[int(table_id)],
                int(count),
            )
            for table_id, count in self._connection.execute(
                """
                SELECT s.table_id, count(DISTINCT s.source_id)
                FROM sources s
                JOIN (SELECT DISTINCT table_id, source_id FROM supports) p
                  USING (table_id, source_id)
                WHERE s.role='support'
                GROUP BY s.table_id
                """
            ).fetchall()
        )
        classification_query = """
            WITH accepted AS (
                SELECT DISTINCT table_id, source_id FROM events
            ), rejected_ids AS (
                SELECT DISTINCT table_id, source_id FROM rejected
            )
            SELECT s.table_id, s.source_id
            FROM sources s
            LEFT JOIN accepted a USING (table_id, source_id)
            LEFT JOIN rejected_ids r USING (table_id, source_id)
            WHERE s.role='event'
              AND (CAST(a.source_id IS NOT NULL AS INTEGER)
                   + CAST(r.source_id IS NOT NULL AS INTEGER)) <> 1
        """
        support_query = """
            WITH linked AS (
                SELECT DISTINCT table_id, source_id FROM supports
            )
            SELECT s.table_id, s.source_id
            FROM sources s
            LEFT JOIN linked l USING (table_id, source_id)
            WHERE s.role='support' AND l.source_id IS NULL
        """
        event_count_query = """
            WITH actual AS (
                SELECT table_id, source_id, count(*) AS event_count
                FROM events GROUP BY table_id, source_id
            )
            SELECT s.table_id, s.source_id
            FROM sources s
            JOIN actual a USING (table_id, source_id)
            WHERE s.role='event' AND a.event_count <> s.expected_events
        """
        issues = {
            "source_row_classification_mismatch": self._issue(classification_query),
            "supporting_source_row_unlinked": self._issue(support_query),
            "source_row_event_count_mismatch": self._issue(event_count_query),
        }
        by_table = {
            source_table: {
                "input_rows": inputs.get(source_table, 0),
                "accepted_source_rows": accepted.get(source_table, 0),
                "rejected_source_rows": rejected.get(source_table, 0),
                "linked_source_rows": linked.get(source_table, 0),
                "events": events.get(source_table, 0),
            }
            for source_table in self._table_ids
        }
        return {
            "duplicate_event_ids": duplicate_event_ids,
            "duplicate_event_examples": duplicate_examples,
            "accepted_unique_source_rows": sum(accepted.values()),
            "rejected_unique_source_rows": sum(rejected.values()),
            "by_table": by_table,
            "issues": issues,
        }

    def close(self) -> None:
        self._connection.close()
        self._temporary.cleanup()

    def __enter__(self) -> "AuditIndex":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
