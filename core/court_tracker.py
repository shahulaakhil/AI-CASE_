"""Tool 7: Court Date & Case Status Tracker.

Two modes:
1. eCourts integration — fetch live status from ecourts.gov.in public service
2. Manual tracker — store case details + hearing dates in local JSON

Storage: data/court_cases.json
"""
from __future__ import annotations

import json
import re
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import requests

from core import config

_CASES_FILE = config.DATA_DIR / "court_cases.json"

# eCourts public endpoint (no auth required for case status by CNR)
_ECOURTS_CNR_URL = "https://services.ecourts.gov.in/ecourtindia_v6/cases/case_status_cnr"
_ECOURTS_TIMEOUT = 15


def _load_cases() -> list[dict]:
    if _CASES_FILE.exists():
        try:
            return json.loads(_CASES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_cases(cases: list[dict]) -> None:
    _CASES_FILE.write_text(json.dumps(cases, indent=2, default=str), encoding="utf-8")


def get_all_cases() -> list[dict]:
    return _load_cases()


def add_case(
    case_name: str,
    court: str,
    case_number: str,
    cnr_number: str = "",
    parties: str = "",
    next_date: str = "",
    notes: str = "",
) -> dict:
    cases = _load_cases()
    case = {
        "id": str(len(cases) + 1).zfill(4),
        "case_name": case_name,
        "court": court,
        "case_number": case_number,
        "cnr_number": cnr_number,
        "parties": parties,
        "next_date": next_date,
        "notes": notes,
        "hearings": [],
        "status": "Pending",
        "added_on": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
    }
    cases.append(case)
    _save_cases(cases)
    return case


def update_case(case_id: str, **updates) -> Optional[dict]:
    cases = _load_cases()
    for case in cases:
        if case["id"] == case_id:
            case.update(updates)
            case["last_updated"] = datetime.now().isoformat()
            _save_cases(cases)
            return case
    return None


def add_hearing(case_id: str, hearing_date: str, outcome: str = "", next_date: str = "") -> Optional[dict]:
    cases = _load_cases()
    for case in cases:
        if case["id"] == case_id:
            case["hearings"].append({
                "date": hearing_date,
                "outcome": outcome,
                "added_on": datetime.now().isoformat(),
            })
            if next_date:
                case["next_date"] = next_date
            case["last_updated"] = datetime.now().isoformat()
            _save_cases(cases)
            return case
    return None


def delete_case(case_id: str) -> bool:
    cases = _load_cases()
    updated = [c for c in cases if c["id"] != case_id]
    if len(updated) == len(cases):
        return False
    _save_cases(updated)
    return True


def fetch_ecourts_status(cnr_number: str) -> dict:
    """Attempt to fetch case status from eCourts using CNR number.

    CNR format: XXDDDDDDDDYYYY (e.g., MHAU01234562024)
    Returns dict with status, next_date, or an error key.
    """
    if not cnr_number or len(cnr_number) < 10:
        return {"error": "Invalid CNR number format."}

    # eCourts public API endpoint (case status by CNR)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"cino": cnr_number.strip().upper()}
        resp = requests.post(
            _ECOURTS_CNR_URL,
            data=data,
            headers=headers,
            timeout=_ECOURTS_TIMEOUT,
        )
        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                return {"error": "eCourts returned non-JSON response. The service may be temporarily unavailable."}
        else:
            return {"error": f"eCourts returned HTTP {resp.status_code}. Try again or enter details manually."}
    except requests.Timeout:
        return {"error": "eCourts request timed out. The service may be slow. Try manual entry."}
    except requests.RequestException as e:
        return {"error": f"Could not reach eCourts: {e}"}


def get_upcoming_dates(days_ahead: int = 30) -> list[dict]:
    """Get all cases with hearings in the next N days."""
    cases = _load_cases()
    today = date.today()
    upcoming = []
    for case in cases:
        nd = case.get("next_date", "")
        if not nd:
            continue
        try:
            hearing_date = datetime.fromisoformat(nd).date()
            delta = (hearing_date - today).days
            if 0 <= delta <= days_ahead:
                upcoming.append({**case, "days_away": delta})
        except Exception:
            pass
    return sorted(upcoming, key=lambda x: x["days_away"])
