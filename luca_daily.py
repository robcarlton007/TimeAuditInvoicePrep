# -*- coding: utf-8 -*-
"""
luca_daily.py — Luca Daily Automation (headless, cloud-ready)
Runs every morning via GitHub Actions. Audits the prior business day,
generates personalized Claude messages, and delivers via Gmail + Twilio WhatsApp.
"""

import os, sys, json, re, smtplib, base64, traceback
import urllib.request, urllib.parse
from datetime import datetime, timedelta, date
from collections import defaultdict
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
import anthropic

# ── CONFIG — all from environment variables ────────────────────────────────────
AJERA_URL     = os.environ.get(
    "AJERA_URL",
    "https://ajera.com/V004613/AjeraAPI.ashx"
    "?ew0KICAiQ2xpZW50SUQiOiA0NjEzLA0KICAiRGF0YWJhc2VJRCI6IDE5NzI2LA0K"
    "ICAiSXNTYW1wbGVEYXRhIjogZmFsc2UNCn0%3d"
)
AJERA_USER    = os.environ.get("AJERA_USER",    "ClaudeTime247")
AJERA_PASS    = os.environ.get("AJERA_PASS",    "GuinneaPig247!")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GMAIL_USER     = os.environ.get("GMAIL_USER",         "")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASSWORD",  "")
TWILIO_SID     = os.environ.get("TWILIO_ACCOUNT_SID",  "")
TWILIO_TOKEN   = os.environ.get("TWILIO_AUTH_TOKEN",   "")
TWILIO_FROM_WA = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
HR_EMAIL       = "hr@carlton-edwards.com"
HR_NAME        = "Kim Dierking"

# ── CONSTANTS — copied from audit_gui.py ──────────────────────────────────────
API_ENDPOINT = AJERA_URL  # resolved at module load; env var may override default

DEPARTMENTS = {
    2: "Asheville",   # Carlton Architecture PA
    4: "Nashville",   # Carlton Edwards PLLC
    6: "Memphis",     # Carlton Edwards PLLC
    7: "Consultant",
}

COMPANIES = {
    "Carlton Architecture PA":  [2],
    "Carlton Edwards PLLC":     [4, 6],
}

MIN_HOURS = 8.0

EMP_WEEKLY_HOURS = {
    "Gordon Shisler": 32.0,
}

OVERHEAD_KW = [
    "overhead", "general", "admin", "vacation", "holiday",
    "pto", "sick", "training", "business development", "bd", "marketing", "office",
]
PTO_KW = {"vacation", "holiday", "pto", "sick", "personal"}

# ── LOCAL CACHE — mirrors audit_gui.py ────────────────────────────────────────
# The GUI writes ~/Documents/Luca/ajera_cache.json after every sync.
# luca_daily.py reads it first; only calls the live API when the cache is absent
# or older than CACHE_MAX_AGE hours (same threshold as the GUI).
CACHE_DIR     = Path.home() / "Documents" / "Luca"
CACHE_PATH    = CACHE_DIR / "ajera_cache.json"
CACHE_MAX_AGE = 24  # hours


def load_daily_cache() -> dict:
    """Return the parsed cache dict, or {} if the file is missing or unreadable."""
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[CACHE] Could not read cache: {exc}")
    return {}


def daily_cache_age_hours() -> float:
    """Return how many hours old the cache is; inf if missing or unparseable."""
    cache = load_daily_cache()
    ts = cache.get("last_synced")
    if not ts:
        return float("inf")
    try:
        synced = datetime.fromisoformat(ts)
        return (datetime.now() - synced).total_seconds() / 3600
    except Exception:
        return float("inf")


# ── COLLABORATION DETECTION PATTERNS ──────────────────────────────────────────
SYNC_PATTERNS = [
    r'\bmet\s+with\b',
    r'\bmeeting\s+with\b',
    r'\b(?:had\s+a?\s+)?(?:phone\s+|video\s+)?call\s+with\b',
    r'\bvideo\s+(?:call|meeting|chat)\b',
    r'\bzoomed?\b',
    r'\bteams\s+(?:call|meeting)\b',
    r'\bspoke\s+with\b',
    r'\btalked?\s+(?:to|with)\b',
    r'\bdiscussed?\s+with\b',
    r'\bdiscussed?\b',
    r'\breviewed?\s+with\b',
    r'\bworked?\s+(?:with|together)\b',
    r'\bworking\s+(?:session|meeting)\b',
    r'\bsession\s+with\b',
    r'\bsynced?\s*(?:up\s*)?with\b',
    r'\bcheck\s*-?\s*in\s+with\b',
    r'\bwalk(?:ed|ing)?\s+(?:\w+\s+)?through\s+with\b',
    r'\bpresented?\s+to\b',
    r'\bcollaborated?\s+(?:with|on)\b',
    r'\btogether\b',
    r'\bjoint\s+(?:meeting|session|call|review|work)\b',
    r'\bkick\s*off\b',
    r'\bstand\s*-?\s*up\b',
    r'\bworkshop\b',
    r'\bcharrette\b',
    r'\bpair(?:ed|ing)?\s+(?:with|on)\b',
    r'\bconsulted?\s+with\b',
    r'\bcoordinated?\s+with\b',
    r'\bco\s*-?\s*work(?:ed|ing)?\b',
    r'\bin\s+person\s+with\b',
]

# ── API HELPERS — copied from audit_gui.py ────────────────────────────────────

def api_post(payload):
    r = requests.post(
        API_ENDPOINT,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=90,
    )
    r.raise_for_status()
    result = r.json()
    if result.get("ResponseCode") not in (None, 0, "0", 200, "200"):
        raise RuntimeError(result.get("Message", str(result)))
    return result


def login(version=1):
    resp = api_post({
        "Method": "CreateAPISession",
        "Username": AJERA_USER,
        "Password": AJERA_PASS,
        "APIVersion": version,
    })
    return resp["Content"]["SessionToken"]


def logout(token):
    try:
        api_post({"Method": "EndAPISession", "SessionToken": token})
    except Exception:
        pass


def get_employees(token):
    resp = api_post({
        "Method": "ListEmployees",
        "SessionToken": token,
        "MethodArguments": {"FilterByStatus": ["Active"]},
    })
    return resp.get("Content", {}).get("Employees", [])


def get_companies(token):
    resp = api_post({
        "Method": "ListCompanies",
        "SessionToken": token,
        "MethodArguments": {"FilterByStatus": ["Active"]},
    })
    return resp.get("Content", {}).get("Companies", [])


def get_departments(token):
    resp = api_post({
        "Method": "ListDepartments",
        "SessionToken": token,
        "MethodArguments": {"FilterByStatus": ["Active"]},
    })
    return resp.get("Content", {}).get("Departments", [])


def get_activities(token):
    resp = api_post({
        "Method": "ListActivities",
        "SessionToken": token,
        "MethodArguments": {"FilterByStatus": ["Active"]},
    })
    return resp.get("Content", {}).get("Activities", [])


def get_project_list(token):
    resp = api_post({
        "Method": "ListProjects",
        "SessionToken": token,
        "MethodArguments": {"FilterByStatus": ["Active", "Preliminary", "Hold"]},
    })
    return resp.get("Content", {}).get("Projects", [])


def get_timesheet_list(token, start, end):
    resp = api_post({
        "Method": "ListTimesheets",
        "SessionToken": token,
        "MethodArguments": {
            "FilterByEarliestTimesheetDate": str(start),
            "FilterByLatestTimesheetDate":   str(end),
        },
    })
    return resp.get("Content", {}).get("Timesheets", [])


def get_timesheet_detail(token, keys, batch_size=10):
    results = []
    for i in range(0, len(keys), batch_size):
        chunk = keys[i:i + batch_size]
        resp = api_post({
            "Method": "GetTimesheets",
            "SessionToken": token,
            "MethodArguments": {"RequestedTimesheets": chunk},
        })
        results.extend(resp.get("Content", {}).get("Timesheets", []))
    return results


# ── DATE UTILS — copied from audit_gui.py ─────────────────────────────────────

def d_to_date(ts_date_str, d_index):
    """Ajera TimesheetDate = Friday; D1=Sat … D7=Fri"""
    ts = datetime.strptime(ts_date_str[:10], "%Y-%m-%d").date()
    return ts - timedelta(days=6) + timedelta(days=d_index - 1)


def payroll_week_start(dt):
    """Return the Saturday that begins the payroll week containing dt."""
    return dt - timedelta(days=(dt.weekday() - 5) % 7)


def daily_min_hours(emp_name):
    """Return the per-day minimum hours threshold for this employee."""
    weekly = EMP_WEEKLY_HOURS.get(emp_name, MIN_HOURS * 5)
    return weekly / 5


def _has_sync_pattern(note):
    """True if the note contains a synchronous-collaboration indicator."""
    return any(re.search(p, note, re.IGNORECASE) for p in SYNC_PATTERNS)


def _is_possessive_match(note, match):
    """True if this regex match is immediately followed by 's (possessive form)."""
    after = note[match.end():match.end() + 3]
    return bool(re.match(r"'s\b", after))


# ── AUDIT CORE — copied from audit_gui.py ─────────────────────────────────────

def run_audit(start, end, emp_dept_map, employees=None):
    """Returns (flags, by_employee, by_project, prior_by_emp, emp_week_totals, employees).

    Pass ``employees`` (the ListEmployees list) to skip the live API call for
    employee data — used when the caller already loaded the cache.
    If omitted, a v1 API session is opened to fetch employees live.
    """
    # Fetch three extra payroll weeks before start:
    #   1 week back  — prior-week totals for the incomplete-day flag
    #   2-3 weeks back — rolling trend data passed to Ask Luca
    query_start = payroll_week_start(start) - timedelta(days=21)

    # Only open a v1 session if we weren't given a pre-fetched employee list.
    need_v1 = employees is None
    t1 = login(1) if need_v1 else None
    t2 = login(2)
    try:
        if need_v1:
            employees = get_employees(t1)
        emp_name_map = {
            e["EmployeeKey"]: f"{e.get('FirstName','')} {e.get('LastName','')}".strip()
            for e in employees
        }
        ts_list  = get_timesheet_list(t2, query_start, end)
        ts_keys  = [t["Timesheet Key"] for t in ts_list if t.get("Timesheet Key")]
        detailed = get_timesheet_detail(t2, ts_keys) if ts_keys else []
    finally:
        if t1:
            logout(t1)
        logout(t2)

    # name part (lowercase first/last, min 3 chars) -> list of employee keys
    name_part_to_eks = defaultdict(list)
    for _e in employees:
        _ek = _e["EmployeeKey"]
        for _part in [(_e.get("FirstName") or "").strip(), (_e.get("LastName") or "").strip()]:
            if len(_part) >= 3:
                name_part_to_eks[_part.lower()].append(_ek)

    flags = {
        "missing_notes": [], "incomplete_days": [],
        "full_overhead": [], "collab": [], "teamwork": [],
    }
    by_employee     = defaultdict(lambda: defaultdict(list))
    prior_by_emp    = defaultdict(lambda: defaultdict(list))
    by_project      = defaultdict(lambda: defaultdict(list))
    emp_day_entries = defaultdict(lambda: defaultdict(list))
    emp_week_totals = defaultdict(lambda: defaultdict(float))

    for sheet in detailed:
        ek    = sheet.get("EmployeeKey")
        ename = emp_name_map.get(ek, f"#{ek}")
        dept  = emp_dept_map.get(ek, 7)
        ts_ds = str(sheet.get("TimesheetDate", ""))

        day_hrs  = defaultdict(float)
        day_oh   = defaultdict(float)
        day_note = defaultdict(bool)
        day_ents = defaultdict(list)

        for entry in (sheet.get("Overhead", {}).get("Detail") or []):
            desc = entry.get("Timesheet Overhead Group Detail", "")
            for d in range(1, 8):
                hrs  = float(entry.get(f"D{d} Regular") or 0)
                note = (entry.get(f"D{d} Notes") or "").strip()
                if hrs <= 0:
                    continue
                dt = d_to_date(ts_ds, d)
                day_hrs[dt]  += hrs
                day_oh[dt]   += hrs
                if note:
                    day_note[dt] = True
                day_ents[dt].append({
                    "type": "overhead", "desc": desc,
                    "hrs": hrs, "note": note, "dept": dept,
                })

        for entry in (sheet.get("Project", {}).get("Detail") or []):
            pd   = entry.get("Project Description", "")
            ph   = entry.get("Phase Description", "")
            act  = entry.get("Activity", "")
            pkey = entry.get("Project Key")
            for d in range(1, 8):
                reg  = float(entry.get(f"D{d} Regular")  or 0)
                ovt  = float(entry.get(f"D{d} Overtime") or 0)
                note = (entry.get(f"D{d} Notes") or "").strip()
                hrs  = reg + ovt
                if hrs <= 0:
                    continue
                dt = d_to_date(ts_ds, d)
                day_hrs[dt]  += hrs
                if note:
                    day_note[dt] = True
                e = {
                    "type": "project", "desc": pd, "phase": ph,
                    "activity": act, "hrs": hrs, "note": note,
                    "dept": dept, "pkey": pkey,
                }
                day_ents[dt].append(e)
                by_project[pd][ename].append({
                    "date": dt, "phase": ph, "activity": act,
                    "hrs": hrs, "note": note, "dept": dept,
                })

        for dt in sorted(day_hrs):
            total = day_hrs[dt]
            ws    = payroll_week_start(dt)
            emp_week_totals[ename][ws] += total

            if dt < start:
                for e in day_ents[dt]:
                    prior_by_emp[ename][dt].append(e)
                continue

            lbl  = dt.strftime("%a %m/%d")
            ents = day_ents[dt]

            for e in ents:
                by_employee[ename][dt].append(e)
                emp_day_entries[ek][dt].append({
                    "proj":     e["desc"] if e["type"] == "project" else f"[Overhead] {e['desc']}",
                    "phase":    e.get("phase", ""),
                    "activity": e.get("activity", ""),
                    "hrs":      e["hrs"],
                    "note":     e["note"],
                    "pkey":     e.get("pkey"),
                })

            if dt.weekday() < 5:
                day_min = daily_min_hours(ename)
                if total < day_min:
                    flags["incomplete_days"].append({
                        "emp": ename, "dept": dept, "date": lbl,
                        "hrs": total, "miss": round(day_min - total, 2),
                        "_week_start": ws,
                        "week_total": None, "prior_week_total": None,
                    })
            for e in ents:
                if not e["note"]:
                    is_pto = (e["type"] == "overhead" and
                              any(kw in (e["desc"] or "").lower() for kw in PTO_KW))
                    flags["missing_notes"].append({
                        "emp": ename, "dept": dept, "date": lbl,
                        "desc": e["desc"], "hrs": e["hrs"],
                        "type": e["type"], "is_pto": is_pto,
                    })
                if e["note"] and _has_sync_pattern(e["note"]):
                    flags["teamwork"].append({
                        "employee": ename,
                        "dept":     dept,
                        "date":     dt,
                        "proj":     e["desc"] if e["type"] == "project" else f"[Overhead] {e['desc']}",
                        "phase":    e.get("phase", ""),
                        "activity": e.get("activity", ""),
                        "hours":    e["hrs"],
                        "note":     e["note"],
                    })
            if total > 0 and day_oh[dt] >= total * 0.9:
                oh_descs = ", ".join(
                    e["desc"] for e in ents if e["type"] == "overhead" and e["desc"]
                )
                flags["full_overhead"].append({
                    "emp": ename, "dept": dept, "date": lbl,
                    "hrs": total, "has_note": day_note[dt], "descs": oh_descs,
                })

    # Collaboration Citations
    seen_citations: set = set()
    for c_ek, c_date_map in emp_day_entries.items():
        c_ename = emp_name_map.get(c_ek, f"#{c_ek}")
        for c_dt, c_ents in c_date_map.items():
            c_lbl = c_dt.strftime("%a %m/%d")
            for c_ent in c_ents:
                c_note = c_ent.get("note", "")
                if not c_note:
                    continue
                if not _has_sync_pattern(c_note):
                    continue
                for name_part, m_eks in name_part_to_eks.items():
                    name_matches = list(re.finditer(
                        r'\b' + re.escape(name_part) + r'\b', c_note, re.IGNORECASE
                    ))
                    if not name_matches:
                        continue
                    has_non_possessive = any(
                        not _is_possessive_match(c_note, m) for m in name_matches
                    )
                    if not has_non_possessive:
                        continue
                    for m_ek in m_eks:
                        if m_ek == c_ek:
                            continue
                        cite_key = (c_ek, m_ek, c_dt.isoformat(), c_ent.get("pkey"))
                        if cite_key in seen_citations:
                            continue
                        seen_citations.add(cite_key)
                        m_ename = emp_name_map.get(m_ek, f"#{m_ek}")
                        flags["collab"].append({
                            "mentioned_emp": m_ename,
                            "cited_by":      c_ename,
                            "date":          c_lbl,
                            "date_obj":      c_dt,
                            "project":       c_ent.get("proj", ""),
                            "phase":         c_ent.get("phase", ""),
                            "activity":      c_ent.get("activity", ""),
                            "hours":         c_ent.get("hrs", 0),
                            "note":          c_note,
                        })

    # Back-fill weekly totals into incomplete_days flags
    for f in flags["incomplete_days"]:
        ws       = f.pop("_week_start")
        prior_ws = ws - timedelta(days=7)
        wt = emp_week_totals.get(f["emp"], {})
        f["week_total"]       = wt.get(ws, 0.0)
        f["prior_week_total"] = wt.get(prior_ws, 0.0)

    return flags, by_employee, by_project, prior_by_emp, emp_week_totals, employees


# ── NEW: EMPLOYEE DETAILS ──────────────────────────────────────────────────────

def get_employee_details(token, employee_keys, batch_size=20):
    """
    Calls GetEmployees to retrieve full employee detail including:
    IsSupervisor, IsPrincipal, SupervisorKey, Title, CompanyKey, DepartmentKey,
    and any email field if present.

    NOTE: Ajera field availability depends on your API version and configuration.
    Fields assumed to exist: IsSupervisor, IsPrincipal, SupervisorKey, Title.
    Verify against a live GetEmployees response if needed.
    """
    results = []
    for i in range(0, len(employee_keys), batch_size):
        chunk = employee_keys[i:i + batch_size]
        resp = api_post({
            "Method": "GetEmployees",
            "SessionToken": token,
            "MethodArguments": {"RequestedEmployees": chunk},
        })
        results.extend(resp.get("Content", {}).get("Employees", []))
    return results


# ── NEW: DATE HELPERS ──────────────────────────────────────────────────────────

def prior_business_day():
    """
    Returns the prior business day as a date object.
    Mon → Fri, Tue–Fri → yesterday, Sat/Sun → Fri.
    """
    today = date.today()
    # weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
    offset = {0: 3, 6: 2}.get(today.weekday(), 1)  # Mon=3 back, Sun=2 back, else 1
    return today - timedelta(days=offset)


# ── NEW: CONSECUTIVE MISSED DAYS ───────────────────────────────────────────────

def detect_consecutive_missed(emp_name, by_employee, prior_by_emp, check_date):
    """
    Counts consecutive business days (ending on check_date, going backwards)
    where emp_name logged zero entries. Capped at 3 for tier logic.
    """
    count = 0
    cursor = check_date
    for _ in range(7):
        if cursor.weekday() < 5:  # business day only
            has_entries = (
                bool(by_employee.get(emp_name, {}).get(cursor)) or
                bool(prior_by_emp.get(emp_name, {}).get(cursor))
            )
            if not has_entries:
                count += 1
            else:
                break
        cursor -= timedelta(days=1)
    return min(count, 3)


# ── NEW: EMPLOYEE MESSAGE CONTEXT ─────────────────────────────────────────────

def build_employee_context(emp_name, prior_day, flags, by_employee, prior_by_emp,
                            emp_week_totals, consecutive_missed, supervisor_name,
                            studio, is_missing=False):
    """
    Builds a structured plain-text block describing an employee's timesheet
    situation. Used as context for Claude's personalized message generation.
    """
    lines = []
    lines.append(f"EMPLOYEE: {emp_name}")
    lines.append(f"STUDIO: {studio}")
    lines.append(f"SUPERVISOR: {supervisor_name}")
    lines.append(f"DATE REVIEWED: {prior_day.strftime('%A, %B %d, %Y')}")
    lines.append("")

    # Prior day entries
    day_entries = by_employee.get(emp_name, {}).get(prior_day, [])
    if is_missing or not day_entries:
        lines.append("TIMESHEET STATUS: No entries logged for this day.")
    else:
        day_total = sum(e.get("hrs", 0) for e in day_entries)
        lines.append(f"TIMESHEET STATUS: Logged {day_total:.1f}h across {len(day_entries)} entry/entries.")
        lines.append("ENTRIES:")
        for e in day_entries:
            kind   = e.get("type", "")
            desc   = e.get("desc", "—")
            phase  = e.get("phase", "")
            act    = e.get("activity", "")
            hrs    = e.get("hrs", 0)
            note   = e.get("note", "").strip()
            label  = desc
            if phase:  label += f" / {phase}"
            if act:    label += f" [{act}]"
            lines.append(f"  - {label}: {hrs:.1f}h")
            if note:
                lines.append(f"    Note: \"{note}\"")
            else:
                lines.append(f"    Note: MISSING")

    lines.append("")

    # Flags for this employee
    mn  = [f for f in flags.get("missing_notes", [])   if f.get("emp") == emp_name]
    inc = [f for f in flags.get("incomplete_days", []) if f.get("emp") == emp_name]
    foh = [f for f in flags.get("full_overhead", [])   if f.get("emp") == emp_name]
    col = [f for f in flags.get("collab", [])          if f.get("mentioned_emp") == emp_name]
    tmw = [f for f in flags.get("teamwork", [])        if f.get("employee") == emp_name]

    if mn:
        blocked = [f for f in mn if not f.get("is_pto")]
        lines.append(f"MISSING NOTES: {len(blocked)} entry/entries missing notes (invoicing blocked).")
        for f in blocked:
            lines.append(f"  - {f['date']}: {f['desc']} ({f['hrs']}h, {f['type']})")

    if inc:
        for f in inc:
            lines.append(
                f"SHORT DAY: {f['date']} — {f['hrs']}h logged, "
                f"{f['miss']}h below threshold. "
                f"Week total so far: {f.get('week_total', 0):.1f}h "
                f"(prior week: {f.get('prior_week_total', 0):.1f}h)."
            )

    if foh:
        for f in foh:
            lines.append(
                f"FULL OVERHEAD DAY: {f['date']} — {f['hrs']}h, "
                f"all overhead ({f.get('descs', '—')}). "
                f"Has note: {'yes' if f.get('has_note') else 'no'}."
            )

    if col:
        lines.append(f"COLLABORATION CITATIONS: Mentioned by {len(col)} colleague(s) on collaborative work.")
        for c in col:
            lines.append(f"  - {c['cited_by']} cited {emp_name} on {c['date']}: \"{c['note'][:120]}\"")

    if tmw:
        lines.append(f"SYNC WORK LOGGED: {len(tmw)} collaborative entry/entries.")
        for t in tmw:
            lines.append(f"  - {t.get('proj', '—')} [{t.get('hours', 0):.1f}h]: \"{t.get('note', '')[:100]}\"")

    lines.append("")

    # Weekly context
    ws_current  = payroll_week_start(prior_day)
    ws_prior    = ws_current - timedelta(days=7)
    wt_map      = emp_week_totals.get(emp_name, {})
    week_so_far = wt_map.get(ws_current, 0.0)
    prior_week  = wt_map.get(ws_prior, 0.0)
    weekly_tgt  = EMP_WEEKLY_HOURS.get(emp_name, MIN_HOURS * 5)
    lines.append(f"WEEKLY HOURS (week starting {ws_current}): {week_so_far:.1f}h so far (target: {weekly_tgt:.0f}h/week)")
    lines.append(f"PRIOR WEEK TOTAL: {prior_week:.1f}h")
    lines.append("")

    # Prior weeks pattern summary
    prior_dates = sorted(prior_by_emp.get(emp_name, {}).keys(), reverse=True)
    if prior_dates:
        recent_prior = prior_dates[:10]
        short_days   = sum(
            1 for d in recent_prior
            if d.weekday() < 5 and
               sum(e.get("hrs", 0) for e in prior_by_emp[emp_name].get(d, [])) < daily_min_hours(emp_name)
        )
        no_note_days = sum(
            1 for d in recent_prior
            if any(not e.get("note", "").strip() and not e.get("is_pto")
                   for e in prior_by_emp[emp_name].get(d, []))
        )
        lines.append(f"RECENT HISTORY (prior 2–3 weeks, {len(recent_prior)} days sampled):")
        lines.append(f"  Short days: {short_days} of {len(recent_prior)}")
        lines.append(f"  Days with missing notes: {no_note_days} of {len(recent_prior)}")
    else:
        lines.append("RECENT HISTORY: No prior-period data available.")

    lines.append("")

    # Escalation
    tier_labels = {
        0: "Clean — no issues",
        1: "First missed day",
        2: "Second consecutive missed day",
        3: "Three or more consecutive missed days — serious pattern",
    }
    lines.append(f"CONSECUTIVE MISSED DAYS: {consecutive_missed}")
    lines.append(f"ESCALATION TIER: {consecutive_missed} — {tier_labels.get(consecutive_missed, 'Serious pattern')}")

    return "\n".join(lines)


# ── NEW: GENERATE EMPLOYEE MESSAGE ────────────────────────────────────────────

def generate_employee_message(emp_context, escalation_tier, client):
    """
    Calls Claude (claude-haiku-3-5) to write a personalized daily timesheet message.
    Returns plain text. Non-streaming for simplicity.
    """
    system_prompt = (
        "You are Luca, Carlton Edwards' timesheet intelligence assistant. "
        "You write daily timesheet review messages directly to employees. "
        "Your tone is: warm, collegial, analytically sharp, and fresh every day. "
        "You are not a bot sending a reminder. You are a knowledgeable colleague who looked at their work. "
        "NEVER use canned openers like 'This is a reminder that...' or 'Please be advised...' "
        "NEVER start two consecutive days with the same sentence structure. "
        "Focus on the most important issue first. Acknowledge what's right before what's wrong when appropriate. "
        "If there's nothing wrong, say so warmly and specifically — don't just say 'looks good.' "
        "Reference specific projects, phases, dates, and hours — make it feel personal, not generic. "
        "Write in plain text (not markdown). 3-5 sentences max for a clean day. Up to 8 sentences for a flagged day. "
        "End with something that moves them forward, not just a statement of the problem."
    )

    user_prompt = (
        f"Write a daily timesheet message for this employee.\n"
        f"Escalation tier: {escalation_tier} "
        f"(0=clean, 1=first miss, 2=second consecutive miss, 3+=serious pattern)\n\n"
        f"{emp_context}"
    )

    response = client.messages.create(
        model="claude-haiku-3-5",
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()


# ── NEW: SUPERVISOR CONTEXT ────────────────────────────────────────────────────

def build_supervisor_context(supervisor_name, team, target_date, emp_flags,
                              by_employee, prior_by_emp, emp_week_totals,
                              consecutive_map, missing_completely):
    """
    Builds a structured briefing block for Claude, covering the full team
    under this supervisor for the given target_date.
    """
    lines = []
    lines.append(f"SUPERVISOR: {supervisor_name}")
    lines.append(f"DATE: {target_date.strftime('%A, %B %d, %Y')}")
    lines.append(f"TEAM SIZE: {len(team)} employee(s)")
    lines.append("")

    team_issues  = 0
    missing_emps = []
    flagged_emps = []
    clean_emps   = []

    for emp_name in sorted(team):
        tier    = consecutive_map.get(emp_name, 0)
        e_flags = emp_flags[emp_name]
        mn      = [f for f in e_flags.get("missing_notes", []) if not f.get("is_pto")]
        inc     = e_flags.get("incomplete_days", [])
        foh     = e_flags.get("full_overhead", [])
        col     = e_flags.get("collab", [])
        missing = emp_name in missing_completely

        has_issues = missing or tier > 0 or mn or inc or foh
        if has_issues:
            team_issues += 1

        day_entries = by_employee.get(emp_name, {}).get(target_date, [])
        day_total   = sum(e.get("hrs", 0) for e in day_entries)

        ws_current  = payroll_week_start(target_date)
        ws_prior    = ws_current - timedelta(days=7)
        wt_map      = emp_week_totals.get(emp_name, {})
        week_so_far = wt_map.get(ws_current, 0.0)
        prior_week  = wt_map.get(ws_prior, 0.0)

        summary = f"  {emp_name}:"
        if missing:
            summary += " NO ENTRY (completely absent)"
        elif not day_entries:
            summary += " No entries on this date"
        else:
            summary += f" {day_total:.1f}h logged"
        summary += f" | Week: {week_so_far:.1f}h | Prior week: {prior_week:.1f}h"
        if tier > 0:
            summary += f" | TIER {tier} ESCALATION ({tier} consecutive missed)"
        if mn:
            summary += f" | {len(mn)} missing note(s)"
        if inc:
            summary += f" | {len(inc)} short day(s)"
        if foh:
            summary += f" | {len(foh)} full-overhead day(s)"
        if col:
            summary += f" | cited by {len(col)} colleague(s)"

        if has_issues:
            flagged_emps.append(summary)
        else:
            clean_emps.append(summary)

        if missing:
            missing_emps.append(emp_name)

    lines.append(f"TEAM STATUS SUMMARY: {team_issues} employee(s) with issues today")
    lines.append("")

    if flagged_emps:
        lines.append("FLAGGED EMPLOYEES:")
        lines.extend(flagged_emps)
        lines.append("")

    if clean_emps:
        lines.append("CLEAR EMPLOYEES:")
        lines.extend(clean_emps)
        lines.append("")

    if missing_emps:
        lines.append(f"COMPLETELY MISSING (no entry at all): {', '.join(missing_emps)}")
        lines.append("")

    # Cross-team collaboration check: look for teamwork flags that cross team members
    tmw_pairs = []
    for emp_name in team:
        for f in emp_flags[emp_name].get("teamwork", []):
            if f.get("date") == target_date:
                tmw_pairs.append(f"  {emp_name} logged sync work: {f.get('proj','—')} — \"{f.get('note','')[:100]}\"")
    if tmw_pairs:
        lines.append("INTRA-TEAM COLLABORATION LOGGED:")
        lines.extend(tmw_pairs)
        lines.append("")

    # Trend: how many had issues last week too?
    prior_pattern_emps = []
    for emp_name in team:
        prior_dates = sorted(prior_by_emp.get(emp_name, {}).keys(), reverse=True)
        if prior_dates:
            prior_short = sum(
                1 for d in prior_dates[:5]
                if d.weekday() < 5 and
                   sum(e.get("hrs", 0) for e in prior_by_emp[emp_name].get(d, [])) < daily_min_hours(emp_name)
            )
            if prior_short >= 2:
                prior_pattern_emps.append(f"  {emp_name}: {prior_short}/5 sampled prior days were short")
    if prior_pattern_emps:
        lines.append("RECURRING PATTERN (prior weeks, 5-day sample):")
        lines.extend(prior_pattern_emps)
        lines.append("")

    return "\n".join(lines)


# ── NEW: GENERATE SUPERVISOR REPORT ───────────────────────────────────────────

def generate_supervisor_report(supervisor_context, supervisor_name, client):
    """
    Calls Claude (claude-opus-4-6) to write the supervisor's daily team brief.
    Tone: analytical, concise, action-oriented.
    """
    system_prompt = (
        "You are Luca, Carlton Edwards' timesheet intelligence assistant. "
        "You write daily briefings for studio supervisors. "
        "Your tone is: analytical, precise, and action-oriented. "
        "You are not generating a table dump — write a brief that a busy supervisor can act on in 60 seconds. "
        "Lead with what needs immediate attention. Mention what's working too. "
        "Note escalation tiers clearly — a Tier 3 situation needs a different response than Tier 1. "
        "Reference specific employee names, projects, and hours. Never be vague. "
        "Write in plain text (not markdown). Aim for 6-10 sentences. "
        "End with a clear recommendation for the supervisor's next action."
    )

    user_prompt = (
        f"Write a daily team timesheet brief for supervisor {supervisor_name}.\n\n"
        f"{supervisor_context}"
    )

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=768,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()


# ── NEW: EMAIL ─────────────────────────────────────────────────────────────────

def send_email(to_addr, subject, body_text, cc=None):
    if not GMAIL_USER or not GMAIL_APP_PASS:
        print(f"[EMAIL SKIP] No Gmail credentials. Would send to {to_addr}: {subject}")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = to_addr
    if cc:
        msg["Cc"] = cc if isinstance(cc, str) else ", ".join(cc)
    msg.attach(MIMEText(body_text, "plain"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASS)
        recipients = [to_addr] + ([cc] if isinstance(cc, str) else (cc or []))
        smtp.sendmail(GMAIL_USER, recipients, msg.as_string())
    print(f"[EMAIL SENT] {to_addr} — {subject}")


# ── NEW: WHATSAPP ──────────────────────────────────────────────────────────────

def send_whatsapp(to_phone, message):
    """Send a WhatsApp message via Twilio REST API. to_phone format: '+1XXXXXXXXXX'."""
    if not TWILIO_SID or not TWILIO_TOKEN:
        print(f"[WHATSAPP SKIP] No Twilio credentials. Would send to {to_phone}")
        return
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
    data = urllib.parse.urlencode({
        "From": TWILIO_FROM_WA,
        "To":   f"whatsapp:{to_phone}",
        "Body": message,
    }).encode()
    credentials = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
    )
    urllib.request.urlopen(req)
    print(f"[WHATSAPP SENT] {to_phone}")


# ── NEW: LOAD CONTACTS ─────────────────────────────────────────────────────────

def build_contacts_from_ajera(emp_detail):
    """
    Builds the contact map directly from Ajera GetEmployees response.

    GetEmployees returns:
      - Email              — primary email address
      - PrimaryPhone       — first phone number
      - PrimaryPhoneDescription — label (e.g. "Mobile", "Work")
      - SecondaryPhone / SecondaryPhoneDescription
      - TertiaryPhone  / TertiaryPhoneDescription

    The WhatsApp phone is whichever phone entry has a description containing
    "mobile", "cell", or "whatsapp" (case-insensitive). Falls back to PrimaryPhone.

    Returns dict: {emp_name: {"email": str|None, "phone": str|None}}
    """
    contacts = {}
    for e in emp_detail:
        name  = f"{e.get('FirstName','').strip()} {e.get('LastName','').strip()}".strip()
        email = (e.get("Email") or "").strip() or None

        # Find the best mobile/WhatsApp number from up to three phone slots
        phone = None
        for slot_num, slot_desc in [
            ("PrimaryPhone",   "PrimaryPhoneDescription"),
            ("SecondaryPhone", "SecondaryPhoneDescription"),
            ("TertiaryPhone",  "TertiaryPhoneDescription"),
        ]:
            num  = (e.get(slot_num)  or "").strip()
            desc = (e.get(slot_desc) or "").lower()
            if not num:
                continue
            if any(kw in desc for kw in ("mobile", "cell", "whatsapp")):
                phone = num
                break
            if phone is None:
                phone = num  # take first available as fallback

        contacts[name] = {"email": email, "phone": phone}
        print(f"[CONTACTS] {name}: email={email} phone={phone}")

    return contacts


# ── MAIN ORCHESTRATION ─────────────────────────────────────────────────────────

def main():
    target_date = prior_business_day()
    print(f"[LUCA DAILY] Running for {target_date}")

    # ── 1. Load employee roster — cache-first ─────────────────────────────────
    # The GUI writes ~/Documents/Luca/ajera_cache.json on every sync.
    # If the cache is present and fresh enough we skip the live Ajera calls
    # for reference data entirely; timesheets are always fetched live.
    cache     = load_daily_cache()
    cache_age = daily_cache_age_hours()
    use_cache = bool(cache) and cache_age < CACHE_MAX_AGE

    if use_cache:
        emp_list   = cache.get("employees", [])
        emp_detail = cache.get("employee_details", [])
        if not emp_list or not emp_detail:
            # Cache exists but is missing the employee tables — fall through
            use_cache = False
        else:
            print(
                f"[LUCA DAILY] Using cached Ajera data "
                f"(synced {cache_age:.1f}h ago — {CACHE_PATH})"
            )

    if not use_cache:
        reason = "stale" if (bool(cache) and cache_age >= CACHE_MAX_AGE) else "missing"
        print(f"[LUCA DAILY] Cache {reason} ({cache_age:.1f}h old) — fetching live from Ajera")
        t1 = login(1)
        try:
            emp_list   = get_employees(t1)
            emp_keys   = [e["EmployeeKey"] for e in emp_list]
            emp_detail = get_employee_details(t1, emp_keys)
        finally:
            logout(t1)

    # Build lookup maps from full detail
    detail_by_key = {e["EmployeeKey"]: e for e in emp_detail}
    emp_name_map  = {
        e["EmployeeKey"]: f"{e.get('FirstName','')} {e.get('LastName','')}".strip()
        for e in emp_list
    }
    supervisor_map = {}   # emp_key -> supervisor_name
    is_supervisor  = {}   # emp_key -> bool
    is_principal   = {}   # emp_key -> bool
    for e in emp_detail:
        ek = e.get("EmployeeKey")
        is_supervisor[ek] = bool(e.get("IsSupervisor"))
        is_principal[ek]  = bool(e.get("IsPrincipal"))
        sup_key = e.get("SupervisorKey")
        if sup_key and sup_key in emp_name_map:
            supervisor_map[ek] = emp_name_map[sup_key]

    # emp_dept_map needed by run_audit
    emp_dept_map = {e["EmployeeKey"]: e.get("DepartmentKey", 7) for e in emp_detail}
    # Fall back to ListEmployees DepartmentKey if GetEmployees didn't return it
    for e in emp_list:
        ek = e["EmployeeKey"]
        if emp_dept_map.get(ek, 7) == 7 and e.get("DepartmentKey"):
            emp_dept_map[ek] = e["DepartmentKey"]

    # 2. Run audit for prior business day (pass employees so run_audit skips API)
    flags, by_employee, by_project, prior_by_emp, emp_week_totals, _ = run_audit(
        target_date, target_date, emp_dept_map, employees=emp_list
    )

    # 3. Detect employees completely missing for target_date
    active_emp_names = {
        f"{e.get('FirstName','')} {e.get('LastName','')}".strip()
        for e in emp_list
    }
    logged_names       = set(by_employee.keys())
    missing_completely = active_emp_names - logged_names
    # Only flag on business days
    if target_date.weekday() >= 5:
        missing_completely = set()

    # 4. Detect consecutive missed days per employee
    consecutive_map = {}
    for emp_name in active_emp_names:
        consecutive_map[emp_name] = detect_consecutive_missed(
            emp_name, by_employee, prior_by_emp, target_date
        )

    # 5. Build contacts from Ajera detail (email + best mobile/WhatsApp phone)
    contacts = build_contacts_from_ajera(emp_detail)
    client   = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None
    if not client:
        print("[LUCA DAILY] WARNING: No ANTHROPIC_API_KEY set. Messages will be skipped.")

    # 6. Build per-employee flags dict for easy lookup
    emp_flags = defaultdict(lambda: {
        "missing_notes": [], "incomplete_days": [],
        "full_overhead": [], "collab": [], "teamwork": [],
    })
    for f in flags["missing_notes"]:   emp_flags[f["emp"]]["missing_notes"].append(f)
    for f in flags["incomplete_days"]: emp_flags[f["emp"]]["incomplete_days"].append(f)
    for f in flags["full_overhead"]:   emp_flags[f["emp"]]["full_overhead"].append(f)
    for f in flags["collab"]:          emp_flags[f["mentioned_emp"]]["collab"].append(f)
    for f in flags["teamwork"]:        emp_flags[f["employee"]]["teamwork"].append(f)

    # 7. Generate and send employee messages
    for emp_name in sorted(active_emp_names):
        try:
            ek = next(
                (e["EmployeeKey"] for e in emp_list
                 if f"{e.get('FirstName','')} {e.get('LastName','')}".strip() == emp_name),
                None,
            )
            if not ek:
                print(f"[SKIP] Could not find EmployeeKey for {emp_name}")
                continue

            contact    = contacts.get(emp_name, {})
            email      = contact.get("email")
            phone      = contact.get("phone")
            sup_name   = supervisor_map.get(ek, "your supervisor")
            studio     = DEPARTMENTS.get(emp_dept_map.get(ek, 7), "Unknown")
            tier       = consecutive_map.get(emp_name, 0)
            e_flags    = emp_flags[emp_name]
            is_missing = emp_name in missing_completely

            has_issues = (
                is_missing or tier > 0 or
                e_flags["missing_notes"] or
                e_flags["incomplete_days"] or
                e_flags["full_overhead"]
            )

            if not has_issues and not by_employee.get(emp_name, {}).get(target_date):
                continue  # no entries and no flags — skip (e.g. weekend)

            if not client:
                print(f"[SKIP] No Claude client for {emp_name}")
                continue

            ctx     = build_employee_context(
                emp_name, target_date, e_flags,
                by_employee, prior_by_emp, emp_week_totals,
                tier, sup_name, studio, is_missing,
            )
            message = generate_employee_message(ctx, tier, client)

            subject = f"Luca \u00b7 Timesheet Review \u2014 {target_date.strftime('%A, %B %d')}"

            # Email
            if email:
                sup_email = contacts.get(sup_name, {}).get("email")
                cc_list   = []
                if sup_email and tier >= 1:
                    cc_list.append(sup_email)
                if tier >= 3:
                    cc_list.append(HR_EMAIL)
                send_email(email, subject, message, cc=cc_list if cc_list else None)
            else:
                print(f"[EMAIL SKIP] No email on file for {emp_name}")

            # WhatsApp — Tier 1 and 2 nudge only; Tier 3 is email-only
            if phone and tier in (1, 2):
                send_whatsapp(
                    phone,
                    f"Luca \u2014 {target_date.strftime('%a %b %d')}\n\n{message}",
                )

            print(
                f"[DONE] {emp_name} \u2014 tier {tier}, "
                f"flags: {sum(len(v) for v in e_flags.values())}"
            )

        except Exception:
            print(f"[ERROR] Failed processing {emp_name}:")
            traceback.print_exc()

    # 8. Build supervisor reports
    supervisor_teams = defaultdict(list)
    for e in emp_list:
        ek       = e["EmployeeKey"]
        ename    = emp_name_map.get(ek, "")
        sup_name = supervisor_map.get(ek)
        if sup_name:
            supervisor_teams[sup_name].append(ename)

    for sup_name, team in supervisor_teams.items():
        try:
            if not team or not client:
                continue

            sup_contact = contacts.get(sup_name, {})
            sup_email   = sup_contact.get("email")

            ctx    = build_supervisor_context(
                sup_name, team, target_date, emp_flags,
                by_employee, prior_by_emp, emp_week_totals,
                consecutive_map, missing_completely,
            )
            report = generate_supervisor_report(ctx, sup_name, client)

            if sup_email:
                send_email(
                    sup_email,
                    f"Luca \u00b7 Team Brief \u2014 {target_date.strftime('%A, %B %d')}",
                    report,
                )
            else:
                print(f"[SUPERVISOR EMAIL SKIP] No email on file for supervisor {sup_name}")

            print(f"[SUPERVISOR REPORT] {sup_name} \u2014 {len(team)} employee(s)")

        except Exception:
            print(f"[ERROR] Failed supervisor report for {sup_name}:")
            traceback.print_exc()

    print(f"[LUCA DAILY] Complete for {target_date}")


if __name__ == "__main__":
    main()
