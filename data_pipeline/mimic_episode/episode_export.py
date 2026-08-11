from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb


REQUIRED_EXPORT_FILES = (
    "episode_index.parquet",
    "care_contacts.parquet",
    "timeline_events.parquet",
    "event_items.parquet",
    "documents.parquet",
    "episode_coverage.parquet",
)


def _sql_literal(value: str | Path) -> str:
    if isinstance(value, Path):
        value = value.resolve().as_posix()
    return "'" + str(value).replace("'", "''") + "'"


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    return value


def _query_dicts(
    connection: duckdb.DuckDBPyConnection,
    sql: str,
) -> list[dict[str, Any]]:
    cursor = connection.execute(sql)
    columns = [description[0] for description in cursor.description]
    return [
        {column: _json_value(value) for column, value in zip(columns, row)}
        for row in cursor.fetchall()
    ]


def export_episode_json(
    output_dir: Path,
    episode_id: str,
    destination: Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    root = Path(output_dir).resolve()
    missing = [root / name for name in REQUIRED_EXPORT_FILES if not (root / name).is_file()]
    if missing:
        details = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"缺少病例导出所需 Parquet：\n{details}")

    target = Path(destination).resolve()
    if target.exists() and not overwrite:
        raise FileExistsError(f"病例 JSON 已存在；如需覆盖请明确指定 overwrite：{target}")

    episode_file = _sql_literal(root / "episode_index.parquet")
    contact_file = _sql_literal(root / "care_contacts.parquet")
    event_file = _sql_literal(root / "timeline_events.parquet")
    item_file = _sql_literal(root / "event_items.parquet")
    document_file = _sql_literal(root / "documents.parquet")
    coverage_file = _sql_literal(root / "episode_coverage.parquet")
    episode_literal = _sql_literal(episode_id)

    connection = duckdb.connect()
    try:
        episodes = _query_dicts(
            connection,
            f"SELECT * FROM read_parquet({episode_file}) WHERE episode_id = {episode_literal}",
        )
        if not episodes:
            raise KeyError(f"不存在 episode_id：{episode_id}")
        episode = episodes[0]
        subject_id = int(episode["subject_id"])
        start_literal = _sql_literal(episode["episode_start_time"])

        contacts = _query_dicts(
            connection,
            f"SELECT * FROM read_parquet({contact_file}) "
            f"WHERE episode_id = {episode_literal} "
            "ORDER BY contact_sequence, contact_id",
        )
        current_events = _query_dicts(
            connection,
            f"SELECT * FROM read_parquet({event_file}) "
            f"WHERE episode_id = {episode_literal} "
            "ORDER BY available_time NULLS LAST, event_time NULLS LAST, event_id",
        )
        current_documents = _query_dicts(
            connection,
            f"SELECT * FROM read_parquet({document_file}) "
            f"WHERE episode_id = {episode_literal} "
            "ORDER BY available_time NULLS LAST, event_time NULLS LAST, note_id",
        )
        coverage_rows = _query_dicts(
            connection,
            f"SELECT * FROM read_parquet({coverage_file}) WHERE episode_id = {episode_literal}",
        )

        current_event_ids = [event["event_id"] for event in current_events]
        if current_event_ids:
            ids = ", ".join(_sql_literal(event_id) for event_id in current_event_ids)
            current_items = _query_dicts(
                connection,
                f"SELECT * EXCLUDE (raw_payload) FROM read_parquet({item_file}) "
                f"WHERE event_id IN ({ids}) ORDER BY event_id, item_ordinal, item_event_id",
            )
        else:
            current_items = []

        prior_events = _query_dicts(
            connection,
            f"SELECT * FROM read_parquet({event_file}) "
            f"WHERE subject_id = {subject_id} AND available_time < {start_literal} "
            "ORDER BY available_time, event_time NULLS LAST, event_id",
        )
        prior_documents = _query_dicts(
            connection,
            f"SELECT * FROM read_parquet({document_file}) "
            f"WHERE subject_id = {subject_id} AND available_time < {start_literal} "
            "ORDER BY available_time, event_time NULLS LAST, note_id",
        )
    finally:
        connection.close()

    payload: dict[str, Any] = {
        "episode_id": episode_id,
        "patient": {"subject_id": subject_id},
        "prior_context": {
            "events": prior_events,
            "documents": prior_documents,
        },
        "current_episode": {
            "episode": episode,
            "care_contacts": contacts,
            "timeline_events": current_events,
            "event_items": current_items,
            "documents": current_documents,
        },
        "coverage": coverage_rows[0] if coverage_rows else {},
        "provenance": {
            "source": "episode_aggregation_parquet",
            "history_rule": "available_time < episode_start_time",
        },
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
