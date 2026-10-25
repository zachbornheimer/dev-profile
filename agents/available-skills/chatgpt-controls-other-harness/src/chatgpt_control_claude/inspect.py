from __future__ import annotations

from pathlib import Path
import json
import zipfile


def read_report(zip_path: Path) -> dict:
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        if "report.json" not in names:
            raise ValueError("ZIP has no report.json")
        return json.loads(z.read("report.json"))


def summarize_report(report: dict) -> str:
    fields = [
        ("uuid", report.get("uuid")),
        ("ticket", report.get("ticket")),
        ("operation", report.get("operation")),
        ("outcome", report.get("outcome")),
        ("acceptance_proved", report.get("acceptance_proved")),
        ("error", report.get("error")),
    ]
    return "\n".join(f"{k}: {v}" for k, v in fields if v is not None)
