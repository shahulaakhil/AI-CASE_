"""Court date and case status tracker, plus the eCourts CNR lookup."""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime
from typing import Any

import requests

from .. import db

STATUSES = ("Pending", "Active", "Arguments", "Reserved", "Disposed", "Stayed", "Withdrawn")
PRIORITIES = ("Low", "Normal", "High", "Critical")

_ECOURTS_URL = "https://services.ecourts.gov.in/ecourtindia_v6/cases/case_status_cnr"
_ECOURTS_TIMEOUT = 20
_CNR_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{2}\d{6}\d{4}$")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean_date(value: str) -> str:
    """Accept DD-MM-YYYY, DD/MM/YYYY or ISO and store ISO. Empty stays empty."""
    raw = (value or "").strip()
    if not raw:
        return ""
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw).date().isoformat()
    except ValueError:
        return raw


def _days_away(next_date: str) -> int | None:
    if not next_date:
        return None
    try:
        return (date.fromisoformat(next_date) - date.today()).days
    except ValueError:
        return None


def _decorate(case: dict) -> dict:
    case = db.row_to_case(case)
    case["days_away"] = _days_away(case.get("next_date", ""))
    case["hearing_count"] = len(case.get("hearings") or [])
    return case


def list_cases() -> list[dict]:
    rows = db.query(
        "SELECT * FROM cases ORDER BY CASE WHEN next_date = '' THEN 1 ELSE 0 END, "
        "next_date ASC, created_at DESC"
    )
    return [_decorate(row) for row in rows]


def get_case(case_id: str) -> dict | None:
    rows = db.query("SELECT * FROM cases WHERE id = ?", (case_id,))
    return _decorate(rows[0]) if rows else None


def create_case(payload: dict) -> dict:
    case_id = uuid.uuid4().hex[:12]
    now = _now()
    record = {
        "id": case_id,
        "case_name": (payload.get("case_name") or "").strip(),
        "court": (payload.get("court") or "").strip(),
        "case_number": (payload.get("case_number") or "").strip(),
        "cnr_number": (payload.get("cnr_number") or "").strip().upper(),
        "parties": (payload.get("parties") or "").strip(),
        "next_date": _clean_date(payload.get("next_date", "")),
        "stage": (payload.get("stage") or "").strip(),
        "status": (payload.get("status") or "Pending").strip(),
        "priority": (payload.get("priority") or "Normal").strip(),
        "notes": (payload.get("notes") or "").strip(),
        "hearings": json.dumps([]),
        "created_at": now,
        "updated_at": now,
    }
    db.execute(
        "INSERT INTO cases (id, case_name, court, case_number, cnr_number, parties, "
        "next_date, stage, status, priority, notes, hearings, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(record[column] for column in db.COLUMNS),
    )
    return _decorate(record)


_EDITABLE = (
    "case_name", "court", "case_number", "cnr_number", "parties", "next_date",
    "stage", "status", "priority", "notes",
)


def update_case(case_id: str, payload: dict) -> dict | None:
    existing = get_case(case_id)
    if existing is None:
        return None

    assignments: list[str] = []
    values: list[Any] = []
    for field in _EDITABLE:
        if field not in payload:
            continue
        value = payload[field]
        value = "" if value is None else str(value).strip()
        if field == "next_date":
            value = _clean_date(value)
        if field == "cnr_number":
            value = value.upper()
        assignments.append(f"{field} = ?")
        values.append(value)

    if not assignments:
        return existing

    assignments.append("updated_at = ?")
    values.append(_now())
    values.append(case_id)
    db.execute(f"UPDATE cases SET {', '.join(assignments)} WHERE id = ?", tuple(values))
    return get_case(case_id)


def delete_case(case_id: str) -> bool:
    return db.execute("DELETE FROM cases WHERE id = ?", (case_id,)) > 0


def add_hearing(
    case_id: str,
    hearing_date: str,
    outcome: str = "",
    next_date: str = "",
) -> dict | None:
    case = get_case(case_id)
    if case is None:
        return None

    hearings = case.get("hearings") or []
    hearings.append(
        {
            "id": uuid.uuid4().hex[:8],
            "date": _clean_date(hearing_date),
            "outcome": (outcome or "").strip(),
            "recorded_at": _now(),
        }
    )
    hearings.sort(key=lambda item: item.get("date", ""), reverse=True)

    if next_date:
        db.execute(
            "UPDATE cases SET hearings = ?, next_date = ?, updated_at = ? WHERE id = ?",
            (json.dumps(hearings), _clean_date(next_date), _now(), case_id),
        )
    else:
        db.execute(
            "UPDATE cases SET hearings = ?, updated_at = ? WHERE id = ?",
            (json.dumps(hearings), _now(), case_id),
        )
    return get_case(case_id)


def delete_hearing(case_id: str, hearing_id: str) -> dict | None:
    case = get_case(case_id)
    if case is None:
        return None
    hearings = [h for h in (case.get("hearings") or []) if h.get("id") != hearing_id]
    db.execute(
        "UPDATE cases SET hearings = ?, updated_at = ? WHERE id = ?",
        (json.dumps(hearings), _now(), case_id),
    )
    return get_case(case_id)


def upcoming(days_ahead: int = 30) -> list[dict]:
    results = []
    for case in list_cases():
        days = case.get("days_away")
        if days is None or days < 0 or days > days_ahead:
            continue
        results.append(case)
    return sorted(results, key=lambda case: case["days_away"])


def overdue() -> list[dict]:
    results = [
        case
        for case in list_cases()
        if case.get("days_away") is not None
        and case["days_away"] < 0
        and case.get("status") not in ("Disposed", "Withdrawn")
    ]
    return sorted(results, key=lambda case: case["days_away"], reverse=True)


def summary() -> dict[str, Any]:
    cases = list_cases()
    active = [c for c in cases if c.get("status") not in ("Disposed", "Withdrawn")]
    this_week = [
        c for c in cases if c.get("days_away") is not None and 0 <= c["days_away"] <= 7
    ]
    return {
        "total": len(cases),
        "active": len(active),
        "this_week": len(this_week),
        "overdue": len(overdue()),
        "hearings_logged": sum(c.get("hearing_count", 0) for c in cases),
    }


def valid_cnr(cnr: str) -> bool:
    return bool(_CNR_RE.match((cnr or "").strip().upper()))


def fetch_ecourts_status(cnr_number: str) -> dict:
    """Query the eCourts public CNR service.

    eCourts frequently blocks automated access and requires a captcha, so the
    caller must treat a failure here as normal and fall back to manual entry.
    """
    cnr = (cnr_number or "").strip().upper()
    if len(cnr) < 16:
        return {
            "ok": False,
            "error": "A CNR number is 16 characters, for example DLHC010123452024.",
        }

    try:
        response = requests.post(
            _ECOURTS_URL,
            data={"cino": cnr},
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; LitigatAI/1.0)",
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=_ECOURTS_TIMEOUT,
        )
    except requests.Timeout:
        return {
            "ok": False,
            "error": "eCourts did not respond in time. Enter the details manually for now.",
        }
    except requests.RequestException as exc:
        return {"ok": False, "error": f"eCourts could not be reached: {exc}"}

    if response.status_code != 200:
        return {
            "ok": False,
            "error": (
                f"eCourts returned HTTP {response.status_code}. The public service is often "
                "captcha protected, so manual entry is the reliable route."
            ),
        }

    try:
        return {"ok": True, "data": response.json()}
    except ValueError:
        return {
            "ok": False,
            "error": (
                "eCourts returned a captcha page rather than data. Look the case up on the "
                "eCourts portal and paste the details into the form."
            ),
        }
