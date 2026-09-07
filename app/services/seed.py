"""Sample matters for the case tracker, used on a demo deployment.

Render's free plan has an ephemeral filesystem, so the SQLite tracker starts
empty on every deploy and restart, and a visitor lands on a blank screen with
nothing to look at. Setting DEMO_SEED=1 inserts a handful of realistic Indian
matters at start up, but only into a tracker that is genuinely empty, so this
can never overwrite real data on a deployment that uses Postgres.

Dates are computed relative to the day the app boots. That matters: a fixed
date would drift into the past and the "upcoming hearings" view would be empty
again a month later.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from . import tracker

log = logging.getLogger("litigatai.seed")


def _in(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


# Offsets are chosen so the dashboard shows an overdue matter, something this
# week, something later in the month, and a disposed matter with no next date.
SAMPLE_CASES: tuple[dict, ...] = (
    {
        "case_name": "Meera Krishnan v. Sunrise Realty Pvt Ltd",
        "court": "District Consumer Disputes Redressal Commission, Pune",
        "case_number": "CC/114/2024",
        "cnr_number": "MHPU010114452024",
        "parties": "Meera Krishnan (Complainant) v. Sunrise Realty Pvt Ltd (Opposite Party)",
        "next_date": _in(4),
        "stage": "Evidence of the complainant",
        "status": "Active",
        "priority": "High",
        "notes": (
            "Possession of Flat B-704 was due on 1 March 2023 and has still not been "
            "handed over. Refund with interest claimed under section 18 of the RERA "
            "Act 2016 read with section 35 of the Consumer Protection Act 2019. The "
            "opposite party pleads a municipal stop work notice as force majeure."
        ),
        "hearings": [
            {"date": _in(-38), "outcome": "Complaint admitted. Notice issued to the opposite party."},
            {"date": _in(-17), "outcome": "Written version filed. Complainant granted time to file affidavit of evidence."},
        ],
    },
    {
        "case_name": "State of Maharashtra v. Rakesh Deshmukh",
        "court": "Court of Sessions, Greater Bombay",
        "case_number": "SC/482/2023",
        "cnr_number": "MHCC020482392023",
        "parties": "State of Maharashtra (Prosecution) v. Rakesh Deshmukh (Accused)",
        "next_date": _in(-3),
        "stage": "Framing of charge",
        "status": "Arguments",
        "priority": "Critical",
        "notes": (
            "Application for discharge under section 227 CrPC pending. Chargesheet "
            "relies almost entirely on a section 27 Evidence Act disclosure. Bail "
            "granted on 12 January subject to weekly attendance."
        ),
        "hearings": [
            {"date": _in(-52), "outcome": "Chargesheet supplied to the accused under section 207 CrPC."},
            {"date": _in(-24), "outcome": "Discharge application filed. Prosecution to reply."},
            {"date": _in(-3), "outcome": "Part heard on the discharge application. Adjourned for the remainder."},
        ],
    },
    {
        "case_name": "Anand Textiles LLP v. Commissioner of GST, Surat",
        "court": "High Court of Gujarat, Ahmedabad",
        "case_number": "SCA/8891/2024",
        "cnr_number": "GJHC240889112024",
        "parties": "Anand Textiles LLP (Petitioner) v. Commissioner of GST, Surat (Respondent)",
        "next_date": _in(19),
        "stage": "Admission",
        "status": "Pending",
        "priority": "Normal",
        "notes": (
            "Writ petition under Article 226 against blocking of the electronic credit "
            "ledger under rule 86A without a pre decisional hearing. Interim relief "
            "sought to unblock input tax credit of Rs 1.42 crore."
        ),
        "hearings": [
            {"date": _in(-9), "outcome": "Notice issued to the respondent, returnable in three weeks."},
        ],
    },
    {
        "case_name": "Farida Sheikh v. Imtiaz Sheikh",
        "court": "Family Court, Bandra, Mumbai",
        "case_number": "PA/276/2025",
        "cnr_number": "MHFC030276152025",
        "parties": "Farida Sheikh (Applicant) v. Imtiaz Sheikh (Respondent)",
        "next_date": _in(11),
        "stage": "Interim maintenance",
        "status": "Active",
        "priority": "High",
        "notes": (
            "Application under section 125 CrPC for maintenance for the applicant and "
            "one minor child. Respondent's salary certificate called for. Rajnesh v. "
            "Neha (2021) 2 SCC 324 affidavit of assets filed by both sides."
        ),
        "hearings": [
            {"date": _in(-30), "outcome": "Both sides directed to file affidavits of assets and liabilities."},
        ],
    },
    {
        "case_name": "Vikram Rao v. Deccan Logistics Ltd",
        "court": "National Company Law Tribunal, Hyderabad",
        "case_number": "CP/119/HDB/2023",
        "parties": "Vikram Rao (Operational Creditor) v. Deccan Logistics Ltd (Corporate Debtor)",
        "next_date": "",
        "stage": "Disposed",
        "status": "Disposed",
        "priority": "Low",
        "notes": (
            "Section 9 IBC petition withdrawn after a settlement recorded on the last "
            "date. Retained for the limitation record only."
        ),
        "hearings": [
            {"date": _in(-96), "outcome": "Petition admitted for hearing on admission."},
            {"date": _in(-61), "outcome": "Settlement terms filed. Petition disposed as withdrawn."},
        ],
    },
)


def seed_if_empty() -> int:
    """Insert the sample matters when the tracker holds nothing. Returns count."""
    try:
        existing = tracker.list_cases()
    except Exception as exc:  # noqa: BLE001 - never block start up on the demo data
        log.warning("Could not read the tracker, so nothing was seeded: %s", exc)
        return 0

    if existing:
        log.info("Tracker already holds %d cases, so nothing was seeded.", len(existing))
        return 0

    inserted = 0
    for sample in SAMPLE_CASES:
        hearings = sample.get("hearings") or []
        payload = {k: v for k, v in sample.items() if k != "hearings"}
        try:
            case = tracker.create_case(payload)
            for hearing in hearings:
                # next_date is already set on the case, so it is not passed here.
                tracker.add_hearing(case["id"], hearing["date"], hearing.get("outcome", ""))
            inserted += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("Sample case %r could not be inserted: %s", sample["case_name"], exc)

    log.info("Seeded %d sample matters into an empty tracker.", inserted)
    return inserted
