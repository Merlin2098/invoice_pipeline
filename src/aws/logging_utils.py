from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


SERVICE_NAME = "invoice_pipeline"
DEFAULT_FIELDS = {
    "run_id": None,
    "execution_id": None,
    "document_id": None,
    "source_s3_key": None,
    "status": None,
    "duration_ms": None,
    "error_code": None,
}

logging.basicConfig(level=logging.INFO, format="%(message)s")


class JsonLoggerAdapter(logging.LoggerAdapter[Any]):
    def bind(self, **kwargs: Any) -> "JsonLoggerAdapter":
        context = dict(self.extra)
        context.update({key: value for key, value in kwargs.items() if value is not None})
        return JsonLoggerAdapter(self.logger, context)

    def process(
        self, msg: Any, kwargs: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": kwargs.pop("_level", None),
            "service": SERVICE_NAME,
            **DEFAULT_FIELDS,
            **self.extra,
        }
        if isinstance(msg, dict):
            message = msg.get("message")
            payload.update({key: value for key, value in msg.items() if key != "message"})
            payload["message"] = str(message or "")
        else:
            payload["message"] = str(msg)
        return json.dumps(payload, default=str, sort_keys=True), kwargs

    def log(
        self,
        level: int,
        msg: Any,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        if self.isEnabledFor(level):
            kwargs["_level"] = logging.getLevelName(level)
            msg, kwargs = self.process(msg, kwargs)
            self.logger.log(level, msg, *args, **kwargs)


def get_logger(stage: str) -> JsonLoggerAdapter:
    logger = logging.getLogger(f"{SERVICE_NAME}.{stage}")
    logger.setLevel(logging.INFO)
    return JsonLoggerAdapter(logger, {"stage": stage})
