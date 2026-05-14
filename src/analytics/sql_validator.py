from __future__ import annotations

import re
from dataclasses import dataclass

from src.analytics.schema_registry import TABLES

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

_ALLOWED_DATABASES = {"invoice_pipeline_gold"}
_BLOCKED_KEYWORDS = {
    "alter",
    "create",
    "delete",
    "drop",
    "insert",
    "merge",
    "truncate",
    "update",
}
_ALLOWED_FUNCTIONS = {
    "approx_distinct",
    "avg",
    "cast",
    "coalesce",
    "count",
    "date",
    "date_parse",
    "date_trunc",
    "day",
    "distinct",
    "lower",
    "max",
    "min",
    "month",
    "round",
    "sum",
    "upper",
    "year",
}
_SQL_KEYWORDS = {
    "and",
    "as",
    "asc",
    "between",
    "by",
    "case",
    "desc",
    "else",
    "end",
    "false",
    "from",
    "group",
    "having",
    "in",
    "is",
    "join",
    "left",
    "like",
    "limit",
    "not",
    "null",
    "on",
    "or",
    "order",
    "right",
    "select",
    "then",
    "true",
    "when",
    "where",
}


class SqlValidationError(ValueError):
    """Raised when generated SQL is outside the allowed analytics subset."""


@dataclass(frozen=True)
class ValidatedSql:
    sql: str
    tables: tuple[str, ...]
    limit: int


def validate_sql(sql: str) -> ValidatedSql:
    normalized = _normalize_sql(sql)
    lowered = normalized.lower()

    if not lowered.startswith("select "):
        raise SqlValidationError("Only SELECT queries are allowed.")
    if any(re.search(rf"\b{keyword}\b", lowered) for keyword in _BLOCKED_KEYWORDS):
        raise SqlValidationError("DDL and DML statements are not allowed.")
    if _has_unrestricted_wildcard(lowered):
        raise SqlValidationError("SELECT * is not allowed.")

    tables = _extract_tables(lowered)
    if not tables:
        raise SqlValidationError("Query must reference an allowed table.")
    unknown_tables = sorted({table for table in tables if table not in TABLES})
    if unknown_tables:
        raise SqlValidationError(f"Unknown table(s): {', '.join(unknown_tables)}")

    allowed_columns = {
        column for table in tables for column in TABLES[table].all_columns
    }
    aliases = _extract_aliases(lowered)
    _validate_identifiers(lowered, allowed_columns, aliases, set(tables))

    limited_sql, limit = _ensure_limit(normalized)
    return ValidatedSql(sql=limited_sql, tables=tuple(dict.fromkeys(tables)), limit=limit)


def _normalize_sql(sql: str) -> str:
    cleaned = sql.strip()
    while cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()
    if not cleaned:
        raise SqlValidationError("SQL query is empty.")
    if ";" in cleaned:
        raise SqlValidationError("Only one SQL statement is allowed.")
    return re.sub(r"\s+", " ", cleaned)


def _has_unrestricted_wildcard(lowered_sql: str) -> bool:
    select_body = lowered_sql.split(" from ", maxsplit=1)[0]
    if re.search(r"\bselect\s+\*", select_body):
        return True
    if re.search(r"(^|,)\s*\*", select_body):
        return True
    return bool(re.search(r"\b[a-z_][a-z0-9_]*\.\*", lowered_sql))


def _extract_tables(lowered_sql: str) -> list[str]:
    tables: list[str] = []
    for match in re.finditer(r"\b(?:from|join)\s+([a-z_][a-z0-9_.]*)", lowered_sql):
        table = match.group(1).split(".")[-1]
        tables.append(table)
    return tables


def _extract_aliases(lowered_sql: str) -> set[str]:
    aliases = set(re.findall(r"\bas\s+([a-z_][a-z0-9_]*)", lowered_sql))
    for match in re.finditer(
        r"\b(?:from|join)\s+[a-z_][a-z0-9_.]*(?:\s+([a-z_][a-z0-9_]*))?",
        lowered_sql,
    ):
        alias = match.group(1)
        if alias and alias not in _SQL_KEYWORDS:
            aliases.add(alias)
    return aliases


def _validate_identifiers(
    lowered_sql: str,
    allowed_columns: set[str],
    aliases: set[str],
    table_names: set[str],
) -> None:
    scrubbed = re.sub(r"'[^']*'", " ", lowered_sql)
    scrubbed = re.sub(r'"[^"]*"', " ", scrubbed)
    identifiers = set(re.findall(r"\b[a-z_][a-z0-9_]*\b", scrubbed))
    allowed = (
        allowed_columns
        | aliases
        | table_names
        | _ALLOWED_DATABASES
        | _SQL_KEYWORDS
        | _ALLOWED_FUNCTIONS
    )
    unknown = sorted(identifiers - allowed)
    if unknown:
        raise SqlValidationError(f"Unknown identifier(s): {', '.join(unknown)}")


def _ensure_limit(sql: str) -> tuple[str, int]:
    match = re.search(r"\blimit\s+(\d+)\b", sql, flags=re.IGNORECASE)
    if match:
        limit = int(match.group(1))
        if limit > MAX_LIMIT:
            raise SqlValidationError(f"LIMIT must be less than or equal to {MAX_LIMIT}.")
        return sql, limit
    return f"{sql} LIMIT {DEFAULT_LIMIT}", DEFAULT_LIMIT
