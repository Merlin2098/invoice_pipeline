# Chat Agent Scope Design

## Purpose

This document explains how the invoice pipeline's natural-language chat
agent (`chat_api.py`) is constrained to answer only invoice-related
analytics questions over the Gold layer. It is intended as a reference
pattern when implementing other Bedrock-backed agents in this repository.

The core idea: **the LLM is treated as untrusted**. Scoping is not achieved
by asking the model nicely — it's enforced by deterministic validation that
runs on every model output before anything is executed.

---

## Request flow

```
question (user)
   │
   ▼
[1] BedrockSqlGenerator  -- generates candidate SQL using a fixed
   │                         system prompt + a single allowed table schema
   ▼
[2] sql_validator.validate_sql()  -- deterministic whitelist check
   │                                 (rejects/raises before execution)
   ▼
[3] AthenaClient  -- executes only against a fixed database/workgroup
   │
   ▼
[4] Bedrock summarizer  -- turns result rows into a business-language
                            answer (own narrow system prompt)
```

Files involved:

* [`src/aws/lambda_handlers/chat_api.py`](../src/aws/lambda_handlers/chat_api.py) — orchestration
* [`src/analytics/bedrock_sql.py`](../src/analytics/bedrock_sql.py) — SQL generation step
* [`src/analytics/sql_validator.py`](../src/analytics/sql_validator.py) — the actual security boundary
* [`src/analytics/schema_registry.py`](../src/analytics/schema_registry.py) — single source of truth for known tables/columns
* [`specs/prompts/bedrock_analytics_sql_prompt.md`](../specs/prompts/bedrock_analytics_sql_prompt.md) — system prompt for SQL generation

---

## Layer 1 — Narrow context at generation time

`BedrockSqlGenerator.generate_sql()` builds the prompt sent to Bedrock from
two sources only:

1. A fixed system prompt (`bedrock_analytics_sql_prompt.md`) stating: return
   only SQL, SELECT-only, no DDL/DML, no `SELECT *`, use only the provided
   schema.
2. The schema of **one table** (`gold_invoice_summary` by default),
   generated dynamically from `schema_registry.py`.

The model is never shown other tables, other databases, or infrastructure
details. This keeps generated SQL *plausible* and on-topic, but it is a
steering mechanism, not a guarantee — a model can still hallucinate or be
prompt-injected via the user's question text.

---

## Layer 2 — Deterministic SQL validation (the real boundary)

`sql_validator.validate_sql()` parses and checks the generated SQL with
regex-based rules, independent of what the model intended:

| Check | Rule |
|---|---|
| Statement type | Must start with `select ` |
| Blocked keywords | `alter`, `create`, `delete`, `drop`, `insert`, `merge`, `truncate`, `update` rejected anywhere |
| Wildcards | `SELECT *`, `alias.*`, bare `*` in select list rejected |
| Statement count | Only one statement allowed (any `;` rejected) |
| Tables | Every `FROM`/`JOIN` target must be a key in `TABLES` (currently `gold_documents`, `gold_invoice_summary`) |
| Identifiers | Every identifier (column, alias, function) must be in: allowed columns for the referenced tables, detected aliases, table names, `_ALLOWED_DATABASES`, SQL keyword list, or `_ALLOWED_FUNCTIONS` |
| Limit | A `LIMIT` is enforced (default 100, hard cap 1000) |

Any violation raises `SqlValidationError`, which `chat_api.py` turns into a
`400 sql_validation_error` response **without ever calling Athena**.

This is the layer that actually prevents scope creep: even if the model is
coerced (via prompt injection in the user's question) into emitting SQL
against an unrelated table, a system table, or with destructive intent, the
validator rejects it because the table/column/keyword isn't in the
whitelist derived from `schema_registry.py`.

---

## Layer 3 — Execution boundary

`AthenaClient` always executes against a fixed `database` (from
`GLUE_DATABASE`, default `invoice_pipeline_gold`) and a fixed `workgroup`.
The validated SQL cannot reference another database — `_validate_identifiers`
only allows `_ALLOWED_DATABASES = {"invoice_pipeline_gold"}` as an
identifier, so even a fully-qualified `other_db.some_table` reference would
fail identifier validation.

---

## Layer 4 — Output summarization

`_summarize_results()` makes a second, separate Bedrock call with its own
narrow system prompt ("You are a helpful analytics assistant that
summarizes data query results in plain business language... Do not mention
SQL or technical details"). It only ever receives the user's question, the
already-validated SQL, and up to `_CHAT_RESULT_ROW_CAP` (50) result rows —
never raw schema or credentials.

---

## Other guardrails

* `_MAX_QUESTION_CHARS = 500` — bounds input size before it ever reaches Bedrock.
* `inferenceConfig={"temperature": 0}` on both Bedrock calls — deterministic, less prone to creative deviation.
* Structured logging (`logger.bind(user_question=...)`, generated SQL, query id, scan size) on every completed query for auditability.

---

## Pattern to reuse for new agents

When adding a new Bedrock-backed agent in this repo:

1. **Define a schema/whitelist registry** (tables, columns, allowed
   functions/operations) analogous to `schema_registry.py`. This is the
   single source of truth for both the prompt and the validator.
2. **Write a narrow system prompt** that only describes what's in that
   registry — don't let the model see unrelated capabilities.
3. **Validate the model's structured output deterministically** before
   acting on it. Reject anything outside the whitelist; never rely on the
   prompt alone to enforce scope.
4. **Fix the execution target** (database, workgroup, bucket, API endpoint,
   etc.) so validated output cannot redirect execution elsewhere.
5. If summarizing or rendering results back to the user, use a **separate,
   narrowly-scoped prompt** for that step, fed only with already-validated
   data.
6. Bound input size, use `temperature: 0` for structured generation, and log
   generated artifacts (SQL, queries, commands) for auditability.
