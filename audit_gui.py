# -*- coding: utf-8 -*-
"""
Luca — Carlton Edwards Intelligence
"""
import sys, os, json, re, threading, webbrowser, traceback, io
from datetime import datetime, timedelta, date
from collections import defaultdict
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox
import tkcalendar
import requests
import customtkinter as ctk
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("dark-blue")

try:
    from google import genai as _genai
    from google.genai import types as _genai_types
    _GEMINI_AVAILABLE = True
except ImportError:
    _GEMINI_AVAILABLE = False

# ── CONFIG ────────────────────────────────────────────────────────────────────
API_ENDPOINT = (
    "https://ajera.com/V004613/AjeraAPI.ashx"
    "?ew0KICAiQ2xpZW50SUQiOiA0NjEzLA0KICAiRGF0YWJhc2VJRCI6IDE5NzI2LA0K"
    "ICAiSXNTYW1wbGVEYXRhIjogZmFsc2UNCn0%3d"
)
API_USER     = "ClaudeTime247"
API_PASSWORD = "GuinneaPig247!"

DEPARTMENTS = {
    2: "Asheville",   # Carlton Architecture PA
    4: "Nashville",   # Carlton Edwards PLLC
    6: "Memphis",     # Carlton Edwards PLLC
    7: "Consultant",
}

# Company→department mapping for filtering and context
COMPANIES = {
    "Carlton Architecture PA":  [2],     # Asheville only
    "Carlton Edwards PLLC":     [4, 6],  # Nashville + Memphis
}

MIN_HOURS = 8.0

# Weekly hour targets for employees who work non-standard schedules.
# Daily minimum is derived as weekly_target / 5.
EMP_WEEKLY_HOURS = {
    "Gordon Shisler": 32.0,
}

OVERHEAD_KW = [
    "overhead","general","admin","vacation","holiday",
    "pto","sick","training","business development","bd","marketing","office"
]
PTO_KW = {"vacation","holiday","pto","sick","personal"}

# Phrases that indicate synchronous (real-time) collaboration.
# A cross-reference is only generated when at least one of these appears in the note
# AND the referenced employee's name is not in a possessive context (e.g. "Rob's loom").
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

# Reports are saved to ~/Documents/Luca on every machine.
# When running as a PyInstaller bundle, bundled assets (icon, guide) live in
# sys._MEIPASS; during development they sit next to this script.
def _base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent

def resource_path(name):
    """Absolute path to a bundled asset (works dev + PyInstaller --onefile)."""
    return _base_dir() / name

REPORT_DIR = Path.home() / "Documents" / "Luca"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

AJERA_CACHE      = REPORT_DIR / "ajera_cache.json"
SESSION_FILE     = REPORT_DIR / "luca_session.json"
CACHE_MAX_AGE    = 24   # hours before reference cache is considered stale
TS_HISTORY_WEEKS = 10   # total weeks to keep in the rolling timesheet cache
TS_REFRESH_WEEKS =  4   # weeks to re-fetch on daily / post-audit partial refresh

# ── COLORS — Luca / Carlton Edwards palette ───────────────────────────────────
BG        = "#F8F6F2"   # page background — warm cream (Claude-style)
SURFACE   = "#FFFEFB"   # card surface — warm near-white
SURFACE2  = "#F0EDE8"   # muted warm surface (inactive / alt cards)
ACCENT    = "#1A1A1A"   # near-black — header, primary buttons
ACCENT2   = "#2E2420"   # dark warm brown — hover state
ACCENT3   = "#967B65"   # warm bronze — indicators / accents
TEXT      = "#1A1A1A"   # near-black primary text
TEXT2     = "#8A7A6E"   # warm gray secondary text
BORDER    = "#D4C8BC"   # warm gray-beige border
RED       = "#C0392B"   # muted red — error / blocked
YELLOW    = "#B87832"   # warm amber — warning
AMBER     = "#B87832"   # alias
GREEN_LT  = "#EDE8E2"   # warm beige — success / ok tint
GREEN     = "#967B65"   # warm bronze — success (same as ACCENT3)
DARK      = "#1B4332"   # deepest — same as ACCENT

# ── API HELPERS ───────────────────────────────────────────────────────────────

def api_post(payload):
    r = requests.post(API_ENDPOINT,
                      headers={"Content-Type": "application/json"},
                      data=json.dumps(payload), timeout=90)
    r.raise_for_status()
    result = r.json()
    if result.get("ResponseCode") not in (None, 0, "0", 200, "200"):
        raise RuntimeError(result.get("Message", str(result)))
    return result

def login(version=1):
    resp = api_post({"Method":"CreateAPISession","Username":API_USER,
                     "Password":API_PASSWORD,"APIVersion":version})
    return resp["Content"]["SessionToken"]

def logout(token):
    try: api_post({"Method":"EndAPISession","SessionToken":token})
    except: pass

def get_employees(token):
    resp = api_post({"Method":"ListEmployees","SessionToken":token,
                     "MethodArguments":{"FilterByStatus":["Active"]}})
    return resp.get("Content",{}).get("Employees",[])

def get_companies(token):
    """ListCompanies — returns CompanyKey, Description, Status."""
    resp = api_post({"Method": "ListCompanies", "SessionToken": token,
                     "MethodArguments": {"FilterByStatus": ["Active"]}})
    return resp.get("Content", {}).get("Companies", [])

def get_departments(token):
    """ListDepartments — returns DepartmentKey, Department name, Status, overhead %."""
    resp = api_post({"Method": "ListDepartments", "SessionToken": token,
                     "MethodArguments": {"FilterByStatus": ["Active"]}})
    return resp.get("Content", {}).get("Departments", [])

def get_activities(token):
    """ListActivities — returns ActivityKey, Description, Status."""
    resp = api_post({"Method": "ListActivities", "SessionToken": token,
                     "MethodArguments": {"FilterByStatus": ["Active"]}})
    return resp.get("Content", {}).get("Activities", [])

def get_project_list(token):
    """ListProjects — returns ProjectKey, ID, Description for every active project."""
    resp = api_post({"Method": "ListProjects", "SessionToken": token,
                     "MethodArguments": {"FilterByStatus": ["Active", "Preliminary", "Hold"]}})
    return resp.get("Content", {}).get("Projects", [])

def get_project_details(token, project_keys, batch_size=20):
    """GetProjects — returns full project detail including nested Phases with PhaseKey."""
    results = []
    for i in range(0, len(project_keys), batch_size):
        chunk = project_keys[i:i + batch_size]
        resp = api_post({"Method": "GetProjects", "SessionToken": token,
                         "MethodArguments": {"RequestedProjects": chunk}})
        results.extend(resp.get("Content", {}).get("Projects", []))
    return results

def load_ajera_cache() -> dict:
    """Load the local Ajera data cache. Returns empty dict if missing or corrupt."""
    if not AJERA_CACHE.exists():
        return {}
    try:
        return json.loads(AJERA_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def cache_age_hours() -> float:
    """Return how many hours ago the cache was last synced. Returns inf if no cache."""
    cache = load_ajera_cache()
    ts = cache.get("last_synced")
    if not ts:
        return float("inf")
    try:
        synced = datetime.fromisoformat(ts)
        return (datetime.now() - synced).total_seconds() / 3600
    except Exception:
        return float("inf")

def cache_age_label() -> str:
    """Human-readable cache age string for display in the sidebar."""
    age = cache_age_hours()
    if age == float("inf"):
        return "No cache — sync required"
    if age < 1:
        mins = int(age * 60)
        return f"Synced {mins}m ago"
    if age < 24:
        return f"Synced {age:.0f}h ago"
    return f"Synced {age/24:.0f}d ago — refresh recommended"

def _timesheet_history_range():
    """Return (start, end) covering the last TS_HISTORY_WEEKS of timesheets.

    End = today.  Start = today minus (TS_HISTORY_WEEKS × 7) days.
    Both are date objects aligned to calendar days; Ajera filters by the
    TimesheetDate field (Fridays), so any week whose Friday falls in this
    range will be included.
    """
    today = date.today()
    start = today - timedelta(days=TS_HISTORY_WEEKS * 7)
    return start, today


def sync_ajera_cache(progress_cb=None, refresh_mode: str = "full") -> dict:
    """Fetch Ajera reference data and maintain the rolling timesheet cache.

    refresh_mode:
        "full"    — Fetch all reference data (employees, projects, phases,
                    activities, companies, departments) PLUS all TS_HISTORY_WEEKS
                    weeks of timesheets.  Used by the Sync Data button and the
                    initial population run.
        "partial" — Re-fetch only the last TS_REFRESH_WEEKS weeks of timesheets
                    to catch retroactive employee changes.  Reference data is
                    skipped on partial mode — the existing cache values are kept.
                    Used by the daily automation and post-audit background refresh.

    Rolling-window rule: weeks older than TS_HISTORY_WEEKS are always dropped
    from cache["timesheet_weeks"] regardless of refresh_mode.

    LLM note: entirely deterministic — pure data fetching and structured Python.
    No AI involvement here.  The LLM is called separately for reasoning/narrative.
    """
    def _cb(msg):
        if progress_cb:
            progress_cb(msg)
        print(f"[CACHE SYNC] {msg}")

    # Partial mode preserves existing weeks; full mode starts fresh
    if refresh_mode == "partial":
        cache = load_ajera_cache()
        cache["sync_errors"] = []
        cache.setdefault("timesheet_weeks", {})
    else:
        cache = {"last_synced": datetime.now().isoformat(),
                 "sync_errors": [], "timesheet_weeks": {}}

    # ── v1 session — reference data (full mode only) ──────────────────────────
    if refresh_mode == "full":
        t1 = login(1)
        try:
            _cb("Fetching employees…")
            emp_list = get_employees(t1)
            cache["employees"] = emp_list
            _cb(f"  {len(emp_list)} employees")

            _cb("Fetching employee details (roles, supervisors)…")
            emp_keys   = [e["EmployeeKey"] for e in emp_list if e.get("EmployeeKey")]
            emp_detail = []
            batch = 20
            for i in range(0, len(emp_keys), batch):
                chunk = emp_keys[i:i+batch]
                try:
                    resp = api_post({"Method": "GetEmployees",
                                     "SessionToken": t1,
                                     "MethodArguments": {"RequestedEmployees": chunk}})
                    emp_detail.extend(resp.get("Content", {}).get("Employees", []))
                except Exception as e:
                    cache["sync_errors"].append(f"GetEmployees batch {i}: {e}")
            cache["employee_details"] = emp_detail
            _cb(f"  {len(emp_detail)} employee detail records")

            _cb("Fetching companies…")
            companies = get_companies(t1)
            cache["companies"] = companies
            _cb(f"  {len(companies)} companies")

            _cb("Fetching departments…")
            depts = get_departments(t1)
            cache["departments"] = depts
            _cb(f"  {len(depts)} departments")

            _cb("Fetching activities…")
            acts = get_activities(t1)
            cache["activities"] = acts
            _cb(f"  {len(acts)} activities")

            _cb("Fetching projects…")
            projects = get_project_list(t1)
            cache["projects"] = projects
            _cb(f"  {len(projects)} projects")

            _cb("Fetching project phases (this may take a moment)…")
            proj_keys    = [p["ProjectKey"] for p in projects if p.get("ProjectKey")]
            proj_details = get_project_details(t1, proj_keys, batch_size=20)
            phases = []
            for proj in proj_details:
                pkey  = proj.get("ProjectKey")
                pdesc = proj.get("Description", "")
                pid   = proj.get("ID", "")
                for ig in (proj.get("InvoiceGroups") or []):
                    for ph in (ig.get("Phases") or []):
                        phases.append({
                            "ProjectKey":   pkey,
                            "ProjectDesc":  pdesc,
                            "ProjectID":    pid,
                            "PhaseKey":     ph.get("PhaseKey"),
                            "PhaseID":      ph.get("ID", ""),
                            "PhaseDesc":    ph.get("Description", ""),
                            "PhaseStatus":  ph.get("Status", ""),
                        })
            cache["phases"] = phases
            _cb(f"  {len(phases)} phases across {len(proj_details)} projects")
            cache["last_synced"] = datetime.now().isoformat()

        except Exception as e:
            cache["sync_errors"].append(f"Reference data error: {e}")
            _cb(f"ERROR: {e}")
        finally:
            logout(t1)
    else:
        _cb("Partial refresh — skipping reference data (keeping cached values).")

    # ── v2 session — rolling timesheet window ─────────────────────────────────
    # full  → fetch all TS_HISTORY_WEEKS (10) weeks
    # partial → fetch only the last TS_REFRESH_WEEKS (4) weeks to catch retro edits
    n_weeks = TS_HISTORY_WEEKS if refresh_mode == "full" else TS_REFRESH_WEEKS
    fridays = history_fridays(n_weeks)
    _cb(f"Updating timesheet cache — {refresh_mode} mode, {n_weeks} weeks "
        f"({fridays[-1]} → {fridays[0]})…")
    t2 = login(2)
    try:
        fetched = _fetch_weeks_into_cache(cache, fridays, t2, _cb)
        _cb(f"  {fetched} timesheet records refreshed across {n_weeks} weeks")
    except Exception as exc:
        cache["sync_errors"].append(f"Timesheet history error: {exc}")
        _cb(f"  Warning: timesheet refresh failed — {exc}")
    finally:
        logout(t2)

    # ── Enforce rolling window ─────────────────────────────────────────────────
    dropped = _drop_old_weeks(cache, keep=TS_HISTORY_WEEKS)
    if dropped:
        _cb(f"  Rolling window: dropped {dropped} week(s) older than "
            f"{TS_HISTORY_WEEKS} weeks")

    # ── Metadata ──────────────────────────────────────────────────────────────
    n_cached = len(cache.get("timesheet_weeks", {}))
    cache["ts_window_weeks"]   = TS_HISTORY_WEEKS
    cache["ts_refresh_weeks"]  = TS_REFRESH_WEEKS
    cache["ts_weeks_in_cache"] = n_cached
    cache["ts_last_synced"]    = datetime.now().isoformat()

    # ── Persist ───────────────────────────────────────────────────────────────
    try:
        AJERA_CACHE.write_text(
            json.dumps(cache, indent=2, default=str), encoding="utf-8")
        _cb(f"Cache saved → {AJERA_CACHE}  ({n_cached} weeks in rolling window)")
    except Exception as exc:
        _cb(f"Failed to save cache: {exc}")

    return cache

def get_timesheet_list(token, start, end):
    resp = api_post({"Method":"ListTimesheets","SessionToken":token,
                     "MethodArguments":{
                         "FilterByEarliestTimesheetDate": str(start),
                         "FilterByLatestTimesheetDate":   str(end)}})
    return resp.get("Content",{}).get("Timesheets",[])

def get_timesheet_detail(token, keys, batch_size=10):
    results = []
    for i in range(0, len(keys), batch_size):
        chunk = keys[i:i+batch_size]
        resp = api_post({"Method":"GetTimesheets","SessionToken":token,
                         "MethodArguments":{"RequestedTimesheets":chunk}})
        results.extend(resp.get("Content",{}).get("Timesheets",[]))
    return results

# ── PAYROLL-WEEK & ROLLING-CACHE HELPERS ──────────────────────────────────────
# All deterministic — no LLM involvement.
# Ajera payroll week: Saturday (D1) through Friday (D7).
# TimesheetDate in Ajera == the Friday that closes each payroll week.

def payroll_friday_of(d) -> date:
    """Return the Friday that closes the Sat-Fri payroll week containing d."""
    return d + timedelta(days=(4 - d.weekday()) % 7)


def payroll_friday(offset: int = 0) -> date:
    """Friday of a recent payroll week.
    offset=0 = current week, offset=-1 = last week, offset=-(n-1) = n weeks ago."""
    return payroll_friday_of(date.today()) + timedelta(weeks=offset)


def history_fridays(n: int = TS_HISTORY_WEEKS) -> list:
    """Return list of the n most recent payroll-week Fridays, newest first."""
    base = payroll_friday(0)
    return [base + timedelta(weeks=-i) for i in range(n)]


def _fetch_weeks_into_cache(cache: dict, fridays: list, token2, cb) -> int:
    """Fetch one payroll week of timesheets per Friday into cache["timesheet_weeks"].

    Operates inside an already-open v2 Ajera session token.
    Each week is keyed by its Friday date string "YYYY-MM-DD".
    Empty weeks are stored with timesheets=[] so we know they were checked.
    Returns total number of timesheet records stored across all weeks.
    """
    cache.setdefault("timesheet_weeks", {})
    total = 0
    for friday in fridays:
        friday_str = str(friday)
        week_start = friday - timedelta(days=6)     # preceding Saturday
        try:
            ts_list   = get_timesheet_list(token2, week_start, friday)
            ts_keys   = [t["Timesheet Key"] for t in ts_list
                         if t.get("Timesheet Key")]
            ts_detail = (get_timesheet_detail(token2, ts_keys, batch_size=10)
                         if ts_keys else [])
            cache["timesheet_weeks"][friday_str] = {
                "fetched_at": datetime.now().isoformat(),
                "timesheets": ts_detail,
            }
            total += len(ts_detail)
            cb(f"    {week_start} → {friday}: {len(ts_detail)} records")
        except Exception as exc:
            cb(f"    Week {friday_str}: ERROR — {exc}")
    return total


def _drop_old_weeks(cache: dict, keep: int = TS_HISTORY_WEEKS) -> int:
    """Remove weeks older than `keep` payroll weeks from cache["timesheet_weeks"].

    Enforces the rolling window so storage stays bounded at TS_HISTORY_WEEKS weeks.
    ISO date strings (YYYY-MM-DD) sort chronologically as plain strings — no
    date parsing needed for the comparison.
    Returns count of weeks removed.
    """
    weeks = cache.get("timesheet_weeks", {})
    if not weeks:
        return 0
    cutoff_str = str(payroll_friday(-(keep - 1)))   # oldest Friday we keep
    to_drop    = [k for k in list(weeks) if k < cutoff_str]
    for k in to_drop:
        del weeks[k]
    return len(to_drop)


def ts_details_from_cache(cache: dict, start: date, end: date) -> list:
    """Return a flat list of timesheet records covering [start, end].

    Reads from the new week-keyed cache["timesheet_weeks"].  Falls back to
    the legacy flat "timesheet_details" key for pre-migration cache files.
    Includes all records from weeks whose Sat-Fri window overlaps [start, end].
    Pure deterministic Python — no LLM involvement.
    """
    weeks = cache.get("timesheet_weeks", {})
    if weeks:
        records = []
        for friday_str, week_data in weeks.items():
            try:
                friday = date.fromisoformat(friday_str)
            except ValueError:
                continue
            week_sat = friday - timedelta(days=6)
            if friday >= start and week_sat <= end:    # inclusive overlap
                records.extend(week_data.get("timesheets", []))
        return records
    return cache.get("timesheet_details", [])          # legacy fallback


def weeks_covered_by_cache(cache: dict) -> tuple:
    """Return (earliest_date, latest_date) spanned by the timesheet cache.

    earliest_date = Saturday of the oldest cached week.
    latest_date   = Friday of the most recent cached week.
    Returns (None, None) if no timesheet data is present.
    """
    weeks = cache.get("timesheet_weeks", {})
    if weeks:
        fridays = []
        for k in weeks:
            try:
                fridays.append(date.fromisoformat(k))
            except ValueError:
                pass
        if fridays:
            return min(fridays) - timedelta(days=6), max(fridays)
        return None, None
    # Legacy fallback — old flat structure
    s = cache.get("timesheet_start")
    e = cache.get("timesheet_end")
    if s and e:
        try:
            return date.fromisoformat(s), date.fromisoformat(e)
        except ValueError:
            pass
    return None, None


# ── DATE UTILS ────────────────────────────────────────────────────────────────

def payroll_week_bounds(offset=0):
    """Saturday to Friday payroll week."""
    today = datetime.today()
    days_since_sat = (today.weekday() - 5) % 7
    last_sat = today - timedelta(days=days_since_sat)
    start = last_sat + timedelta(weeks=offset)
    return start.date(), (start + timedelta(days=6)).date()

def month_bounds(offset=0):
    """First to last day of the month."""
    import calendar
    today = datetime.today()
    month = today.month + offset
    year  = today.year
    while month <= 0:  month += 12; year -= 1
    while month > 12:  month -= 12; year += 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)

def d_to_date(ts_date_str, d_index):
    """Ajera TimesheetDate = Friday; D1=Sat … D7=Fri"""
    ts = datetime.strptime(ts_date_str[:10], "%Y-%m-%d").date()
    return ts - timedelta(days=6) + timedelta(days=d_index-1)

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

# ── AUDIT CORE ────────────────────────────────────────────────────────────────

def run_audit(start, end, emp_dept_map):
    """Returns (flags, by_employee, by_project)."""
    # Fetch three extra payroll weeks before start:
    #   • 1 week back  — prior-week totals for the incomplete-day flag
    #   • 2-3 weeks back — rolling trend data passed to Ask Luca
    query_start = payroll_week_start(start) - timedelta(days=21)

    t1 = login(1)
    t2 = login(2)
    try:
        employees   = get_employees(t1)
        emp_name_map = {e["EmployeeKey"]:
                        f"{e.get('FirstName','')} {e.get('LastName','')}".strip()
                        for e in employees}
        ts_list  = get_timesheet_list(t2, query_start, end)
        ts_keys  = [t["Timesheet Key"] for t in ts_list if t.get("Timesheet Key")]
        detailed = get_timesheet_detail(t2, ts_keys) if ts_keys else []
    finally:
        logout(t1); logout(t2)

    # name part (lowercase first/last, min 3 chars) -> list of employee keys
    name_part_to_eks = defaultdict(list)
    for _e in employees:
        _ek = _e["EmployeeKey"]
        for _part in [(_e.get("FirstName") or "").strip(), (_e.get("LastName") or "").strip()]:
            if len(_part) >= 3:
                name_part_to_eks[_part.lower()].append(_ek)

    flags = {"missing_notes":[], "incomplete_days":[], "full_overhead":[], "collab":[], "teamwork":[]}
    by_employee     = defaultdict(lambda: defaultdict(list))  # emp -> date -> entries (audit period)
    prior_by_emp    = defaultdict(lambda: defaultdict(list))  # emp -> date -> entries (prior weeks)
    by_project      = defaultdict(lambda: defaultdict(list))  # proj_desc -> emp -> entries
    emp_day_entries = defaultdict(lambda: defaultdict(list))  # ek -> date -> [{proj,...}]
    emp_week_totals = defaultdict(lambda: defaultdict(float)) # emp -> week_sat -> total hrs

    for sheet in detailed:
        ek    = sheet.get("EmployeeKey")
        ename = emp_name_map.get(ek, f"#{ek}")
        dept  = emp_dept_map.get(ek, 7)
        ts_ds = str(sheet.get("TimesheetDate",""))

        day_hrs  = defaultdict(float)
        day_oh   = defaultdict(float)
        day_note = defaultdict(bool)
        day_ents = defaultdict(list)

        for entry in (sheet.get("Overhead",{}).get("Detail") or []):
            desc = entry.get("Timesheet Overhead Group Detail","")
            for d in range(1,8):
                hrs  = float(entry.get(f"D{d} Regular") or 0)
                note = (entry.get(f"D{d} Notes") or "").strip()
                if hrs <= 0: continue
                dt = d_to_date(ts_ds, d)
                day_hrs[dt]  += hrs
                day_oh[dt]   += hrs
                if note: day_note[dt] = True
                day_ents[dt].append({"type":"overhead","desc":desc,
                                     "hrs":hrs,"note":note,"dept":dept})

        for entry in (sheet.get("Project",{}).get("Detail") or []):
            pd   = entry.get("Project Description","")
            ph   = entry.get("Phase Description","")
            act  = entry.get("Activity","")
            pkey = entry.get("Project Key")
            for d in range(1,8):
                reg  = float(entry.get(f"D{d} Regular")  or 0)
                ovt  = float(entry.get(f"D{d} Overtime") or 0)
                note = (entry.get(f"D{d} Notes") or "").strip()
                hrs  = reg + ovt
                if hrs <= 0: continue
                dt = d_to_date(ts_ds, d)
                day_hrs[dt]  += hrs
                if note: day_note[dt] = True
                e = {"type":"project","desc":pd,"phase":ph,"activity":act,
                     "hrs":hrs,"note":note,"dept":dept,"pkey":pkey}
                day_ents[dt].append(e)
                by_project[pd][ename].append({
                    "date":dt,"phase":ph,"activity":act,
                    "hrs":hrs,"note":note,"dept":dept})

        for dt in sorted(day_hrs):
            total = day_hrs[dt]
            ws    = payroll_week_start(dt)
            # Weekend hours count toward the weekly total even if we don't flag
            # the day itself as short (nobody expects 8h on a Saturday).
            emp_week_totals[ename][ws] += total  # accumulate for ALL fetched weeks

            if dt < start:
                # Collect full entry data for prior weeks so Ask Luca can spot trends
                for e in day_ents[dt]:
                    prior_by_emp[ename][dt].append(e)
                continue  # prior weeks: trend data only, no audit flags or report entries

            lbl  = dt.strftime("%a %m/%d")
            ents = day_ents[dt]

            for e in ents:
                by_employee[ename][dt].append(e)
                emp_day_entries[ek][dt].append({
                    "proj": e["desc"] if e["type"] == "project" else f"[Overhead] {e['desc']}",
                    "phase": e.get("phase",""), "activity": e.get("activity",""),
                    "hrs": e["hrs"], "note": e["note"],
                    "pkey": e.get("pkey")})

            # Incomplete-day check applies to Mon–Fri only.
            # Weekend hours are voluntarily logged and shouldn't trigger a shortfall flag.
            if dt.weekday() < 5:
                day_min = daily_min_hours(ename)
                if total < day_min:
                    flags["incomplete_days"].append(
                        {"emp":ename,"dept":dept,"date":lbl,"hrs":total,
                         "miss":round(day_min-total,2),
                         "_week_start":ws,
                         "week_total":None,"prior_week_total":None})
            for e in ents:
                if not e["note"]:
                    is_pto = (e["type"] == "overhead" and
                              any(kw in (e["desc"] or "").lower() for kw in PTO_KW))
                    flags["missing_notes"].append(
                        {"emp":ename,"dept":dept,"date":lbl,
                         "desc":e["desc"],"hrs":e["hrs"],"type":e["type"],
                         "is_pto":is_pto})
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
                flags["full_overhead"].append(
                    {"emp":ename,"dept":dept,"date":lbl,
                     "hrs":total,"has_note":day_note[dt],"descs":oh_descs})

    # ── Collaboration Citations: collect every sync mention of another employee ──
    # For each timesheet note that contains a synchronous-work signal (met with,
    # discussed, etc.) AND names a colleague, we record one citation record.
    # The report is organised by the MENTIONED person — showing who cited them,
    # on what date, on which project/phase, and the exact note text.
    # No cross-referencing or grading is performed here; that is Step 2.
    seen_citations: set = set()
    for c_ek, c_date_map in emp_day_entries.items():
        c_ename = emp_name_map.get(c_ek, f"#{c_ek}")
        for c_dt, c_ents in c_date_map.items():
            c_lbl = c_dt.strftime("%a %m/%d")
            for c_ent in c_ents:
                c_note = c_ent.get("note", "")
                if not c_note:
                    continue
                # Require at least one synchronous-collaboration signal.
                if not _has_sync_pattern(c_note):
                    continue
                for name_part, m_eks in name_part_to_eks.items():
                    name_matches = list(re.finditer(
                        r'\b' + re.escape(name_part) + r'\b', c_note, re.IGNORECASE))
                    if not name_matches:
                        continue
                    # Skip if every occurrence is possessive (Rob's, etc.)
                    has_non_possessive = any(
                        not _is_possessive_match(c_note, m) for m in name_matches)
                    if not has_non_possessive:
                        continue
                    for m_ek in m_eks:
                        if m_ek == c_ek:
                            continue
                        # Deduplicate per unique (citer, mentioned, date, entry)
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

# ── HTML REPORT ───────────────────────────────────────────────────────────────

def dept_label(dept_id):
    return DEPARTMENTS.get(dept_id, f"Dept {dept_id}")

def build_html(flags, by_employee, by_project, start, end):
    mn   = flags["missing_notes"]
    inc  = flags["incomplete_days"]
    foh  = flags["full_overhead"]
    col  = flags["collab"]
    tmw  = flags.get("teamwork", [])
    mn_blocked = [f for f in mn if not f.get("is_pto")]
    total_issues = len(mn_blocked)+len(inc)+len(foh)+len(col)

    status_color = "#C0392B" if total_issues else "#1E7E34"
    status_text  = f"{total_issues} issue(s) — resolve before invoicing" if total_issues else "All clear"

    dept_order = [2, 4, 6, 7]

    def flag_badge(count, color):
        return (f'<span style="background:{color};color:#fff;'
                f'padding:2px 8px;border-radius:10px;font-size:12px">{count}</span>')

    def section(title, color, rows_html, count):
        badge = flag_badge(count, color)
        return f"""
        <div class="section">
          <div class="section-header" style="border-left:5px solid {color}">
            <h3>{title} {badge}</h3>
          </div>
          <div class="section-body">{rows_html}</div>
        </div>"""

    def flag_table(headers, rows):
        if not rows:
            return '<p class="ok">No issues found.</p>'
        ths = "".join(f"<th>{h}</th>" for h in headers)
        trs = "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
            for row in rows
        )
        return f"<table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>"

    # ── Flags tables ──────────────────────────────────────────────────────────
    mn_rows = [
        [('&#x2705; OK' if f.get("is_pto") else '&#x1F534; Blocked'),
         f["emp"], dept_label(f["dept"]), f["date"],
         f["desc"], f"{f['hrs']}h", f["type"]]
        for f in mn
    ]
    mn_html = flag_table(["","Employee","Studio","Date","Entry","Hours","Type"], mn_rows)

    inc_rows = [
        [f["emp"], dept_label(f["dept"]), f["date"],
         f"{f['hrs']}h", f"{f['miss']}h short",
         f"{f['week_total']}h",
         f"{f['prior_week_total']}h" if f["prior_week_total"] else "—"]
        for f in inc
    ]
    inc_html = flag_table(
        ["Employee","Studio","Date","Day Total","Shortfall","Week Total","Prior Week"],
        inc_rows)

    foh_rows = [[f["emp"], dept_label(f["dept"]), f["date"],
                 f"{f['hrs']}h",
                 f.get("descs") or "—",
                 "Yes" if f["has_note"] else '<span class="warn">No</span>']
                for f in foh]
    foh_html = flag_table(["Employee","Studio","Date","Hours","Activity","Has Note"], foh_rows)

    def _entry_cards(entries):
        """Render a list of entry dicts as annotation cards."""
        if not entries:
            return ('<div style="color:#888;font-style:italic;padding:8px">'
                    'No entries found for this date.</div>')
        parts = []
        for e in entries:
            proj  = e.get("proj", "—")
            phase = e.get("phase", "")
            act   = e.get("activity", "")
            hrs   = e.get("hrs", 0)
            note  = e.get("note", "")
            label = proj
            if phase:   label += f' &nbsp;/&nbsp; {phase}'
            if act:     label += f' &nbsp;[{act}]'
            note_html = (note if note else
                         '<span style="color:#C0392B;font-weight:bold">NO NOTE</span>')
            parts.append(
                f'<div style="margin-bottom:8px;padding:11px 14px;'
                f'background:#F7F9FC;border-radius:6px;'
                f'border-left:3px solid #2D6A9F">'
                f'<div style="font-size:14px;font-weight:700;color:#111827">{label}</div>'
                f'<div style="font-size:14px;color:#374151;margin-top:3px">{hrs}h</div>'
                f'<div style="font-size:14px;color:#374151;font-style:italic;'
                f'margin-top:5px;line-height:1.5">{note_html}</div>'
                f'</div>')
        return "".join(parts)

    # ── Collaboration Citations HTML ───────────────────────────────────────────
    # Grouped by the MENTIONED employee.  Each card row = one citation:
    #   date | cited by | project | phase | hours | verbatim note
    if not col:
        col_html = '<p class="ok">No collaboration citations found in this period.</p>'
    else:
        from collections import defaultdict as _cdd
        by_mentioned: dict = _cdd(list)
        for c in col:
            by_mentioned[c["mentioned_emp"]].append(c)

        blocks = []
        for m_emp in sorted(by_mentioned.keys()):
            cites = sorted(by_mentioned[m_emp],
                           key=lambda x: (x.get("date_obj") or date.min, x["cited_by"]))
            rows = []
            for c in cites:
                note_safe = (c["note"]
                             .replace("&", "&amp;")
                             .replace("<", "&lt;")
                             .replace(">", "&gt;"))
                phase_tag = (f'<span class="cite-phase">{c["phase"]}</span>'
                             if c.get("phase") else "")
                rows.append(
                    f'<div class="cite-row">'
                    f'<div class="cite-meta">'
                    f'<span class="cite-date">{c["date"]}</span>'
                    f'<span class="cite-by">cited by <strong>{c["cited_by"]}</strong></span>'
                    f'<span class="cite-proj">{c["project"]}</span>'
                    f'{phase_tag}'
                    f'<span class="cite-hrs">{c["hours"]:.1f}h</span>'
                    f'</div>'
                    f'<div class="cite-note">&#8220;{note_safe}&#8221;</div>'
                    f'</div>'
                )
            n = len(cites)
            count_lbl = f'{n} citation{"s" if n != 1 else ""}'
            blocks.append(
                f'<div class="cite-block">'
                f'<div class="cite-emp-hdr">'
                f'<span class="cite-emp-name">{m_emp}</span>'
                f'<span class="cite-count">{count_lbl}</span>'
                f'</div>'
                f'{"".join(rows)}'
                f'</div>'
            )
        col_html = "".join(blocks)

    # ── Teamwork HTML ─────────────────────────────────────────────────────────
    if not tmw:
        tmw_html = '<p class="ok">No collaborative entries logged this period.</p>'
    else:
        from collections import defaultdict as _tdd
        by_tmw_emp: dict = _tdd(list)
        for t in tmw:
            by_tmw_emp[t["employee"]].append(t)

        tmw_total_entries = len(tmw)
        tmw_total_hours   = sum(t["hours"] for t in tmw)
        tmw_emp_count     = len(by_tmw_emp)

        summary_bar = (
            f'<div style="display:flex;gap:28px;padding:16px 20px;'
            f'background:#F9FAFB;border-bottom:1px solid #E5E7EB;'
            f'border-radius:12px 12px 0 0;flex-wrap:wrap;">'
            f'<span style="font-size:14px;color:#111827;">'
            f'<strong>{tmw_total_entries}</strong> collaborative '
            f'{"entry" if tmw_total_entries == 1 else "entries"}</span>'
            f'<span style="font-size:14px;color:#111827;">'
            f'<strong>{tmw_total_hours:.1f}h</strong> logged</span>'
            f'<span style="font-size:14px;color:#111827;">'
            f'<strong>{tmw_emp_count}</strong> '
            f'{"employee" if tmw_emp_count == 1 else "employees"} with collaborative work</span>'
            f'</div>'
        )

        tmw_blocks = [summary_bar]
        for emp_name in sorted(by_tmw_emp.keys()):
            entries = sorted(by_tmw_emp[emp_name], key=lambda x: x["date"])
            emp_entry_count = len(entries)
            emp_hours       = sum(e["hours"] for e in entries)
            count_badge = (
                f'<span style="background:#F3F4F6;color:#374151;font-size:13px;'
                f'padding:3px 10px;border-radius:99px;font-weight:500;">'
                f'{emp_entry_count} {"entry" if emp_entry_count == 1 else "entries"}'
                f' &middot; {emp_hours:.1f}h</span>'
            )
            entry_rows = []
            for i, e in enumerate(entries):
                divider = 'border-top:1px solid #F3F4F6;' if i > 0 else ''
                date_str  = e["date"].strftime("%a %b %d") if hasattr(e["date"], "strftime") else str(e["date"])
                proj_str  = e["proj"]
                if e["phase"]:    proj_str += f' / {e["phase"]}'
                note_safe = (e["note"]
                             .replace("&", "&amp;")
                             .replace("<", "&lt;")
                             .replace(">", "&gt;"))
                entry_rows.append(
                    f'<div style="padding:12px 18px;{divider}">'
                    f'<div style="display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;">'
                    f'<span style="color:#4B5563;font-size:14px;min-width:96px;font-weight:500;">{date_str}</span>'
                    f'<span style="font-weight:500;font-size:14px;color:#111827;">{proj_str}</span>'
                    f'<span style="font-weight:700;color:#111827;font-size:14px;margin-left:auto;">'
                    f'{e["hours"]:.1f}h</span>'
                    f'</div>'
                    f'<div style="color:#374151;font-size:14px;font-style:italic;margin-top:4px;'
                    f'padding-left:110px;line-height:1.5;">{note_safe}</div>'
                    f'</div>'
                )
            tmw_blocks.append(
                f'<div style="background:#fff;border:1px solid #E5E7EB;'
                f'border-radius:12px;margin-bottom:14px;overflow:hidden;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:12px 18px;border-bottom:1px solid #E5E7EB;">'
                f'<span style="font-weight:700;font-size:16px;color:#111827;">'
                f'{emp_name}</span>'
                f'{count_badge}'
                f'</div>'
                f'{"".join(entry_rows)}'
                f'</div>'
            )
        tmw_html = "".join(tmw_blocks)

    # ── By Employee ───────────────────────────────────────────────────────────
    emp_sections = ""
    for dept_id in dept_order:
        dept_name = dept_label(dept_id)
        dept_emps = sorted(
            [(ename, dates) for ename, dates in by_employee.items()
             if any(e["dept"] == dept_id
                    for dates_val in dates.values() for e in dates_val)],
            key=lambda x: x[0]
        )
        if not dept_emps: continue

        emp_html = ""
        for ename, date_map in dept_emps:
            rows = ""
            total_hrs = 0
            for dt in sorted(date_map.keys()):
                ents = date_map[dt]
                day_total = sum(e["hrs"] for e in ents)
                total_hrs += day_total
                short = day_total < MIN_HOURS and dt.weekday() < 5
                day_class = ' class="short-day"' if short else ""
                day_label_str = dt.strftime("%a %m/%d")
                rows += f'<tr{day_class}><td colspan="4"><strong>{day_label_str}</strong> &mdash; {day_total}h total'
                if short: rows += f' <span class="warn-badge">SHORT {round(MIN_HOURS-day_total,2)}h</span>'
                rows += "</td></tr>"
                for e in ents:
                    if e["type"] == "project":
                        label = e["desc"]
                        if e.get("phase"): label += f' / {e["phase"]}'
                        if e.get("activity"): label += f' [{e["activity"]}]'
                    else:
                        label = f'[Overhead] {e["desc"]}'
                    note_html = e["note"] if e["note"] else '<span class="no-note">NO NOTE — BLOCKED</span>'
                    rows += (f'<tr><td style="width:70px">{e["hrs"]}h</td>'
                             f'<td colspan="2">{label}</td>'
                             f'<td class="note-cell">{note_html}</td></tr>')

            emp_html += f"""
            <div class="emp-card">
              <div class="emp-header">
                <span class="emp-name">{ename}</span>
                <span class="emp-total">{total_hrs}h total</span>
              </div>
              <table class="detail-table">
                <thead><tr><th>Hours</th><th colspan="2">Entry</th><th>Notes</th></tr></thead>
                <tbody>{rows}</tbody>
              </table>
            </div>"""

        emp_sections += f"""
        <div class="dept-section">
          <h3 class="dept-title">{dept_name}</h3>
          {emp_html}
        </div>"""

    # ── By Project ────────────────────────────────────────────────────────────
    proj_html = ""
    for proj_name in sorted(by_project.keys()):
        emp_map = by_project[proj_name]
        proj_total = sum(e["hrs"] for emps in emp_map.values() for e in emps)
        rows = ""
        for ename in sorted(emp_map.keys()):
            entries = sorted(emp_map[ename], key=lambda x: x["date"])
            for e in entries:
                label = e.get("phase","")
                if e.get("activity"): label += f' [{e["activity"]}]'
                note_html = e["note"] if e["note"] else '<span class="no-note">NO NOTE</span>'
                dept_str  = dept_label(e.get("dept", 7))
                rows += (f"<tr><td>{e['date'].strftime('%a %m/%d')}</td>"
                         f"<td>{ename}</td><td>{dept_str}</td>"
                         f"<td>{label}</td><td>{e['hrs']}h</td>"
                         f'<td class="note-cell">{note_html}</td></tr>')

        proj_html += f"""
        <div class="proj-card">
          <div class="proj-header">
            <span class="proj-name">{proj_name}</span>
            <span class="proj-total">{proj_total}h</span>
          </div>
          <table class="detail-table">
            <thead><tr><th>Date</th><th>Employee</th><th>Studio</th>
            <th>Phase/Activity</th><th>Hours</th><th>Notes</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>"""

    # ── Assemble ──────────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>LUCA — {start} to {end}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap">
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          font-size:15px; background:#F7F8FA; color:#111827;
          -webkit-font-smoothing:antialiased; line-height:1.6; }}
  .page-wrap {{ max-width:1200px; margin:0 auto; padding:32px 24px; }}

  /* ── Header ── */
  .report-header {{
    background:#fff; border:1px solid #E5E7EB; border-radius:16px;
    padding:28px 36px; margin-bottom:28px;
    display:flex; justify-content:space-between; align-items:center;
  }}
  .report-header-left h1 {{
    font-size:28px; font-weight:700; color:#111827; margin-bottom:6px;
    letter-spacing:-0.02em;
  }}
  .report-header-left p {{ color:#374151; font-size:15px; font-weight:400; }}
  .report-header-right {{ display:flex; align-items:center; gap:12px; }}
  .print-btn {{
    background:transparent; border:1.5px solid #1B4332; color:#1B4332;
    padding:10px 24px; border-radius:8px; cursor:pointer;
    font-family:'Inter', sans-serif;
    font-size:14px; font-weight:600; letter-spacing:0em; transition:all .15s;
  }}
  .print-btn:hover {{ background:#1B4332; color:#fff; }}
  .status-badge {{
    display:inline-block; padding:10px 24px; border-radius:24px;
    background:{status_color}; color:#fff;
    font-size:14px; font-weight:700; letter-spacing:.2px;
  }}

  /* ── Summary stat cards ── */
  .summary-grid {{
    display:grid; grid-template-columns:repeat(5,1fr);
    gap:16px; margin-bottom:28px;
  }}
  .summary-card {{
    background:#fff; border-radius:16px; padding:24px 26px;
    border:1px solid #E5E7EB; box-shadow:0 1px 3px rgba(0,0,0,.05);
  }}
  .summary-card.primary {{
    background:#1B4332; border-color:#1B4332;
  }}
  .summary-card .num {{
    font-size:44px; font-weight:800; line-height:1; margin-bottom:10px;
    color:#111827;
  }}
  .summary-card.primary .num {{ color:#fff; }}
  .summary-card .lbl {{
    font-size:12px; color:#4B5563; text-transform:uppercase;
    letter-spacing:.5px; font-weight:600;
  }}
  .summary-card.primary .lbl {{ color:rgba(255,255,255,.75); }}
  .summary-card .trend {{
    margin-top:10px; font-size:13px; color:#40916C; font-weight:600;
    display:flex; align-items:center; gap:4px;
  }}
  .summary-card.primary .trend {{ color:#95D5B2; }}

  /* ── Tab bar — pill style ── */
  .tabs {{
    display:flex; gap:6px; margin-bottom:24px;
    background:#fff; padding:6px; border-radius:12px;
    border:1px solid #E5E7EB; width:fit-content;
  }}
  .tab {{
    padding:9px 24px; cursor:pointer; border-radius:8px;
    font-size:14px; font-weight:600; color:#4B5563;
    transition:all .15s; user-select:none; border:none; background:none;
  }}
  .tab.active {{ background:#1B4332; color:#fff; }}
  .tab-content {{ display:none; }}
  .tab-content.active {{ display:block; }}

  /* ── Section cards ── */
  .section {{ margin-bottom:24px; }}
  .section-header {{
    display:flex; justify-content:space-between; align-items:center;
    padding:15px 20px; background:#fff;
    border:1px solid #E5E7EB; border-bottom:none;
    border-radius:12px 12px 0 0;
  }}
  .section-header h3 {{
    font-size:16px; font-weight:700; color:#111827;
    display:flex; align-items:center; gap:10px;
  }}
  .count-badge {{
    background:#1B4332; color:#fff; border-radius:20px;
    padding:3px 13px; font-size:12px; font-weight:700;
  }}
  .section-body {{
    background:#fff; border:1px solid #E5E7EB; border-top:none;
    border-radius:0 0 12px 12px; overflow:hidden;
  }}

  /* ── Tables ── */
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th {{
    background:#F7F8FA; color:#374151; padding:12px 16px;
    text-align:left; font-weight:700; font-size:12px;
    text-transform:uppercase; letter-spacing:.5px;
    border-bottom:1px solid #E5E7EB;
  }}
  td {{
    padding:12px 16px; border-bottom:1px solid #F3F4F6;
    vertical-align:top; color:#111827;
  }}
  tr:last-child td {{ border-bottom:none; }}
  tr:hover td {{ background:#FAFAFA; }}
  .ok {{ color:#40916C; font-style:italic; padding:14px 16px; display:block; font-size:14px; }}

  /* ── Inline badges ── */
  .badge {{
    display:inline-block; padding:3px 11px; border-radius:20px;
    font-size:12px; font-weight:700;
  }}
  .badge-red    {{ background:#FEE2E2; color:#991B1B; }}
  .badge-yellow {{ background:#FEF3C7; color:#92400E; }}
  .badge-green  {{ background:#D1FAE5; color:#065F46; }}

  /* ── Employee / project cards ── */
  .dept-section {{ margin-bottom:36px; }}
  .dept-title {{
    font-size:17px; font-weight:700; color:#1B4332;
    border-left:4px solid #1B4332; padding-left:14px;
    margin-bottom:18px;
  }}
  .emp-card, .proj-card {{
    background:#fff; border:1px solid #E5E7EB;
    border-radius:14px; margin-bottom:16px; overflow:hidden;
  }}
  .emp-header, .proj-header {{
    display:flex; justify-content:space-between; align-items:center;
    padding:15px 20px; background:#1B4332; color:#fff;
  }}
  .emp-name, .proj-name {{ font-weight:700; font-size:16px; }}
  .emp-total, .proj-total {{
    font-size:13px; opacity:.9;
    background:rgba(255,255,255,.18); padding:4px 14px; border-radius:20px;
  }}
  .detail-table th {{ background:#F7F8FA; }}
  .note-cell {{ color:#374151; font-style:italic; max-width:360px; }}
  .short-day td {{ background:#FFFBEB !important; }}
  .no-note {{ color:#EF4444; font-weight:700; font-style:normal; }}
  .warn-badge {{
    background:#FEF3C7; color:#92400E; padding:3px 10px;
    border-radius:10px; font-size:12px; font-weight:700; margin-left:6px;
  }}

  /* ── Collaboration Citation cards ── */
  .cite-block {{
    background:#fff; border:1px solid #E5E7EB;
    border-radius:12px; margin-bottom:16px; overflow:hidden;
  }}
  .cite-emp-hdr {{
    display:flex; justify-content:space-between; align-items:center;
    padding:13px 18px; background:{ACCENT};
    font-weight:700; font-size:15px; color:#fff;
  }}
  .cite-emp-name {{ color:#fff; }}
  .cite-count {{
    background:rgba(255,255,255,.18); padding:3px 14px;
    border-radius:20px; font-size:13px; font-weight:600; color:#fff;
  }}
  .cite-row {{
    padding:14px 18px; border-bottom:1px solid #F3F4F6;
  }}
  .cite-row:last-child {{ border-bottom:none; }}
  .cite-meta {{
    display:flex; flex-wrap:wrap; align-items:center;
    gap:8px; margin-bottom:8px;
  }}
  .cite-date  {{ font-weight:700; color:{ACCENT}; font-size:14px; }}
  .cite-by    {{ font-size:14px; color:#374151; }}
  .cite-by strong {{ color:#111827; }}
  .cite-proj  {{ font-size:13px; color:{ACCENT2}; background:#EEF4F0;
                padding:3px 10px; border-radius:20px; }}
  .cite-phase {{ font-size:13px; color:#4B5563; }}
  .cite-hrs   {{ font-size:13px; color:#4B5563; margin-left:auto; }}
  .cite-note  {{ font-size:14px; color:#111827; font-style:italic; line-height:1.6; }}

  span.warn {{ color:{YELLOW}; font-weight:bold; }}
  @media print {{
    .print-btn, .tabs {{ display:none !important; }}
    .tab-content {{ display:block !important; page-break-before:always; }}
    .tab-content:first-of-type {{ page-break-before:avoid; }}
    body {{ background:#fff; font-size:12px; }}
    .report-header {{ border:none; box-shadow:none; margin-bottom:16px; }}
    .section, .emp-card, .proj-card, .cite-block {{ break-inside:avoid; }}
  }}
</style>
<script>
function showTab(id) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  document.getElementById('content-'+id).classList.add('active');
}}
</script>
</head>
<body>
<div class="page-wrap">

  <div class="report-header">
    <div class="report-header-left">
      <h1>Carlton Edwards Intelligence</h1>
      <p>Period: <strong>{start}</strong> &mdash; <strong>{end}</strong>
         &nbsp;&nbsp;&middot;&nbsp;&nbsp;
         Generated: {datetime.now().strftime("%B %d, %Y &nbsp; %I:%M %p")}</p>
    </div>
    <div class="report-header-right">
      <button class="print-btn" onclick="window.print()">Print Report</button>
      <div class="status-badge">{status_text}</div>
    </div>
  </div>

  <div class="summary-grid">
    <div class="summary-card" style="border-top-color:{RED}">
      <div class="num" style="color:{RED}">{len(mn_blocked)}</div>
      <div class="lbl">Blocked — No Notes</div>
    </div>
    <div class="summary-card" style="border-top-color:{YELLOW}">
      <div class="num" style="color:{YELLOW}">{len(inc)}</div>
      <div class="lbl">Incomplete Days</div>
    </div>
    <div class="summary-card" style="border-top-color:{YELLOW}">
      <div class="num" style="color:{YELLOW}">{len(foh)}</div>
      <div class="lbl">Full Overhead Days</div>
    </div>
    <div class="summary-card" style="border-top-color:{YELLOW}">
      <div class="num" style="color:{YELLOW}">{len(col)}</div>
      <div class="lbl">Collab Citations</div>
    </div>
    <div class="summary-card" style="border-top-color:{ACCENT3}">
      <div class="num" style="color:{ACCENT3}">{len(set(t["employee"] for t in tmw))}</div>
      <div class="lbl">Teamwork</div>
    </div>
  </div>

  <div class="tabs">
    <div class="tab active" id="tab-flags" onclick="showTab('flags')">Flags</div>
    <div class="tab" id="tab-employee" onclick="showTab('employee')">By Employee</div>
    <div class="tab" id="tab-project" onclick="showTab('project')">By Project</div>
    <div class="tab" id="tab-teamwork" onclick="showTab('teamwork')">Teamwork</div>
  </div>

  <!-- FLAGS TAB -->
  <div class="tab-content active" id="content-flags">
    {section("Entries Without Notes", RED, mn_html, len(mn_blocked))}
    {section("Incomplete Days (< 8h)", YELLOW, inc_html, len(inc))}
    {section("Full Overhead / General Days", YELLOW, foh_html, len(foh))}
    {section("Collaboration Citations", ACCENT3, col_html, len(col))}
  </div>

  <!-- BY EMPLOYEE TAB -->
  <div class="tab-content" id="content-employee">
    {emp_sections}
  </div>

  <!-- BY PROJECT TAB -->
  <div class="tab-content" id="content-project">
    {proj_html}
  </div>

  <!-- TEAMWORK TAB -->
  <div class="tab-content" id="content-teamwork">
    {section("Teamwork", ACCENT3, tmw_html, len(set(t["employee"] for t in tmw)))}
  </div>

</div>
</body>
</html>"""
    return html

# ── LUCA CHAT ─────────────────────────────────────────────────────────────────

LUCA_CONFIG    = REPORT_DIR / "luca_config.json"
LUCA_REFERENCE = REPORT_DIR / "luca_reference.json"
ACTIONS_LOG    = REPORT_DIR / "luca_actions.json"
PLAYBOOK       = REPORT_DIR / "luca_playbook.json"
GEMINI_MODEL   = "gemini-2.0-flash"

# luca_knowledge.yaml lives next to the script / exe (project folder),
# not in ~/Documents/Luca — it is a developer/admin-maintained file.
LUCA_KNOWLEDGE = _base_dir() / "luca_knowledge.yaml"

def _load_luca_knowledge() -> str:
    """Return the contents of luca_knowledge.yaml as a plain text string.
    Falls back gracefully if the file is missing or unreadable."""
    if not LUCA_KNOWLEDGE.exists():
        return ""
    try:
        return LUCA_KNOWLEDGE.read_text(encoding="utf-8")
    except Exception:
        return ""

# Default reference data — written to disk on first run so the user can edit it.
_DEFAULT_REFERENCE = {
    "overhead_codes": {
        "General":             "Non-billable general office overhead and administration",
        "Business Development":"Client prospecting, proposals, and BD activities",
        "Process Improvement": "Internal workflow, tools, and systems improvement",
        "PTO":                 "Paid time off — no note required (auto-approved)",
        "Vacation":            "Vacation leave — no note required (auto-approved)",
        "Holiday":             "Company-observed holidays",
        "Sick":                "Sick leave",
        "Training":            "Professional development and continuing education",
        "Admin":               "Administrative tasks",
        "Marketing":           "Marketing, social media, and brand activities",
        "Office":              "Facilities, IT, and general office management",
    },
    "employee_weekly_hours": {
        "Gordon Shisler": 32.0,
    },
    "billable_target_pct": 75,
    "notes": (
        "Edit overhead_codes to describe each Ajera overhead category. "
        "Edit employee_weekly_hours to set non-standard weekly targets "
        "(all others default to 40 h/week)."
    ),
}

# ── Action system helpers ──────────────────────────────────────────────────────

def load_actions():
    """Return the flat list of all logged actions."""
    if not ACTIONS_LOG.exists():
        return []
    try:
        return json.loads(ACTIONS_LOG.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_action(action):
    """Append one action record to the log."""
    actions = load_actions()
    actions.append(action)
    ACTIONS_LOG.write_text(
        json.dumps(actions, indent=2, default=str), encoding="utf-8")

def load_playbook():
    """Return the learning playbook (patterns + outcomes)."""
    if not PLAYBOOK.exists():
        return {"version": 1, "patterns": {}}
    try:
        return json.loads(PLAYBOOK.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "patterns": {}}

def save_playbook(pb):
    PLAYBOOK.write_text(
        json.dumps(pb, indent=2, default=str), encoding="utf-8")

def record_in_playbook(issue_type, employee, action_type, outcome=None):
    """Update the firm's reinforcement-learning playbook with a new event.

    Each unique (issue_type, employee) pair is a pattern key.  When an outcome
    is supplied the playbook recalculates which action type has the best
    resolution track record for that pattern.
    """
    from collections import Counter as _Counter
    pb  = load_playbook()
    key = f"{issue_type}::{employee}"
    pat = pb["patterns"].setdefault(key, {
        "issue_type":         issue_type,
        "employee":           employee,
        "occurrences":        0,
        "action_history":     [],
        "recommended_action": action_type,
        "notes":              "",
    })
    pat["occurrences"] += 1
    pat["last_seen"]    = str(date.today())
    if outcome:
        pat["action_history"].append({
            "type":    action_type,
            "date":    str(date.today()),
            "outcome": outcome,
        })
        resolved = [h for h in pat["action_history"]
                    if h.get("outcome") == "resolved"]
        if resolved:
            pat["recommended_action"] = _Counter(
                h["type"] for h in resolved).most_common(1)[0][0]
    save_playbook(pb)

def serialize_actions_context():
    """Format the action log and playbook as a text block for Luca's context."""
    L       = []
    actions = load_actions()
    pb      = load_playbook()

    if actions:
        recent = actions[-30:]     # most recent 30 entries
        L.append("══ FIRM ACTION LOG (recent) ════════════════════════════════")
        for a in recent:
            ts      = str(a.get("timestamp", ""))[:10]
            outcome = a.get("outcome") or "pending"
            L.append(f"  [{a.get('type','?')}]  {a.get('employee','')}  {ts}  "
                     f"issue:{a.get('issue_type','')}  status:{outcome}")
            if a.get("issue_detail"):
                L.append(f"    → {a['issue_detail']}")
        L.append("")

    if pb.get("patterns"):
        L.append("══ LEARNED PATTERNS (PLAYBOOK) ═════════════════════════════")
        L.append("(Patterns Luca has observed + outcomes of actions taken)")
        for key, pat in sorted(pb["patterns"].items()):
            n        = pat.get("occurrences", 0)
            rec      = pat.get("recommended_action", "REMINDER")
            last     = pat.get("last_seen", "")
            hist     = pat.get("action_history", [])
            resolved = sum(1 for h in hist if h.get("outcome") == "resolved")
            L.append(f"  {pat['employee']}  |  {pat['issue_type']}  "
                     f"|  seen {n}x  last:{last}  "
                     f"recommended:{rec}  resolved:{resolved}/{len(hist)}")
            if pat.get("notes"):
                L.append(f"    Notes: {pat['notes']}")
        L.append("")

    return "\n".join(L)

# ──────────────────────────────────────────────────────────────────────────────

def _load_luca_reference():
    """Load (and create if missing) the firm reference / config JSON."""
    if not LUCA_REFERENCE.exists():
        try:
            LUCA_REFERENCE.write_text(
                json.dumps(_DEFAULT_REFERENCE, indent=2), encoding="utf-8")
        except Exception:
            pass
        return dict(_DEFAULT_REFERENCE)
    try:
        data = json.loads(LUCA_REFERENCE.read_text(encoding="utf-8"))
        # Merge any keys added to the default that aren't in the user's file yet
        for k, v in _DEFAULT_REFERENCE.items():
            if k not in data:
                data[k] = v
        return data
    except Exception:
        return dict(_DEFAULT_REFERENCE)

LUCA_SYSTEM  = """\
You are LUCA, an intelligent timesheet audit assistant for Carlton Edwards, \
an architectural firm with two legal entities and three studio locations:

  Company 1 — Carlton Architecture PA
    • Asheville studio  (DepartmentKey 2)

  Company 2 — Carlton Edwards PLLC
    • Nashville studio  (DepartmentKey 4)
    • Memphis studio    (DepartmentKey 6)

  Consultants (DepartmentKey 7) may appear across either company.

When filtering or grouping by studio, company, or location, always use these \
keys. If the user asks about "Asheville" or "Carlton Architecture", that maps \
to CompanyKey for Carlton Architecture PA and DepartmentKey 2. "Nashville" and \
"Memphis" belong to Carlton Edwards PLLC.

You have been given a rich dataset that includes:
  • Complete audit-period timesheet data (flags, per-employee log, per-project log)
  • 3 prior weeks of rolling timesheet data to reveal trends
  • The full active employee roster with studio and department
  • Firm reference: overhead code definitions, per-employee hour targets, billable targets
  • Recent action log and learned playbook of past patterns + outcomes

CAPABILITIES
- Answer any question about the data precisely, citing names, numbers, and dates
- Identify trends by comparing the audit period against prior weeks
- Recognize repeat patterns (e.g., chronic short days, recurring missing notes)
- Reference the playbook to tell the user what has worked before for this pattern
- Propose concrete actions the user can take immediately

ACTION PROPOSALS
When asked to propose an action (or when a clear action is warranted), include
a structured block in your response EXACTLY in this format:

[ACTION]
{
  "type": "REMINDER",
  "employee": "First Last",
  "issue_type": "missing_notes",
  "issue_detail": "brief description of the specific issue",
  "subject": "Email subject line",
  "message": "Full message text ready to send (address it to the employee, sign off with [Your name])"
}
[/ACTION]

Action types: REMINDER (request correction), EXCEPTION (log approved exception), \
CORRECTION (recode flag), ESCALATE (repeat offender → management), NOTE (audit note).

Always explain your reasoning before or after the [ACTION] block. \
If the playbook shows a prior action with a known outcome, reference it explicitly.

LIVE AJERA QUERY TOOLS
You have two tools that let you query Ajera in real time — independent of the
pre-loaded audit dataset.  Use them when:
  • The user asks about a date range not covered by the audit context
  • The user asks "right now" or "as of today" questions
  • You need to verify or supplement the loaded data with fresh figures
  • The user asks about a specific employee or project outside the audit window

Do NOT call the tools for data already present in the audit context — answer
from the context first and only fetch live data when genuinely needed.
When you call a tool, briefly tell the user what you are looking up before the
result arrives (e.g. "Let me pull Emily's timesheets from January…").

FIRM KNOWLEDGE BASE
The firm's business rules, phase definitions, billing confusion patterns, and
CEC vs architecture distinction are loaded below from luca_knowledge.yaml.
Apply these rules actively when evaluating timesheet entries and notes.

{knowledge_block}
"""

# ── LUCA TOOL DEFINITIONS (Anthropic tool_use format) ─────────────────────────
# These give Ask Luca the ability to query Ajera on demand, independent of any
# pre-loaded audit run.  They are passed to every claude API call so Claude can
# decide when to use them based on the user's question.
LUCA_TOOLS = [
    {
        "name": "query_ajera_employees",
        "description": (
            "Fetch the current list of active employees from Ajera, the firm's project "
            "management system. Returns each employee's full name, studio (Asheville / "
            "Nashville / Memphis / Consultant), and employee key. Use this when the user "
            "asks about headcount, a specific person's department, or who is currently "
            "on staff — and that information is not already in the loaded audit context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "query_ajera_org_structure",
        "description": (
            "Fetch the firm's full organizational structure from Ajera: all companies "
            "(with CompanyKey) and all departments (with DepartmentKey, overhead %). "
            "Also fetches the employee list cross-referenced against companies and "
            "departments so you can see exactly which studio each person belongs to. "
            "Use this when the user asks about the firm structure, companies, studios, "
            "departments, or wants to filter employees by company or department."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "query_ajera_activities",
        "description": (
            "Fetch the complete list of active activities (labor types / billing "
            "categories) from Ajera, with their ActivityKey and description. "
            "Use this when the user asks what activity codes exist, wants to find "
            "an activity key, or needs to understand how time is categorised."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "query_ajera_projects",
        "description": (
            "Fetch the list of active/open projects from Ajera. Returns each project's "
            "ProjectKey, ID (short code), and Description (full name). Use this when "
            "the user asks for a project list, wants to find a project key, or needs "
            "to look up a project by name or code. Lightweight — does not include phases."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "query_ajera_project_phases",
        "description": (
            "Fetch phases (and their PhaseKey values) for projects in Ajera. "
            "Also extracts activity keys from phase resources where available. "
            "Optionally filter by a project name or ID fragment. If no filter is "
            "given, returns phases for all active projects (may be large). "
            "Use this when the user asks about phases, phase keys, or activities "
            "within a specific project."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_filter": {
                    "type": "string",
                    "description": (
                        "Optional: a project name or ID fragment to narrow results "
                        "(case-insensitive substring match). Leave empty for all projects."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "query_ajera_timesheets",
        "description": (
            "Fetch detailed timesheet entries from Ajera for a given date range. "
            "Returns project and overhead time entries for every employee: hours, "
            "project name, phase, activity, and notes. Use this when the user asks "
            "about a period outside the current audit window, wants to compare against "
            "a specific historical week, or needs data not present in the pre-loaded "
            "context. Keep queries to 90 days or fewer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start of the period in YYYY-MM-DD format.",
                },
                "end_date": {
                    "type": "string",
                    "description": "End of the period in YYYY-MM-DD format.",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
]


def _luca_tools_to_gemini():
    """Convert LUCA_TOOLS (Claude format) to Gemini function declaration list."""
    if not _GEMINI_AVAILABLE:
        return []
    declarations = []
    for tool in LUCA_TOOLS:
        declarations.append({
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
        })
    return declarations


def _execute_ajera_tool(tool_name, tool_input):
    """Execute one Ajera API tool call and return a human-readable text result.

    This runs in the _stream_answer background thread so blocking I/O is fine.
    Returns a plain-text string suitable for Claude to read as a tool_result.

    For all reference tools (org structure, activities, employees, projects,
    project phases) data is served from the local cache when the cache exists
    and is less than CACHE_MAX_AGE hours old.  Timesheets are always live.
    """
    if tool_name == "query_ajera_org_structure":
        cache      = load_ajera_cache()
        age        = cache_age_hours()
        from_cache = bool(cache) and age < CACHE_MAX_AGE
        source_note = (f"[From local cache — synced {age:.0f}h ago]"
                       if from_cache else "[Live from Ajera API]")

        if from_cache:
            companies = cache.get("companies", [])
            depts     = cache.get("departments", [])
            emps      = cache.get("employees", [])
        else:
            tok = login(1)
            try:
                companies = get_companies(tok)
                depts     = get_departments(tok)
                emps      = get_employees(tok)
            finally:
                logout(tok)

        # Build lookup maps
        co_map   = {c.get("CompanyKey"):    (c.get("Description") or "").strip()
                    for c in companies}
        dept_map = {d.get("DepartmentKey"): (d.get("Department")  or "").strip()
                    for d in depts}

        lines = ["FIRM ORGANIZATIONAL STRUCTURE", "=" * 62,
                 source_note]

        lines.append(f"\nCOMPANIES  ({len(companies)})")
        lines.append(f"  {'CompanyKey':<12}  {'Description':<36}  Status")
        lines.append("  " + "-" * 58)
        for c in sorted(companies, key=lambda x: x.get("CompanyKey", 0)):
            ck   = c.get("CompanyKey", "?")
            desc = (c.get("Description") or "").strip()
            sta  = (c.get("Status")      or "").strip()
            lines.append(f"  {str(ck):<12}  {desc:<36}  {sta}")

        lines.append(f"\nDEPARTMENTS  ({len(depts)})")
        lines.append(f"  {'DeptKey':<10}  {'Department':<24}  {'Overhead %':<12}  Status")
        lines.append("  " + "-" * 60)
        for d in sorted(depts, key=lambda x: x.get("DepartmentKey", 0)):
            dk  = d.get("DepartmentKey", "?")
            dn  = (d.get("Department") or "").strip()
            oh  = d.get("OverheadPercent", "")
            sta = (d.get("Status")     or "").strip()
            oh_str = f"{oh:.1f}%" if isinstance(oh, (int, float)) else str(oh)
            lines.append(f"  {str(dk):<10}  {dn:<24}  {oh_str:<12}  {sta}")

        # Employee breakdown by company/department (if those fields come back)
        by_co_dept = defaultdict(lambda: defaultdict(list))
        flat_emps  = []
        for e in emps:
            fn   = (e.get("FirstName")  or "").strip()
            mn   = (e.get("MiddleName") or "").strip()
            ln   = (e.get("LastName")   or "").strip()
            full = " ".join(p for p in [fn, mn, ln] if p)
            ek   = e.get("EmployeeKey", "?")
            ck   = e.get("CompanyKey")
            dk   = e.get("DepartmentKey")
            if ck or dk:
                co_name   = co_map.get(ck,   f"Company {ck}"   if ck else "Unknown")
                dept_name = dept_map.get(dk, f"Dept {dk}"      if dk else "Unknown")
                by_co_dept[co_name][dept_name].append((full, ek))
            else:
                flat_emps.append((full, ek))

        if by_co_dept:
            lines.append(f"\nEMPLOYEES BY COMPANY / DEPARTMENT  ({len(emps)} active)")
            for co_name in sorted(by_co_dept):
                lines.append(f"\n  {co_name}")
                for dept_name in sorted(by_co_dept[co_name]):
                    lines.append(f"    {dept_name}:")
                    for full, ek in sorted(by_co_dept[co_name][dept_name]):
                        lines.append(f"      {full:<30}  EK: {ek}")
        elif flat_emps:
            lines.append(f"\nEMPLOYEES  ({len(flat_emps)} active)")
            lines.append("  (Company/Dept keys not returned by ListEmployees —"
                         " use query_ajera_employees for the full roster)")

        return "\n".join(lines)

    elif tool_name == "query_ajera_activities":
        cache      = load_ajera_cache()
        age        = cache_age_hours()
        from_cache = bool(cache) and age < CACHE_MAX_AGE
        source_note = (f"[From local cache — synced {age:.0f}h ago]"
                       if from_cache else "[Live from Ajera API]")

        if from_cache:
            acts = cache.get("activities", [])
        else:
            tok = login(1)
            try:
                acts = get_activities(tok)
            finally:
                logout(tok)

        acts_sorted = sorted(acts, key=lambda a: (a.get("Description") or "").lower())
        lines = [
            f"ACTIVITIES / LABOR TYPES  ({len(acts_sorted)} active)",
            "=" * 52,
            source_note,
            f"  {'ActivityKey':<14}  Description",
            "  " + "-" * 48,
        ]
        for a in acts_sorted:
            ak   = a.get("ActivityKey", "?")
            desc = (a.get("Description") or "").strip()
            lines.append(f"  {str(ak):<14}  {desc}")
        return "\n".join(lines)

    elif tool_name == "query_ajera_employees":
        cache      = load_ajera_cache()
        age        = cache_age_hours()
        from_cache = bool(cache) and age < CACHE_MAX_AGE
        source_note = (f"[From local cache — synced {age:.0f}h ago]"
                       if from_cache else "[Live from Ajera API]")

        if from_cache:
            emps      = cache.get("employees", [])
            companies = cache.get("companies", [])
            depts     = cache.get("departments", [])
        else:
            tok = login(1)
            try:
                emps      = get_employees(tok)
                companies = get_companies(tok)
                depts     = get_departments(tok)
            finally:
                logout(tok)

        co_map   = {c.get("CompanyKey"):    (c.get("Description") or "").strip()
                    for c in companies}
        dept_map = {d.get("DepartmentKey"): (d.get("Department")  or "").strip()
                    for d in depts}

        rows = []
        for e in emps:
            ek   = e.get("EmployeeKey", "?")
            fn   = (e.get("FirstName")  or "").strip()
            mn   = (e.get("MiddleName") or "").strip()
            ln   = (e.get("LastName")   or "").strip()
            full = " ".join(p for p in [fn, mn, ln] if p)
            ck   = e.get("CompanyKey")
            dk   = e.get("DepartmentKey")
            co   = co_map.get(ck,   "") if ck else ""
            dept = dept_map.get(dk, "") if dk else ""
            rows.append((full, ek, co, dept))

        rows.sort(key=lambda r: (r[2], r[3], r[0].lower()))
        has_org = any(r[2] or r[3] for r in rows)

        lines = [
            f"ACTIVE EMPLOYEE ROSTER  ({len(rows)} employees)",
            "=" * 62,
            source_note,
        ]
        if has_org:
            lines.append(f"  {'Name':<30}  {'EK':<8}  {'Company':<28}  Department")
            lines.append("  " + "-" * 80)
            for full, ek, co, dept in rows:
                lines.append(f"  {full:<30}  {str(ek):<8}  {co:<28}  {dept}")
        else:
            lines.append(f"  {'Name':<30}  Employee Key")
            lines.append("  " + "-" * 48)
            for full, ek, *_ in rows:
                lines.append(f"  {full:<30}  {ek}")

        return "\n".join(lines)

    elif tool_name == "query_ajera_projects":
        cache      = load_ajera_cache()
        age        = cache_age_hours()
        from_cache = bool(cache) and age < CACHE_MAX_AGE
        source_note = (f"[From local cache — synced {age:.0f}h ago]"
                       if from_cache else "[Live from Ajera API]")

        if from_cache:
            projects = cache.get("projects", [])
        else:
            tok = login(1)
            try:
                projects = get_project_list(tok)
            finally:
                logout(tok)

        projects_sorted = sorted(projects, key=lambda p: (p.get("ID") or "").lower())
        lines = [
            f"ACTIVE / OPEN PROJECTS  ({len(projects_sorted)} projects)",
            "=" * 62,
            source_note,
            f"  {'ID':<18}  {'Description':<36}  ProjectKey",
            "  " + "-" * 58,
        ]
        for p in projects_sorted:
            pid  = (p.get("ID")          or "").strip()
            desc = (p.get("Description") or "").strip()
            pk   = p.get("ProjectKey", "?")
            lines.append(f"  {pid:<18}  {desc:<36}  {pk}")
        return "\n".join(lines)

    elif tool_name == "query_ajera_project_phases":
        pf = (tool_input.get("project_filter") or "").strip().lower()

        cache      = load_ajera_cache()
        age        = cache_age_hours()
        from_cache = bool(cache) and age < CACHE_MAX_AGE
        source_note = (f"[From local cache — synced {age:.0f}h ago]"
                       if from_cache else "[Live from Ajera API]")

        if from_cache:
            # Build project+phase data from the cache
            all_projects = cache.get("projects", [])
            cached_phases = cache.get("phases", [])

            if pf:
                matched_pkeys = {
                    p["ProjectKey"] for p in all_projects
                    if pf in (p.get("ID") or "").lower()
                    or pf in (p.get("Description") or "").lower()
                }
                filtered_phases = [ph for ph in cached_phases
                                   if ph.get("ProjectKey") in matched_pkeys]
                filtered_projects = [p for p in all_projects
                                     if p.get("ProjectKey") in matched_pkeys]
            else:
                filtered_phases   = cached_phases
                filtered_projects = all_projects

            if not filtered_projects:
                return f"No projects matched the filter '{pf}'."

            lines = ["PROJECT PHASES & ACTIVITIES", "=" * 70, source_note]
            # Group phases by project
            from collections import defaultdict as _pdd
            phases_by_proj = _pdd(list)
            for ph in filtered_phases:
                phases_by_proj[ph.get("ProjectKey")].append(ph)

            proj_list = sorted(filtered_projects,
                               key=lambda p: (p.get("ID") or "").lower())
            cap_note = ""
            if len(proj_list) > 50:
                proj_list = proj_list[:50]
                cap_note = "\n[Results capped at 50 projects. Use project_filter to narrow.]"

            for p in proj_list:
                pid  = (p.get("ID")          or "").strip()
                desc = (p.get("Description") or "").strip()
                pk   = p.get("ProjectKey", "?")
                lines.append(f"\n{pid}  —  {desc}  [ProjectKey: {pk}]")
                ph_list = sorted(phases_by_proj.get(pk, []),
                                 key=lambda x: (x.get("PhaseID") or "").lower())
                if not ph_list:
                    lines.append("    (no phases in cache)")
                else:
                    lines.append(f"  {'PhaseKey':<10}  {'ID':<14}  {'Description':<36}  Status")
                    lines.append("  " + "-" * 72)
                    for ph in ph_list:
                        phk  = ph.get("PhaseKey", "?")
                        phid = (ph.get("PhaseID")   or "").strip()
                        phd  = (ph.get("PhaseDesc") or "").strip()
                        phs  = (ph.get("PhaseStatus") or "").strip()
                        lines.append(f"  {str(phk):<10}  {phid:<14}  {phd:<36}  {phs}")

            return "\n".join(lines) + cap_note

        else:
            # Live API path
            tok = login(1)
            try:
                all_projects = get_project_list(tok)
            finally:
                logout(tok)

            if pf:
                filtered = [p for p in all_projects
                            if pf in (p.get("ID") or "").lower()
                            or pf in (p.get("Description") or "").lower()]
            else:
                filtered = all_projects

            if not filtered:
                return f"No projects matched the filter '{pf}'."

            if len(filtered) > 50:
                filtered = filtered[:50]
                cap_note = "\n[Results capped at 50 projects. Use project_filter to narrow.]"
            else:
                cap_note = ""

            project_keys = [p["ProjectKey"] for p in filtered if p.get("ProjectKey")]
            tok2 = login(1)
            try:
                detailed = get_project_details(tok2, project_keys)
            finally:
                logout(tok2)

            lines = [
                "PROJECT PHASES & ACTIVITIES",
                "=" * 70,
                source_note,
            ]
            for proj in sorted(detailed, key=lambda p: (p.get("ID") or "").lower()):
                pid  = (proj.get("ID")          or "").strip()
                desc = (proj.get("Description") or "").strip()
                pk   = proj.get("ProjectKey", "?")
                lines.append(f"\n{pid}  —  {desc}  [ProjectKey: {pk}]")

                phase_sources = []
                for ig in (proj.get("InvoiceGroups") or []):
                    phase_sources.extend(ig.get("Phases") or [])
                phase_sources.extend(proj.get("Phases") or [])

                if not phase_sources:
                    lines.append("    (no phases found)")
                else:
                    lines.append(f"  {'PhaseKey':<10}  {'ID':<14}  {'Description':<36}  Status")
                    lines.append("  " + "-" * 72)
                    for ph in sorted(phase_sources, key=lambda x: (x.get("ID") or "").lower()):
                        phk  = ph.get("PhaseKey", "?")
                        phid = (ph.get("ID")          or "").strip()
                        phd  = (ph.get("Description") or "").strip()
                        phs  = (ph.get("Status")      or "").strip()
                        lines.append(f"  {str(phk):<10}  {phid:<14}  {phd:<36}  {phs}")

                        activities_seen = {}
                        for res in (ph.get("Resources") or []):
                            ak  = res.get("ActivityKey")
                            an  = (res.get("Activity") or res.get("Description") or "").strip()
                            if ak and ak not in activities_seen:
                                activities_seen[ak] = an
                        if activities_seen:
                            lines.append(f"    Activities:")
                            for ak, an in sorted(activities_seen.items()):
                                lines.append(f"      ActivityKey {ak}: {an}")

            return "\n".join(lines) + cap_note

    elif tool_name == "query_ajera_timesheets":
        start_str = tool_input.get("start_date", "")
        end_str   = tool_input.get("end_date",   "")
        try:
            ts_start = datetime.strptime(start_str, "%Y-%m-%d").date()
            ts_end   = datetime.strptime(end_str,   "%Y-%m-%d").date()
        except ValueError as exc:
            return f"ERROR: invalid date format — {exc}"
        if (ts_end - ts_start).days > 90:
            return "ERROR: date range too large (max 90 days). Please narrow the range."
        if ts_end < ts_start:
            return "ERROR: end_date is before start_date."

        # ── Cache-first: serve from rolling local cache if range is covered ──
        # Deterministic lookup — no LLM involvement.
        _cache  = load_ajera_cache()
        _c_emps = _cache.get("employees", [])

        _use_cache = False
        _earliest, _latest = weeks_covered_by_cache(_cache)
        if (_earliest is not None
                and _earliest <= ts_start
                and _latest   >= ts_end):
            _use_cache = True   # week-keyed cache fully covers the requested range

        if _use_cache:
            detailed = ts_details_from_cache(_cache, ts_start, ts_end)
            ek_name  = {e["EmployeeKey"]:
                        f"{e.get('FirstName','')} {e.get('LastName','')}".strip()
                        for e in _c_emps}
        else:
            tok1 = login(1)
            tok2 = login(2)
            try:
                emps      = get_employees(tok1)
                ek_name   = {e["EmployeeKey"]:
                             f"{e.get('FirstName','')} {e.get('LastName','')}".strip()
                             for e in emps}
                ts_list   = get_timesheet_list(tok2, ts_start, ts_end)
                ts_keys   = [t["Timesheet Key"] for t in ts_list if t.get("Timesheet Key")]
                detailed  = get_timesheet_detail(tok2, ts_keys) if ts_keys else []
            finally:
                logout(tok1)
                logout(tok2)

        if not detailed:
            return f"No timesheet data found between {ts_start} and {ts_end}."

        # Organise: emp_name -> date -> list of entry strings
        emp_data = defaultdict(lambda: defaultdict(list))
        for sheet in detailed:
            ek    = sheet.get("EmployeeKey")
            ename = ek_name.get(ek, f"EK:{ek}")
            ts_ds = str(sheet.get("TimesheetDate", ""))

            for entry in (sheet.get("Project", {}).get("Detail") or []):
                pd  = entry.get("Project Description", "")
                ph  = entry.get("Phase Description", "")
                act = entry.get("Activity", "")
                for d in range(1, 8):
                    reg = float(entry.get(f"D{d} Regular")  or 0)
                    ovt = float(entry.get(f"D{d} Overtime") or 0)
                    hrs = reg + ovt
                    note = (entry.get(f"D{d} Notes") or "").strip()
                    if hrs <= 0:
                        continue
                    dt = d_to_date(ts_ds, d)
                    if dt < ts_start or dt > ts_end:
                        continue
                    label = pd
                    if ph:  label += f" / {ph}"
                    if act: label += f" [{act}]"
                    note_part = f'"{note}"' if note else "NO NOTE"
                    emp_data[ename][dt].append(f"  {hrs:.1f}h  {label}  — {note_part}")

            for entry in (sheet.get("Overhead", {}).get("Detail") or []):
                desc = entry.get("Timesheet Overhead Group Detail", "")
                for d in range(1, 8):
                    hrs  = float(entry.get(f"D{d} Regular") or 0)
                    note = (entry.get(f"D{d} Notes") or "").strip()
                    if hrs <= 0:
                        continue
                    dt = d_to_date(ts_ds, d)
                    if dt < ts_start or dt > ts_end:
                        continue
                    note_part = f'"{note}"' if note else "no note"
                    emp_data[ename][dt].append(
                        f"  {hrs:.1f}h  [Overhead] {desc}  — {note_part}")

        lines = [f"TIMESHEET DATA  {ts_start}  to  {ts_end}", "=" * 60]
        for ename in sorted(emp_data):
            lines.append(f"\n{ename}")
            for dt in sorted(emp_data[ename]):
                day_total = sum(
                    float(s.strip().split("h")[0])
                    for s in emp_data[ename][dt]
                    if s.strip()[0:1].isdigit()
                )
                lines.append(f"  {dt.strftime('%a %m/%d/%Y')}  ({day_total:.1f}h)")
                lines.extend(emp_data[ename][dt])

        result = "\n".join(lines)
        if len(result) > 24_000:
            result = result[:24_000] + (
                "\n\n[TRUNCATED — too many entries. Try a shorter date range or ask"
                " about a specific employee.]")
        return result

    else:
        return f"Unknown tool: {tool_name}"


def _load_api_key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    if LUCA_CONFIG.exists():
        try:
            return json.loads(LUCA_CONFIG.read_text(encoding="utf-8")).get("anthropic_api_key")
        except Exception:
            pass
    return None

def _save_api_key(key):
    cfg = {}
    if LUCA_CONFIG.exists():
        try:
            cfg = json.loads(LUCA_CONFIG.read_text(encoding="utf-8"))
        except Exception:
            pass
    cfg["anthropic_api_key"] = key
    LUCA_CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

def _load_gemini_key_global():
    """Load Gemini API key from env var or config file (module-level helper)."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    if LUCA_CONFIG.exists():
        try:
            data = json.loads(LUCA_CONFIG.read_text(encoding="utf-8"))
            return data.get("gemini_api_key", "")
        except Exception:
            pass
    return ""

def _save_gemini_key_global(key):
    """Save Gemini API key to config file (module-level helper)."""
    data = {}
    if LUCA_CONFIG.exists():
        try:
            data = json.loads(LUCA_CONFIG.read_text(encoding="utf-8"))
        except Exception:
            pass
    data["gemini_api_key"] = key
    LUCA_CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")

def serialize_audit_context(flags, by_emp, by_proj, start, end,
                            employees=None, prior_by_emp=None,
                            emp_week_totals=None, reference=None):
    """Produce a richly structured text document from the audit data for Claude."""
    L = []
    dept_name = lambda d: DEPARTMENTS.get(d, "Unknown")

    L.append(f"AUDIT PERIOD: {start}  to  {end}")
    L.append(f"EMPLOYEES IN PERIOD: {len(by_emp)}")
    L.append(f"PROJECTS IN PERIOD:  {len(by_proj)}")
    L.append("")

    # ── Firm reference / configuration ────────────────────────────────────────
    if reference:
        L.append("══ FIRM REFERENCE & CONFIGURATION ═════════════════════════")
        btp = reference.get("billable_target_pct")
        if btp:
            L.append(f"  Billable hour target: {btp}% of total hours")
        emp_targets = reference.get("employee_weekly_hours", {})
        if emp_targets:
            L.append("  Non-standard weekly hour targets:")
            for name, wk in emp_targets.items():
                L.append(f"    {name}: {wk}h/week  ({wk/5:.1f}h/day target)")
        L.append("  All other employees: 40h/week  (8h/day target)")
        oh_codes = reference.get("overhead_codes", {})
        if oh_codes:
            L.append("  Overhead code definitions:")
            for code, desc in oh_codes.items():
                L.append(f"    [{code}] {desc}")
        L.append("")

    # ── Active employee roster ─────────────────────────────────────────────────
    if employees:
        L.append("══ ACTIVE EMPLOYEE ROSTER ══════════════════════════════════")
        by_dept = defaultdict(list)
        for e in employees:
            dept_id = e.get("Department", 7)
            name = f"{e.get('FirstName','').strip()} {e.get('LastName','').strip()}".strip()
            by_dept[dept_id].append(name)
        for did in sorted(by_dept.keys()):
            L.append(f"  {dept_name(did)} studio ({len(by_dept[did])} employees):")
            for n in sorted(by_dept[did]):
                target_note = ""
                if reference:
                    wk = reference.get("employee_weekly_hours", {}).get(n)
                    if wk:
                        target_note = f"  [{wk}h/week]"
                L.append(f"    • {n}{target_note}")
        L.append("")

    blocked = [f for f in flags["missing_notes"] if not f.get("is_pto")]
    pto_ok  = [f for f in flags["missing_notes"] if  f.get("is_pto")]
    L.append("SUMMARY OF FLAGS:")
    L.append(f"  {len(blocked)} project entries with NO note (action required)")
    L.append(f"  {len(pto_ok)}  PTO/overhead entries with no note (OK — green)")
    L.append(f"  {len(flags['incomplete_days'])} short workdays (< daily target hours)")
    L.append(f"  {len(flags['full_overhead'])} full overhead / general days")
    L.append(f"  {len(flags['collab'])} collaboration citations (sync-work mentions in notes)")
    L.append("")

    # Missing notes
    if flags["missing_notes"]:
        L.append("── MISSING NOTES ──────────────────────────────────────────")
        for f in flags["missing_notes"]:
            tag = "PTO/OK" if f.get("is_pto") else "BLOCKED"
            L.append(f"  [{tag}]  {f['emp']} ({dept_name(f['dept'])})  {f['date']}  |  {f['desc']}  {f['hrs']}h")
        L.append("")

    # Incomplete days
    if flags["incomplete_days"]:
        L.append("── SHORT DAYS ─────────────────────────────────────────────")
        for f in flags["incomplete_days"]:
            L.append(f"  {f['emp']} ({dept_name(f['dept'])})  {f['date']}  |  "
                     f"logged {f['hrs']}h  short {f['miss']}h  |  "
                     f"week total {f.get('week_total',0):.1f}h  "
                     f"prior week {f.get('prior_week_total',0):.1f}h")
        L.append("")

    # Full overhead
    if flags["full_overhead"]:
        L.append("── FULL OVERHEAD DAYS ─────────────────────────────────────")
        for f in flags["full_overhead"]:
            note_tag = "has note" if f.get("has_note") else "NO NOTE"
            L.append(f"  {f['emp']} ({dept_name(f['dept'])})  {f['date']}  |  "
                     f"{f['hrs']}h  [{f.get('descs','')}]  ({note_tag})")
        L.append("")

    # Collaboration Citations
    if flags["collab"]:
        from collections import defaultdict as _cdd2
        L.append("── COLLABORATION CITATIONS ────────────────────────────────")
        L.append("(Organised by mentioned employee — who cited them, when, on what project, verbatim note)")
        by_m: dict = _cdd2(list)
        for c in flags["collab"]:
            by_m[c["mentioned_emp"]].append(c)
        for m_emp in sorted(by_m.keys()):
            L.append(f"  {m_emp}:")
            for c in sorted(by_m[m_emp],
                            key=lambda x: (x.get("date_obj") or date.min, x["cited_by"])):
                note_short = c["note"][:120].replace("\n", " ")
                L.append(f"    {c['date']}  cited by {c['cited_by']}  |  "
                         f"project: {c['project']}  phase: {c['phase']}  {c['hours']:.1f}h")
                L.append(f"    note: \"{note_short}\"")
        L.append("")

    # ── Prior weeks rolling data ───────────────────────────────────────────────
    if prior_by_emp:
        L.append("══ PRIOR 3-WEEK ROLLING DATA ═══════════════════════════════")
        L.append("(Entries logged in the 3 weeks before the audit period — use for trend analysis)")
        L.append("")
        # Weekly summaries per employee
        if emp_week_totals:
            audit_ws = payroll_week_start(start)
            prior_weeks = sorted(
                {ws for wt in emp_week_totals.values() for ws in wt.keys()
                 if ws < audit_ws},
                reverse=True
            )[:3]  # most recent 3 prior weeks
            if prior_weeks:
                L.append("  Weekly totals per employee (most-recent first):")
                header_dates = "  ".join(f"w/s {w}" for w in prior_weeks)
                L.append(f"    {'Employee':<25}  {header_dates}")
                for ename in sorted(emp_week_totals.keys()):
                    wt = emp_week_totals[ename]
                    cols = "   ".join(f"{wt.get(w, 0.0):5.1f}h" for w in prior_weeks)
                    L.append(f"    {ename:<25}  {cols}")
                L.append("")
        # Full entry detail for prior weeks
        for ename in sorted(prior_by_emp.keys()):
            date_map = prior_by_emp[ename]
            total_hrs = sum(e["hrs"] for dates in date_map.values() for e in dates)
            studio = dept_name(next(
                (e["dept"] for dates in date_map.values() for e in dates
                 if e.get("dept")), 7))
            L.append(f"\n[PRIOR]  {ename}  ({studio})  —  {total_hrs:.1f}h over prior weeks")
            for dt in sorted(date_map.keys()):
                entries = date_map[dt]
                day_total = sum(e["hrs"] for e in entries)
                L.append(f"  {dt.strftime('%a %m/%d')}  ({day_total:.1f}h):")
                for e in entries:
                    note = f'"{e["note"]}"' if e.get("note") else "[NO NOTE]"
                    phase = f"/{e['phase']}" if e.get("phase") else ""
                    act   = f"/{e['activity']}" if e.get("activity") else ""
                    L.append(f"    • {e['desc']}{phase}{act}  {e['hrs']}h  {note}")
        L.append("")

    # Per-employee detail
    L.append("══ FULL EMPLOYEE LOG ═══════════════════════════════════════")
    for ename in sorted(by_emp.keys()):
        date_map = by_emp[ename]
        total_hrs = sum(e["hrs"] for dates in date_map.values() for e in dates)
        studio = dept_name(next(
            (e["dept"] for dates in date_map.values() for e in dates if e.get("dept")), 7))
        L.append(f"\n{ename}  ({studio})  —  {total_hrs:.1f}h for period")
        for dt in sorted(date_map.keys()):
            entries = date_map[dt]
            day_total = sum(e["hrs"] for e in entries)
            L.append(f"  {dt.strftime('%a %m/%d')}  ({day_total:.1f}h):")
            for e in entries:
                note = f'"{e["note"]}"' if e.get("note") else "[NO NOTE]"
                phase = f"/{e['phase']}" if e.get("phase") else ""
                act   = f"/{e['activity']}" if e.get("activity") else ""
                L.append(f"    • {e['desc']}{phase}{act}  {e['hrs']}h  {note}")
    L.append("")

    # Per-project detail
    L.append("══ FULL PROJECT LOG ════════════════════════════════════════")
    for pname in sorted(by_proj.keys()):
        emp_map   = by_proj[pname]
        proj_total = sum(e["hrs"] for emps in emp_map.values() for e in emps)
        L.append(f"\n{pname}  —  {proj_total:.1f}h total")
        for ename in sorted(emp_map.keys()):
            for e in emp_map[ename]:
                note   = f'"{e["note"]}"' if e.get("note") else "[NO NOTE]"
                phase  = f"/{e.get('phase','')}" if e.get("phase") else ""
                act    = f"/{e.get('activity','')}" if e.get("activity") else ""
                studio = dept_name(e.get("dept", 7))
                L.append(f"  {e['date'].strftime('%a %m/%d')}  {ename} ({studio}){phase}{act}  "
                         f"{e['hrs']}h  {note}")
    L.append("")

    # ── Action log + playbook ─────────────────────────────────────────────────
    actions_ctx = serialize_actions_context()
    if actions_ctx:
        L.append(actions_ctx)

    # ── Local data cache summary ───────────────────────────────────────────────
    cache = load_ajera_cache()
    if cache:
        age = cache_age_hours()
        L.append(f"\n## LOCAL DATA CACHE (synced {age:.0f}h ago)")
        L.append(f"  Employees:   {len(cache.get('employees', []))}")
        L.append(f"  Projects:    {len(cache.get('projects', []))}")
        L.append(f"  Phases:      {len(cache.get('phases', []))}")
        L.append(f"  Activities:  {len(cache.get('activities', []))}")

    return "\n".join(L)


# ── Spinner widget ─────────────────────────────────────────────────────────────

class _Spinner(tk.Canvas):
    """Small animated arc that rotates while the app is busy."""
    _SIZE = 20
    _EXTENT = 270   # arc sweep in degrees
    _STEP   = 9     # degrees per tick
    _MS     = 35    # ms between ticks

    def __init__(self, master, color=ACCENT3, bg=SURFACE, **kw):
        super().__init__(master, width=self._SIZE, height=self._SIZE,
                         bg=bg, highlightthickness=0, bd=0, **kw)
        self._color   = color
        self._angle   = 0
        self._running = False
        self._job     = None
        # draw empty state so widget has correct size
        self._draw()

    # ── drawing ────────────────────────────────────────────────────────────────
    def _draw(self):
        self.delete("all")
        if not self._running:
            return
        pad = 2
        self.create_arc(
            pad, pad, self._SIZE - pad, self._SIZE - pad,
            start=self._angle, extent=self._EXTENT,
            outline=self._color, style="arc", width=2
        )

    def _tick(self):
        if not self._running:
            return
        self._angle = (self._angle + self._STEP) % 360
        self._draw()
        self._job = self.after(self._MS, self._tick)

    # ── public API ─────────────────────────────────────────────────────────────
    def start(self):
        if self._running:
            return
        self._running = True
        self._tick()

    def stop(self):
        self._running = False
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self._draw()   # clears canvas


# ── GUI ───────────────────────────────────────────────────────────────────────

class AuditApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("LUCA — Carlton Edwards")
        try:
            self.iconbitmap(str(resource_path("audit_icon.ico")))
        except Exception:
            pass
        self.configure(fg_color=BG)
        self.resizable(True, True)
        self.geometry("1260x900")
        self.minsize(900, 640)
        self.report_path      = None
        self._audit_context   = None   # serialized dataset for Claude
        self._chat_history    = []     # multi-turn conversation (API format)
        self._chat_display    = []     # what's visually shown — persisted to disk
        self._streaming       = False
        self._anthropic_key   = _load_api_key()
        self._last_response   = ""     # most recent full response text
        self._pending_action  = None   # structured action awaiting user decision
        self._audit_period    = ""     # "YYYY-MM-DD → YYYY-MM-DD" for action log
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        # Restore last session before auto-sync so UI populates immediately
        self._restore_session()
        # Auto-sync if cache is missing or stale
        if cache_age_hours() > CACHE_MAX_AGE:
            self.after(2000, self._sync_data)  # 2s delay so UI renders first

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):

        # ── HEADER BAR ────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=ACCENT, height=60, corner_radius=0)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        logo_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        logo_frame.pack(side="left", padx=(16, 0))

        # ── Polyhedron logo mark ───────────────────────────────────────────────
        try:
            from PIL import Image as _PILImage
            _logo_src = resource_path("luca_logo.png")
            _pil_img  = _PILImage.open(str(_logo_src)).convert("RGBA")
            # Make white background transparent
            _pixels = _pil_img.load()
            for _y in range(_pil_img.height):
                for _x in range(_pil_img.width):
                    _r, _g, _b, _a = _pixels[_x, _y]
                    if _r > 230 and _g > 230 and _b > 230:
                        _pixels[_x, _y] = (255, 255, 255, 0)
            _ctk_img = ctk.CTkImage(
                light_image=_pil_img,
                dark_image=_pil_img,
                size=(38, 38),
            )
            ctk.CTkLabel(
                logo_frame, image=_ctk_img, text="",
                fg_color="transparent"
            ).pack(side="left", padx=(0, 10))
        except Exception:
            pass  # logo PNG not yet generated — header shows text only

        ctk.CTkLabel(
            logo_frame, text="LUCA",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            fg_color="transparent"
        ).pack(side="left")

        ctk.CTkLabel(
            logo_frame, text="  Carlton Edwards Intelligence",
            text_color="#95D5B2",
            font=ctk.CTkFont(family="Segoe UI", size=15),
            fg_color="transparent"
        ).pack(side="left")

        # ── BODY: sidebar + main panel ─────────────────────────────────────────
        body_outer = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        body_outer.pack(fill="both", expand=True)
        body_outer.grid_columnconfigure(1, weight=1)
        body_outer.grid_rowconfigure(0, weight=1)

        # ── SIDEBAR ────────────────────────────────────────────────────────────
        sidebar = ctk.CTkFrame(
            body_outer, fg_color=SURFACE, width=280, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)

        # Right border on sidebar (thin ctk frame)
        ctk.CTkFrame(body_outer, fg_color=BORDER, width=1,
                     corner_radius=0).grid(row=0, column=0, sticky="nse")

        def sb_section_label(text):
            ctk.CTkLabel(
                sidebar, text=text.upper(),
                text_color=TEXT2,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                fg_color="transparent", anchor="w"
            ).pack(fill="x", padx=18, pady=(16, 4))
            ctk.CTkFrame(sidebar, fg_color=BORDER, height=1,
                         corner_radius=0).pack(fill="x", padx=18, pady=(0, 8))

        def sb_small_btn(parent, text, cmd):
            return ctk.CTkButton(
                parent, text=text, command=cmd,
                fg_color=SURFACE, hover_color=GREEN_LT,
                text_color=ACCENT, border_color=ACCENT, border_width=1,
                font=ctk.CTkFont(family="Segoe UI", size=14),
                corner_radius=6, height=30, width=96
            )

        # ── Date Range section ─────────────────────────────────────────────────
        sb_section_label("Date Range")

        pr_lbl = ctk.CTkLabel(sidebar, text="Payroll week",
                              text_color=TEXT2, fg_color="transparent",
                              font=ctk.CTkFont(family="Segoe UI", size=15),
                              anchor="w")
        pr_lbl.pack(fill="x", padx=18, pady=(0, 4))

        pr_btns = ctk.CTkFrame(sidebar, fg_color="transparent")
        pr_btns.pack(fill="x", padx=18, pady=(0, 8))
        for txt, off in [("This Week", 0), ("Last Week", -1), ("2 Wks Ago", -2)]:
            sb_small_btn(pr_btns, txt,
                         lambda o=off: self._set_payroll_week(o)
                         ).pack(side="left", padx=(0, 4))

        mr_lbl = ctk.CTkLabel(sidebar, text="Monthly",
                              text_color=TEXT2, fg_color="transparent",
                              font=ctk.CTkFont(family="Segoe UI", size=15),
                              anchor="w")
        mr_lbl.pack(fill="x", padx=18, pady=(0, 4))

        mr_btns = ctk.CTkFrame(sidebar, fg_color="transparent")
        mr_btns.pack(fill="x", padx=18, pady=(0, 10))
        for txt, off in [("This Month", 0), ("Last Month", -1)]:
            sb_small_btn(mr_btns, txt,
                         lambda o=off: self._set_month(o)
                         ).pack(side="left", padx=(0, 4))

        # Date pickers row
        date_row = ctk.CTkFrame(sidebar, fg_color="transparent")
        date_row.pack(fill="x", padx=18, pady=(0, 4))

        ctk.CTkLabel(date_row, text="From",
                     text_color=TEXT2, fg_color="transparent",
                     font=ctk.CTkFont(family="Segoe UI", size=15)
                     ).pack(side="left", padx=(0, 6))
        self.cal_start = tkcalendar.DateEntry(
            date_row, width=11, date_pattern="yyyy-mm-dd",
            background=ACCENT, foreground="white",
            selectbackground=ACCENT2, borderwidth=0,
            font=("Segoe UI", 15))
        self.cal_start.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(date_row, text="To",
                     text_color=TEXT2, fg_color="transparent",
                     font=ctk.CTkFont(family="Segoe UI", size=15)
                     ).pack(side="left", padx=(0, 6))
        self.cal_end = tkcalendar.DateEntry(
            date_row, width=11, date_pattern="yyyy-mm-dd",
            background=ACCENT, foreground="white",
            selectbackground=ACCENT2, borderwidth=0,
            font=("Segoe UI", 15))
        self.cal_end.pack(side="left")
        self._set_payroll_week(-1)

        # ── Studios section ────────────────────────────────────────────────────
        sb_section_label("Studios")

        self._studio_vars = {}
        for dept_id, name in DEPARTMENTS.items():
            if name == "Consultant":
                continue
            var = tk.BooleanVar(value=True)
            self._studio_vars[dept_id] = var
            cb_row = ctk.CTkFrame(sidebar, fg_color="transparent")
            cb_row.pack(fill="x", padx=18, pady=1)
            cb = ctk.CTkCheckBox(
                cb_row, text=name, variable=var,
                fg_color=ACCENT, hover_color=ACCENT2,
                checkmark_color="#FFFFFF", border_color=BORDER,
                text_color=TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=15))
            cb.pack(side="left")


        # ── Run Audit button ───────────────────────────────────────────────────
        sb_section_label("Actions")

        self.cache_age_lbl = ctk.CTkLabel(
            sidebar, text=cache_age_label(),
            text_color=TEXT2, fg_color="transparent",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            anchor="w"
        )
        self.cache_age_lbl.pack(fill="x", padx=18, pady=(0, 2))

        self.sync_btn = ctk.CTkButton(
            sidebar, text="Sync Data",
            command=self._sync_data,
            fg_color=SURFACE, hover_color=GREEN_LT,
            text_color=ACCENT, text_color_disabled=TEXT2,
            border_color=BORDER, border_width=1,
            font=ctk.CTkFont(family="Segoe UI", size=15),
            corner_radius=8, height=36
        )
        self.sync_btn.pack(fill="x", padx=18, pady=(0, 8))

        self.run_btn = ctk.CTkButton(
            sidebar, text="  ▶  Run Audit",
            command=self._start_audit,
            fg_color=ACCENT, hover_color=ACCENT2,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            corner_radius=8, height=44
        )
        self.run_btn.pack(fill="x", padx=18, pady=(0, 8))

        self.open_btn = ctk.CTkButton(
            sidebar, text="Open Report",
            command=self._open_report,
            fg_color=SURFACE, hover_color=GREEN_LT,
            text_color=ACCENT, text_color_disabled=TEXT2,
            border_color=BORDER, border_width=1,
            font=ctk.CTkFont(family="Segoe UI", size=15),
            corner_radius=8, height=36, state="disabled"
        )
        self.open_btn.pack(fill="x", padx=18, pady=(0, 6))

        self.print_btn = ctk.CTkButton(
            sidebar, text="Print Report",
            command=self._print_report,
            fg_color=SURFACE, hover_color=GREEN_LT,
            text_color=ACCENT2, border_color=ACCENT3, border_width=1,
            font=ctk.CTkFont(family="Segoe UI", size=15),
            corner_radius=8, height=36, state="disabled"
        )
        self.print_btn.pack(fill="x", padx=18, pady=(0, 6))

        ctk.CTkButton(
            sidebar, text="About",
            command=self._open_guide,
            fg_color=SURFACE, hover_color=BG,
            text_color=TEXT2, border_color=BORDER, border_width=1,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            corner_radius=8, height=34
        ).pack(fill="x", padx=18, pady=(0, 16))

        # ── Credentials section ────────────────────────────────────────────────
        sb_section_label("Credentials")

        ctk.CTkLabel(
            sidebar, text="Anthropic API Key",
            text_color=TEXT2, fg_color="transparent",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            anchor="w"
        ).pack(fill="x", padx=18, pady=(0, 2))

        self.anthropic_key_entry = ctk.CTkEntry(
            sidebar, show="*",
            fg_color=SURFACE2, border_color=BORDER,
            text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            height=32
        )
        self.anthropic_key_entry.pack(fill="x", padx=18, pady=(0, 8))
        if self._anthropic_key:
            self.anthropic_key_entry.insert(0, self._anthropic_key)

        ctk.CTkLabel(
            sidebar, text="Gemini API Key",
            text_color=TEXT2, fg_color="transparent",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            anchor="w"
        ).pack(fill="x", padx=18, pady=(0, 2))

        self.gemini_key_entry = ctk.CTkEntry(
            sidebar, show="*",
            fg_color=SURFACE2, border_color=BORDER,
            text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            height=32
        )
        self.gemini_key_entry.pack(fill="x", padx=18, pady=(0, 8))
        _gk = self._load_gemini_key()
        if _gk:
            self.gemini_key_entry.insert(0, _gk)

        ctk.CTkButton(
            sidebar, text="Save Keys",
            command=self._save_creds,
            fg_color=SURFACE, hover_color=GREEN_LT,
            text_color=ACCENT, border_color=BORDER, border_width=1,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            corner_radius=8, height=34
        ).pack(fill="x", padx=18, pady=(0, 16))

        # ── MAIN PANEL ─────────────────────────────────────────────────────────
        main = ctk.CTkFrame(body_outer, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        # Status + progress strip at top of main panel
        status_strip = ctk.CTkFrame(main, fg_color=SURFACE, corner_radius=0, height=48)
        status_strip.grid(row=0, column=0, sticky="ew")
        status_strip.grid_propagate(False)
        status_strip.grid_columnconfigure(0, minsize=34)   # spinner column
        status_strip.grid_columnconfigure(1, weight=1)     # label column

        # Spinning activity indicator
        self._spinner = _Spinner(status_strip, color=ACCENT3, bg=SURFACE)
        self._spinner.grid(row=0, column=0, padx=(12, 0), pady=(12, 0), sticky="w")

        self.status_var = tk.StringVar(value="Ready.")
        self._status_lbl = ctk.CTkLabel(
            status_strip, textvariable=self.status_var,
            text_color=TEXT2, fg_color="transparent",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            anchor="w"
        )
        self._status_lbl.grid(row=0, column=1, sticky="ew", padx=(4, 20), pady=(14, 0))

        self.progress = ctk.CTkProgressBar(
            status_strip, mode="indeterminate",
            fg_color=BORDER, progress_color=ACCENT2,
            corner_radius=2, height=4
        )
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew",
                           padx=0, pady=(6, 0))
        self.progress.set(0)

        # Results scrollable area
        results_scroll = ctk.CTkScrollableFrame(
            main, fg_color=BG, corner_radius=0)
        results_scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        results_scroll.grid_columnconfigure(0, weight=1)

        # Summary stat cards row (populated after audit)
        self.summary_frame = ctk.CTkFrame(results_scroll, fg_color="transparent")
        self.summary_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 0))

        # ── Ask Luca chat panel ────────────────────────────────────────────────
        # Separator above chat
        ctk.CTkFrame(results_scroll, fg_color=BORDER, height=1,
                     corner_radius=0).grid(row=1, column=0, sticky="ew",
                                           padx=0, pady=(20, 0))

        self._chat_card = ctk.CTkFrame(
            results_scroll, fg_color=SURFACE, corner_radius=0)
        self._chat_card.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        self._chat_card.grid_columnconfigure(0, weight=1)

        # Chat header
        chat_hdr = ctk.CTkFrame(self._chat_card, fg_color="transparent")
        chat_hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 0))

        ctk.CTkLabel(
            chat_hdr, text="ASK LUCA",
            text_color=TEXT2, fg_color="transparent",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        ).pack(side="left")

        ctk.CTkLabel(
            chat_hdr,
            text="  Ask about this audit — or query Ajera directly for any date",
            text_color=TEXT2, fg_color="transparent",
            font=ctk.CTkFont(family="Segoe UI", size=14)
        ).pack(side="left")

        # Save session button — right-aligned in header
        ctk.CTkButton(
            chat_hdr, text="Save Session ↓",
            command=self._save_chat_session,
            fg_color="transparent", hover_color=SURFACE2,
            text_color=ACCENT3, border_color=BORDER, border_width=1,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            corner_radius=5, height=22, width=110
        ).pack(side="right")

        ctk.CTkFrame(self._chat_card, fg_color=BORDER, height=1,
                     corner_radius=0).grid(row=1, column=0, sticky="ew",
                                           padx=16, pady=(8, 0))

        # ── Collapsible quick-reference help panel ─────────────────────────────
        self._help_visible = False

        help_toggle_row = ctk.CTkFrame(self._chat_card, fg_color="transparent")
        help_toggle_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 0))

        self._help_toggle_btn = ctk.CTkButton(
            help_toggle_row,
            text="? What can I ask LUCA?",
            command=self._toggle_help,
            fg_color="transparent", hover_color=GREEN_LT,
            text_color=ACCENT3, anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            corner_radius=4, height=28
        )
        self._help_toggle_btn.pack(side="left")

        # help panel — placed in grid row 3, shown/hidden via grid_remove/grid
        _HELP_TEXT = (
            "AUDIT DATA (after running an audit)\n"
            "  • \"Who had the most missing notes this week?\"\n"
            "  • \"Which employees had incomplete days?\"\n"
            "  • \"Summarise the collaboration citations for Rob Carlton\"\n"
            "  • \"Suggest a reminder message for Emily about her missing notes\"\n"
            "\n"
            "LIVE AJERA — ORG STRUCTURE\n"
            "  • \"Show the firm's companies and departments with their keys\"\n"
            "  • \"List all employees grouped by company and studio\"\n"
            "  • \"Who works in the Carlton Architecture PA company?\"\n"
            "\n"
            "LIVE AJERA — EMPLOYEES\n"
            "  • \"Show all employees and their employee keys\"\n"
            "  • \"Who is active in the Nashville studio?\"\n"
            "\n"
            "LIVE AJERA — PROJECTS\n"
            "  • \"List all active projects with their project keys\"\n"
            "  • \"What is the project key for the Riverfront project?\"\n"
            "\n"
            "LIVE AJERA — PHASES & ACTIVITIES\n"
            "  • \"Show the phases and phase keys for the Greenway project\"\n"
            "  • \"List all phases for projects matching 'CE-2025'\"\n"
            "  • \"What activity codes are available in Ajera?\"\n"
            "\n"
            "LIVE AJERA — TIMESHEETS\n"
            "  • \"Pull Emily Benson's timesheets for January 2025\"\n"
            "  • \"How many hours did the team log to overhead in February?\"\n"
            "  • \"Show all entries for project CE-2024-003 last quarter\"\n"
            "  • \"How many hours did Carlton Edwards PLLC bill last month?\"\n"
        )
        self._help_frame = ctk.CTkFrame(
            self._chat_card, fg_color=GREEN_LT, corner_radius=6)
        self._help_frame.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 0))
        self._help_frame.grid_remove()  # hidden by default

        ctk.CTkLabel(
            self._help_frame, text=_HELP_TEXT,
            text_color=TEXT2, fg_color="transparent",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            justify="left", anchor="nw", wraplength=800
        ).pack(fill="x", padx=14, pady=10, anchor="nw")

        # Chat history box (tk.Text kept for tag_configure support)
        chat_body_frame = ctk.CTkFrame(
            self._chat_card, fg_color="transparent")
        chat_body_frame.grid(row=4, column=0, sticky="ew", padx=16, pady=(8, 0))
        chat_body_frame.grid_columnconfigure(0, weight=1)

        self.chat_box = tk.Text(
            chat_body_frame, height=40, wrap="word",
            bg=SURFACE, fg=TEXT,
            font=("Segoe UI", 16),
            relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            state="disabled", cursor="arrow",
            padx=10, pady=8)
        self.chat_box.grid(row=0, column=0, sticky="ew")

        chat_scroll_bar = tk.Scrollbar(
            chat_body_frame, command=self.chat_box.yview,
            troughcolor=BG, bg=BORDER)
        chat_scroll_bar.grid(row=0, column=1, sticky="ns")
        self.chat_box.config(yscrollcommand=chat_scroll_bar.set)

        # Text tags for visual distinction
        self.chat_box.tag_config("name_user",      foreground=ACCENT,  font=("Segoe UI", 15, "bold"))
        self.chat_box.tag_config("name_assistant",  foreground=ACCENT3, font=("Segoe UI", 15, "bold"))
        self.chat_box.tag_config("user",            foreground=TEXT,    font=("Segoe UI", 16))
        self.chat_box.tag_config("assistant",       foreground=TEXT,    font=("Segoe UI", 16))
        self.chat_box.tag_config("thinking",        foreground=TEXT2,   font=("Segoe UI", 16, "italic"))
        self.chat_box.tag_config("error",           foreground=RED,     font=("Segoe UI", 16))
        self.chat_box.tag_config("tool_status",     foreground=ACCENT3, font=("Segoe UI", 14, "italic"))

        # Input row
        input_row = ctk.CTkFrame(self._chat_card, fg_color="transparent")
        input_row.grid(row=5, column=0, sticky="ew", padx=16, pady=(8, 0))
        input_row.grid_columnconfigure(0, weight=1)

        self.chat_input = ctk.CTkEntry(
            input_row,
            fg_color=SURFACE, border_color=BORDER, text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=16),
            corner_radius=6, height=40
        )
        self.chat_input.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.chat_input.bind("<Return>", lambda e: self._ask_question())

        self.ask_btn = ctk.CTkButton(
            input_row, text="Ask →",
            command=self._ask_question,
            fg_color=ACCENT, hover_color=ACCENT2,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            corner_radius=6, height=40, width=90
        )
        self.ask_btn.grid(row=0, column=1)

        # "Request Action" removed — LUCA acts autonomously when it
        # detects an action in its response (no approval step required).

        # Action card removed — LUCA executes actions autonomously.
        # A stub frame is kept so _dismiss_action_card() doesn't error.
        self._action_frame = ctk.CTkFrame(
            self._chat_card, fg_color="transparent", height=0)
        self._action_frame.grid_remove()

        # Bottom spacer
        ctk.CTkFrame(self._chat_card, fg_color="transparent",
                     height=12).grid(row=7, column=0, sticky="ew")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_payroll_week(self, offset):
        s, e = payroll_week_bounds(offset)
        self.cal_start.set_date(s)
        self.cal_end.set_date(e)

    def _set_month(self, offset):
        s, e = month_bounds(offset)
        self.cal_start.set_date(s)
        self.cal_end.set_date(e)

    def _my_studio_only(self):
        for dept_id, var in self._studio_vars.items():
            var.set(dept_id == 2)  # 2 = Asheville (Rob's studio)

    def _open_report(self):
        if self.report_path and os.path.exists(self.report_path):
            os.startfile(self.report_path)

    def _open_guide(self):
        md_path = resource_path("APPGUIDE.md")
        html_path = REPORT_DIR / "APPGUIDE.html"
        md = md_path.read_text(encoding="utf-8")

        # Simple markdown → HTML renderer
        lines = md.split("\n")
        body_lines = []
        in_table = False
        in_code = False
        for line in lines:
            if line.startswith("```"):
                if in_code:
                    body_lines.append("</code></pre>"); in_code = False
                else:
                    body_lines.append("<pre><code>"); in_code = True
                continue
            if in_code:
                body_lines.append(line); continue
            if line.startswith("# "):
                body_lines.append(f"<h1>{line[2:]}</h1>"); continue
            if line.startswith("## "):
                body_lines.append(f"<h2>{line[3:]}</h2>"); continue
            if line.startswith("### "):
                body_lines.append(f"<h3>{line[4:]}</h3>"); continue
            if line.startswith("---"):
                body_lines.append("<hr>"); continue
            if line.startswith("|"):
                if not in_table:
                    body_lines.append("<table>"); in_table = True
                if "---|" in line or "|---" in line:
                    continue
                cells = [c.strip() for c in line.strip("|").split("|")]
                tag = "th" if not any(b for b in body_lines if "<td>" in b) and in_table else "td"
                body_lines.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
                continue
            if in_table:
                body_lines.append("</table>"); in_table = False
            if line.startswith("- "):
                body_lines.append(f"<li>{line[2:]}</li>"); continue
            if line.strip() == "":
                body_lines.append("<br>"); continue
            # inline bold
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            line = re.sub(r'`(.+?)`', r'<code>\1</code>', line)
            body_lines.append(f"<p>{line}</p>")
        if in_table:
            body_lines.append("</table>")

        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>LUCA — About</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'EB Garamond', Garamond, Georgia, serif;
       font-size:14px;background:#F7F8FA;color:#111827;
       padding:0 0 60px;-webkit-font-smoothing:antialiased;letter-spacing:-0.01em}}
  .page-wrap{{max-width:860px;margin:0 auto;padding:32px 24px}}
  /* Top banner */
  .about-banner{{background:#1B4332;color:#fff;border-radius:16px;
                 padding:28px 32px;margin-bottom:32px;}}
  .about-banner h1{{font-size:26px;font-weight:800;margin-bottom:6px}}
  .about-banner p{{opacity:.75;font-size:13px}}
  /* Content card */
  .content-card{{background:#fff;border:1px solid #E5E7EB;
                 border-radius:16px;padding:28px 32px}}
  h1{{color:#1B4332;font-size:22px;border-bottom:2px solid #E5E7EB;
     padding-bottom:10px;margin-bottom:16px;margin-top:0}}
  h2{{color:#1B4332;font-size:17px;margin-top:28px;margin-bottom:10px;
     border-left:4px solid #40916C;padding-left:12px}}
  h3{{color:#2D6A4F;font-size:14px;margin-top:16px;margin-bottom:6px}}
  hr{{border:none;border-top:1px solid #E5E7EB;margin:24px 0}}
  table{{border-collapse:collapse;width:100%;margin:12px 0;
         border-radius:8px;overflow:hidden}}
  th{{background:#1B4332;color:#fff;padding:9px 14px;text-align:left;
     font-size:12px;text-transform:uppercase;letter-spacing:.5px}}
  td{{padding:8px 14px;border-bottom:1px solid #F3F4F6;color:#374151}}
  tr:last-child td{{border-bottom:none}}
  tr:hover td{{background:#F9FAFB}}
  code{{background:#EEF4F0;padding:2px 7px;border-radius:4px;
        font-family:"Cascadia Code","Consolas",monospace;
        color:#1B4332;font-size:12px}}
  pre{{background:#F7F8FA;border:1px solid #E5E7EB;padding:16px;
       border-radius:10px;overflow:auto;margin:10px 0}}
  pre code{{background:none;padding:0;color:#1B4332}}
  li{{margin:5px 0;color:#374151;line-height:1.6}}
  strong{{color:#111827}}
  p{{line-height:1.7;margin:6px 0;color:#374151}}
  br{{display:block;margin:4px 0}}
</style></head>
<body>
<div class="page-wrap">
  <div class="about-banner">
    <h1>◉ LUCA</h1>
    <p>Carlton Edwards Intelligence</p>
  </div>
  <div class="content-card">
{''.join(body_lines)}
  </div>
</div>
</body></html>"""

        html_path.write_text(html, encoding="utf-8")
        os.startfile(str(html_path))

    def _set_status(self, msg, color=None):
        self.status_var.set(msg)
        self.update_idletasks()

    def _show_summary(self, flags):
        for w in self.summary_frame.winfo_children():
            w.destroy()
        blocked = sum(1 for f in flags['missing_notes'] if not f.get("is_pto"))
        items = [
            (str(blocked),                      "No Notes",  RED,    "#FEE2E2"),
            (str(len(flags['incomplete_days'])), "Short Days", YELLOW, "#FEF3C7"),
            (str(len(flags['full_overhead'])),   "Overhead",  ACCENT, GREEN_LT),
            (str(len(flags['collab'])),          "Collab",    ACCENT3, GREEN_LT),
        ]
        for num, label, fg_col, bg_col in items:
            card = ctk.CTkFrame(self.summary_frame, fg_color=bg_col,
                                border_color=BORDER, border_width=1,
                                corner_radius=10)
            card.pack(side="left", padx=(0, 12), ipadx=16, ipady=8)
            ctk.CTkLabel(card, text=num,
                         text_color=fg_col, fg_color="transparent",
                         font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold")
                         ).pack(padx=14, pady=(10, 2))
            ctk.CTkLabel(card, text=label.upper(),
                         text_color=TEXT2, fg_color="transparent",
                         font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
                         ).pack(padx=14, pady=(0, 10))

    # ── Audit runner ──────────────────────────────────────────────────────────

    def _start_audit(self):
        self.run_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.print_btn.configure(state="disabled")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self._spinner.start()
        self._set_status("Connecting to Ajera...")
        threading.Thread(target=self._audit_thread, daemon=True).start()

    def _audit_thread(self):
        try:
            start = self.cal_start.get_date()
            end   = self.cal_end.get_date()
            selected_depts = {did for did, var in self._studio_vars.items()
                              if var.get()}

            # ── Employee roster — cache first ─────────────────────────────────
            cache     = load_ajera_cache()
            cache_age = cache_age_hours()
            use_cache = bool(cache) and cache_age < CACHE_MAX_AGE

            if use_cache and cache.get("employees"):
                self._set_status(
                    f"Loading employee data from cache "
                    f"(synced {cache_age:.0f}h ago)…"
                )
                emps = cache["employees"]
            else:
                self._set_status("Loading employee data from Ajera…")
                t1   = login(1)
                emps = get_employees(t1)
                logout(t1)

            emp_dept = {e["EmployeeKey"]: e.get("Department", 7) for e in emps}

            # Load (and create if missing) the firm reference file; also update
            # per-employee weekly hour targets so the audit logic picks them up.
            ref = _load_luca_reference()
            EMP_WEEKLY_HOURS.update(ref.get("employee_weekly_hours", {}))

            days = (end - start).days + 1
            self._set_status(f"Pulling {days}-day range from Ajera (timesheets always live)…")
            # Pass employees from cache so run_audit skips its own v1 API call
            flags, by_emp, by_proj, prior_by_emp, emp_week_totals, all_emps = \
                run_audit(start, end, emp_dept, employees=emps)

            # Refresh 10-week timesheet cache in background — doesn't block the audit
            self._refresh_timesheet_cache_bg()

            # Filter by selected studios
            def dept_filter(dept_id): return dept_id in selected_depts

            for key in flags:
                flags[key] = [f for f in flags[key]
                              if dept_filter(f.get("dept", 7))]
            by_emp_f = {e: d for e, d in by_emp.items()
                        if any(ent.get("dept") in selected_depts
                               for dates in d.values() for ent in dates)}
            by_proj_f = {}
            for p, em in by_proj.items():
                filtered = {emp: [e for e in ents
                                  if e.get("dept") in selected_depts]
                            for emp, ents in em.items()}
                filtered = {k: v for k, v in filtered.items() if v}
                if filtered:
                    by_proj_f[p] = filtered

            self._set_status("Building report...")
            html = build_html(flags, by_emp_f, by_proj_f, start, end)
            path = REPORT_DIR / f"audit_{start}.html"
            path.write_text(html, encoding="utf-8")
            self.report_path = str(path)

            mn_blocked = sum(1 for f in flags["missing_notes"] if not f.get("is_pto"))
            total = mn_blocked + sum(len(flags[k]) for k in
                                     ("incomplete_days","full_overhead","collab"))
            ctx = serialize_audit_context(
                flags, by_emp_f, by_proj_f, start, end,
                employees=all_emps,
                prior_by_emp=prior_by_emp,
                emp_week_totals=emp_week_totals,
                reference=ref,
            )
            period_str = f"{start} → {end}"
            self.after(0, lambda f=flags, t=total, c=ctx, p=period_str:
                       self._audit_done(f, t, c, p))

        except Exception as e:
            msg = str(e)
            self.after(0, lambda m=msg: self._audit_error(m))

    def _audit_done(self, flags, total, context, period_str=""):
        self.progress.stop()
        self.progress.set(0)
        self._spinner.stop()
        self.run_btn.configure(state="normal")
        self.open_btn.configure(state="normal",
                                fg_color=ACCENT, hover_color=ACCENT2)
        self.print_btn.configure(state="normal")
        self._set_status(
            f"Done — {total} issue(s) found.  Report: {self.report_path}")
        self._show_summary(flags)

        # Store dataset and reset chat for this audit run
        self._audit_context  = context
        self._audit_period   = period_str
        self._chat_history   = []
        self._chat_display   = []
        self._last_response  = ""
        self._pending_action = None
        self._dismiss_action_card()
        self._save_session()   # persist new audit context immediately
        # Refresh chat hint now that audit data is loaded
        self.chat_box.config(state="normal")
        self.chat_box.delete("1.0", "end")
        self.chat_box.insert("end",
            "Audit complete. Ask any question about this dataset — "
            "or ask LUCA to pull live data from Ajera for any other period.",
            "thinking")
        self.chat_box.config(state="disabled")
        # Mousewheel on chat_box stays local (CTkScrollableFrame handles outer scroll)

    # ── Chat helpers ──────────────────────────────────────────────────────────

    def _chat_append(self, sender, text, name_tag, body_tag):
        """Insert a new message block into the chat history widget."""
        self.chat_box.config(state="normal")
        if self.chat_box.index("end-1c") not in ("1.0", ""):
            self.chat_box.insert("end", "\n\n")
        self.chat_box.insert("end", sender + "\n", name_tag)
        self.chat_box.insert("end", text, body_tag)
        self.chat_box.config(state="disabled")
        self.chat_box.see("end")

    def _chat_stream_start(self, sender, name_tag):
        """Open a streaming message block; returns the mark name for appending."""
        self.chat_box.config(state="normal")
        if self.chat_box.index("end-1c") not in ("1.0", ""):
            self.chat_box.insert("end", "\n\n")
        self.chat_box.insert("end", sender + "\n", name_tag)
        self.chat_box.mark_set("stream_end", "end")
        self.chat_box.mark_gravity("stream_end", "left")
        self.chat_box.config(state="disabled")
        self.chat_box.see("end")

    def _chat_stream_chunk(self, chunk):
        self.chat_box.config(state="normal")
        self.chat_box.insert("end", chunk, "assistant")
        self.chat_box.config(state="disabled")
        self.chat_box.see("end")

    def _ask_question(self):
        question = self.chat_input.get().strip()
        # Allow chat even without a pre-loaded audit: Luca can query Ajera directly.
        if not question or self._streaming:
            return

        # Ensure API key
        if not self._anthropic_key:
            self._prompt_api_key()
            if not self._anthropic_key:
                return

        self.chat_input.delete(0, "end")
        self.ask_btn.configure(state="disabled")
        self._streaming = True
        self._spinner.start()

        # Clear hint text on first question only — preserve conversation after that
        if not self._chat_history:
            self.chat_box.config(state="normal")
            self.chat_box.delete("1.0", "end")
            self.chat_box.config(state="disabled")

        self._chat_append("You", question, "name_user", "user")
        self._chat_display.append({
            "sender": "You", "text": question,
            "name_tag": "name_user", "body_tag": "user",
        })
        self._chat_stream_start("LUCA", "name_assistant")

        threading.Thread(target=self._stream_answer,
                         args=(question,), daemon=True).start()

    def _resolved_system(self) -> str:
        """Return LUCA_SYSTEM with date/time header and knowledge block injected.
        Uses str.replace() — NOT .format() — because the YAML content contains
        curly braces that would be misread as Python format placeholders."""
        now = datetime.now()
        date_header = (
            f"TODAY: {now.strftime('%A, %B %d, %Y')}  |  "
            f"TIME: {now.strftime('%I:%M %p')}  |  "
            f"WEEK DAY: {now.strftime('%A')}\n\n"
        )
        kb = _load_luca_knowledge()
        block = (f"--- BEGIN luca_knowledge.yaml ---\n{kb}\n--- END luca_knowledge.yaml ---"
                 if kb else "(luca_knowledge.yaml not found — business rules not loaded)")
        return date_header + LUCA_SYSTEM.replace("{knowledge_block}", block)

    def _stream_answer(self, question):
        """Agentic answer loop — streams Luca's reply and handles live Ajera tool calls.

        Flow:
          1. Build the message list (injecting the audit context on the first turn).
          2. Open a streaming call to Claude WITH the Ajera tools available.
          3. Stream any text that arrives before a tool decision.
          4. If Claude decides to call a tool (stop_reason == "tool_use"):
               a. Show a status line in the chat ("Querying Ajera…").
               b. Execute the Ajera API call in this background thread.
               c. Feed the result back and loop — up to MAX_TOOL_ROUNDS times.
          5. On end_turn, save the conversation and notify the UI.
        """
        MAX_TOOL_ROUNDS = 5
        try:
            import anthropic as _ant
            client = _ant.Anthropic(api_key=self._anthropic_key)

            # ── Build initial user message ────────────────────────────────────
            if not self._chat_history and self._audit_context:
                user_msg = {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Here is the complete timesheet audit dataset. "
                                "Use it to answer all my questions.\n\n"
                                f"{self._audit_context}"
                            ),
                            "cache_control": {"type": "ephemeral"},
                        },
                        {"type": "text", "text": question},
                    ],
                }
            else:
                user_msg = {"role": "user", "content": question}

            # loop_messages is the working message list for this request;
            # self._chat_history persists only the final user/assistant pair.
            loop_messages  = list(self._chat_history) + [user_msg]
            full_text_parts = []  # accumulate ALL text emitted across tool rounds

            # ── Agentic tool loop ─────────────────────────────────────────────
            for _round in range(MAX_TOOL_ROUNDS):
                with client.messages.stream(
                    model="claude-opus-4-6",
                    max_tokens=8192,
                    thinking={"type": "adaptive"},
                    tools=LUCA_TOOLS,
                    system=self._resolved_system(),
                    messages=loop_messages,
                ) as stream:
                    # Stream text chunks as they arrive
                    for text in stream.text_stream:
                        full_text_parts.append(text)
                        self.after(0, lambda c=text: self._chat_stream_chunk(c))

                    final_msg = stream.get_final_message()

                if final_msg.stop_reason == "tool_use":
                    # Append the full assistant response (incl. thinking + tool_use blocks)
                    loop_messages.append(
                        {"role": "assistant", "content": final_msg.content})

                    # Execute every tool Claude requested
                    tool_results = []
                    for block in final_msg.content:
                        if block.type != "tool_use":
                            continue
                        label = (block.name
                                 .replace("query_ajera_", "")
                                 .replace("_", " ")
                                 .title())
                        self.after(0, lambda lbl=label: self._tool_status(lbl))
                        try:
                            result = _execute_ajera_tool(block.name, block.input)
                        except Exception as te:
                            result = f"ERROR executing {block.name}: {te}"
                        tool_results.append({
                            "type":        "tool_result",
                            "tool_use_id": block.id,
                            "content":     result,
                        })

                    loop_messages.append({"role": "user", "content": tool_results})

                    # Visual separator before Luca's continuation
                    self.after(0, lambda: self._chat_stream_chunk("\n\n"))
                    continue  # go back for another streaming round

                else:
                    break  # stop_reason == "end_turn" — we are done

            # ── Persist history ───────────────────────────────────────────────
            response_text = "".join(full_text_parts)

            if not self._chat_history and self._audit_context:
                # First turn: store user msg with embedded context
                self._chat_history.append(user_msg)
            else:
                self._chat_history.append(user_msg)
            # Store only the final text (not tool intermediates) for follow-ups
            self._chat_history.append(
                {"role": "assistant", "content": response_text})

            self.after(0, lambda r=response_text: self._stream_done(r))

        except Exception as e:
            raw = str(e)
            # 529 = Anthropic servers temporarily overloaded — retry up to 3x
            if "529" in raw or "overloaded_error" in raw:
                import time as _time
                for _attempt in range(3):
                    _wait = 8 * (2 ** _attempt)  # 8s, 16s, 32s
                    self.after(0, lambda w=_wait, a=_attempt+1:
                        self._tool_status(f"Claude busy — retrying in {w}s (attempt {a}/3)"))
                    _time.sleep(_wait)
                    try:
                        # Re-run the full request — re-enter from loop_messages state
                        with client.messages.stream(
                            model="claude-opus-4-6",
                            max_tokens=8192,
                            thinking={"type": "adaptive"},
                            tools=LUCA_TOOLS,
                            system=self._resolved_system(),
                            messages=loop_messages,
                        ) as stream:
                            for text in stream.text_stream:
                                full_text_parts.append(text)
                                self.after(0, lambda c=text: self._chat_stream_chunk(c))
                            final_msg = stream.get_final_message()
                        response_text = "".join(full_text_parts)
                        self._chat_history.append(user_msg)
                        self._chat_history.append(
                            {"role": "assistant", "content": response_text})
                        self.after(0, lambda r=response_text: self._stream_done(r))
                        return
                    except Exception:
                        continue
                # Claude retries exhausted — fall back to Gemini
                gemini_key = self._load_gemini_key() if hasattr(self, '_load_gemini_key') else ""
                if gemini_key and _GEMINI_AVAILABLE:
                    self.after(0, lambda: self._tool_status("Falling back to Gemini"))
                    # Run Gemini in same thread (already in background thread)
                    self._gemini_stream_answer(question)
                    return
                else:
                    msg = ("Claude's servers are briefly overloaded and no Gemini key is configured. "
                           "Try again in a moment, or add a Gemini API key in the sidebar.")
            else:
                msg = raw
            self.after(0, lambda m=msg: self._stream_error(m))

    def _stream_done(self, response_text=""):
        self._streaming      = False
        self._last_response  = response_text
        self._spinner.stop()
        self.ask_btn.configure(state="normal")
        self.chat_input.focus()
        # Record LUCA's full response in the display log and persist to disk
        if response_text:
            self._chat_display.append({
                "sender": "LUCA", "text": response_text,
                "name_tag": "name_assistant", "body_tag": "assistant",
            })
        self._save_session()
        # Auto-execute any structured action — no approval step
        action = self._parse_action_proposal(response_text)
        if action:
            self._auto_execute_action(action)

    def _auto_execute_action(self, action):
        """Execute a structured action immediately — no approval required.

        Logs to luca_actions.json, records in the playbook, and appends a
        confirmation line to the chat so the session record shows what happened.
        """
        record = {
            "id":           f"act_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp":    datetime.now().isoformat(timespec="seconds"),
            "audit_period": self._audit_period,
            "type":         action.get("type", "NOTE"),
            "employee":     action.get("employee", ""),
            "issue_type":   action.get("issue_type", ""),
            "issue_detail": action.get("issue_detail", ""),
            "subject":      action.get("subject", ""),
            "message":      action.get("message", ""),
            "status":       "executed",
            "outcome":      None,
            "outcome_date": None,
        }
        try:
            save_action(record)
            record_in_playbook(
                record["issue_type"],
                record["employee"],
                record["type"],
            )
            confirm = (
                f"Action executed  \u2014  "
                f"{record['type']}  /  {record['employee']}"
                + (f"  /  {record['subject']}" if record['subject'] else "")
            )
        except Exception as exc:
            confirm = f"Action could not be saved: {exc}"

        self._chat_append("LUCA", confirm, "name_assistant", "thinking")

    def _stream_error(self, msg):
        self._streaming = False
        self._spinner.stop()
        # Clean up raw API error JSON into a readable message
        clean = msg
        try:
            # Anthropic errors often stringify as JSON — extract the message field
            import json as _json
            obj = _json.loads(msg) if msg.strip().startswith("{") else None
            if obj:
                err = obj.get("error", obj)
                clean = err.get("message", msg) if isinstance(err, dict) else msg
        except Exception:
            pass
        # Truncate very long raw strings
        if len(clean) > 300:
            clean = clean[:300] + "…"
        self._chat_append("Error", clean, "name_assistant", "error")
        self.ask_btn.configure(state="normal")

    def _gemini_stream_answer(self, question):
        """Gemini fallback for Ask Luca. Runs in background thread."""
        try:
            gemini_key = self._load_gemini_key()
            if not gemini_key or not _GEMINI_AVAILABLE:
                self.after(0, lambda: self._stream_error(
                    "Gemini API key not set. Add it in the sidebar credentials section."))
                return

            g_client = _genai.Client(api_key=gemini_key)

            # Convert chat history from Claude format to Gemini format
            # Claude: {"role": "user"/"assistant", "content": str}
            # Gemini: Content(role="user"/"model", parts=[Part(text=...)])
            gemini_history = []
            for msg in self._chat_history:
                role = "model" if msg["role"] == "assistant" else "user"
                content_val = msg["content"]
                if isinstance(content_val, str):
                    text = content_val
                elif isinstance(content_val, list):
                    # Extract text parts only (skip tool_use/tool_result blocks)
                    text = " ".join(
                        b.get("text", "") for b in content_val
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                else:
                    continue
                if text.strip():
                    gemini_history.append(
                        _genai_types.Content(
                            role=role,
                            parts=[_genai_types.Part(text=text)]
                        )
                    )

            # Build the user message — include audit context on first turn
            if not self._chat_history and self._audit_context:
                user_text = (f"Here is the complete audit dataset for this session:\n\n"
                            f"{self._audit_context}\n\n---\n\n{question}")
            else:
                user_text = question

            gemini_history.append(
                _genai_types.Content(
                    role="user",
                    parts=[_genai_types.Part(text=user_text)]
                )
            )

            # Tools config
            gemini_tool_decls = _luca_tools_to_gemini()
            tools_config = None
            if gemini_tool_decls:
                tools_config = [_genai_types.Tool(function_declarations=gemini_tool_decls)]

            config = _genai_types.GenerateContentConfig(
                system_instruction=self._resolved_system(),
                tools=tools_config,
                temperature=1.0,
            )

            # Emit provider marker before streaming
            self.after(0, lambda: self._chat_stream_chunk("[via Gemini 2.0 Flash]\n\n"))

            # Agentic tool loop (up to MAX_TOOL_ROUNDS)
            MAX_TOOL_ROUNDS = 6
            contents = gemini_history
            full_text_parts = []

            for _round in range(MAX_TOOL_ROUNDS):
                # Use non-streaming for tool rounds, streaming for final text
                response = g_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=contents,
                    config=config,
                )

                candidate = response.candidates[0]
                parts = candidate.content.parts if candidate.content else []

                # Check for function calls
                func_calls = [p for p in parts if hasattr(p, "function_call") and p.function_call]
                text_parts = [p.text for p in parts if hasattr(p, "text") and p.text]

                # Stream any text that came with this round
                for txt in text_parts:
                    full_text_parts.append(txt)
                    self.after(0, lambda c=txt: self._chat_stream_chunk(c))

                if not func_calls:
                    break  # No tool calls — done

                # Execute tool calls
                tool_results = []
                for fc_part in func_calls:
                    fc = fc_part.function_call
                    label = fc.name.replace("query_ajera_", "").replace("_", " ").title()
                    self.after(0, lambda lbl=label: self._tool_status(lbl))
                    try:
                        result = _execute_ajera_tool(fc.name, dict(fc.args))
                    except Exception as te:
                        result = f"ERROR executing {fc.name}: {te}"
                    tool_results.append(
                        _genai_types.Part.from_function_response(
                            name=fc.name,
                            response={"result": result},
                        )
                    )

                # Append assistant response + tool results to contents
                contents = list(contents) + [
                    candidate.content,
                    _genai_types.Content(role="user", parts=tool_results),
                ]
                self.after(0, lambda: self._chat_stream_chunk("\n\n"))

            response_text = "".join(full_text_parts)
            if not response_text:
                response_text = "(No response from Gemini)"

            # Persist history
            user_msg = {"role": "user", "content": user_text}
            self._chat_history.append(user_msg)
            self._chat_history.append({"role": "assistant", "content": response_text})

            self.after(0, lambda r=response_text: self._stream_done(r))

        except Exception as e:
            self.after(0, lambda m=str(e): self._stream_error(m))

    # ── Session export ─────────────────────────────────────────────────────────

    def _save_chat_session(self):
        """Export the current Ask Luca session as a formatted HTML file and
        open it in the browser (where it can be printed to PDF, saved as a
        Google Doc via copy-paste, etc.)."""
        import html as _html
        if not self._chat_history:
            tk.messagebox.showinfo(
                "Nothing to Save", "No chat messages in this session yet.")
            return

        ts   = datetime.now().strftime("%Y%m%d_%H%M")
        date = datetime.now().strftime("%B %d, %Y at %H:%M")
        out  = REPORT_DIR / f"Luca_Chat_{ts}.html"

        rows = []
        for msg in self._chat_history:
            role    = msg.get("role", "user")
            content = msg.get("content", "")
            # content may be a list of blocks (tool-use messages)
            if isinstance(content, list):
                content = "\n".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            sender = "You" if role == "user" else "LUCA"
            body   = _html.escape(str(content))
            rows.append(
                f'<div class="msg {role}">'
                f'<div class="sender">{sender}</div>'
                f'<div class="body">{body}</div></div>'
            )

        html_doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>LUCA Chat — {date}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap');
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'EB Garamond', Garamond, Georgia, serif;background:#F8F6F2;color:#1A1A1A;-webkit-font-smoothing:antialiased;letter-spacing:-0.01em}}
  .page-header{{background:#1A1A1A;color:#fff;padding:28px 48px;display:flex;
    align-items:baseline;gap:20px;}}
  .page-header h1{{font-size:22px;letter-spacing:.5px;}}
  .page-header .meta{{font-size:12px;color:#8A7A6E;}}
  .content{{max-width:820px;margin:40px auto;padding:0 40px 80px;}}
  .msg{{margin-bottom:28px;}}
  .sender{{font-size:10px;font-weight:bold;letter-spacing:1.2px;
    text-transform:uppercase;margin-bottom:6px;}}
  .msg.user .sender{{color:#967B65;}}
  .msg.assistant .sender{{color:#1A1A1A;}}
  .body{{background:#fff;border-radius:8px;padding:16px 20px;
    border:1px solid #D4C8BC;line-height:1.7;font-size:14px;
    white-space:pre-wrap;word-break:break-word;}}
  .msg.user .body{{background:#F0EDE8;}}
  @media print{{
    .page-header{{-webkit-print-color-adjust:exact;print-color-adjust:exact;}}
  }}
</style></head><body>
<div class="page-header">
  <h1>LUCA — Chat Session</h1>
  <span class="meta">Carlton Edwards · {date}</span>
</div>
<div class="content">
{''.join(rows)}
</div>
</body></html>"""

        out.write_text(html_doc, encoding="utf-8")
        webbrowser.open(out.as_uri())

        # Also offer plain-text copy to clipboard
        plain = "\n\n".join(
            f"{'YOU' if m['role']=='user' else 'LUCA'}:\n"
            + (m["content"] if isinstance(m["content"], str)
               else "\n".join(b.get("text","") for b in m["content"]
                              if isinstance(b,dict) and b.get("type")=="text"))
            for m in self._chat_history
        )
        self.clipboard_clear()
        self.clipboard_append(plain)
        tk.messagebox.showinfo(
            "Session Saved",
            f"Chat saved to:\n{out.name}\n\n"
            "Opened in browser — print there to get a PDF, or paste into a "
            "Google Doc (plain text also copied to your clipboard)."
        )

    def _toggle_help(self):
        """Show/hide the quick-reference help panel inside Ask Luca."""
        if self._help_visible:
            self._help_frame.grid_remove()
            self._help_toggle_btn.configure(text="? What can I ask LUCA?")
            self._help_visible = False
        else:
            self._help_frame.grid()
            self._help_toggle_btn.configure(text="▲ Close help")
            self._help_visible = True

    def _tool_status(self, label):
        """Insert an italicised status line while an Ajera tool is executing."""
        self.chat_box.config(state="normal")
        if self.chat_box.index("end-1c") not in ("1.0", ""):
            self.chat_box.insert("end", "\n")
        self.chat_box.insert("end", f"  [ Querying Ajera: {label}... ]\n", "tool_status")
        self.chat_box.config(state="disabled")
        self.chat_box.see("end")

    # ── Print ──────────────────────────────────────────────────────────────────

    def _print_report(self):
        """Open the current report in the browser's print dialog."""
        if not self.report_path:
            return
        try:
            # Windows: print verb opens browser → print dialog
            os.startfile(self.report_path, "print")
        except Exception:
            # Fallback: just open it (user can Ctrl+P from the browser,
            # or click the Print Report button embedded in the HTML)
            webbrowser.open(
                "file:///" + self.report_path.replace("\\", "/"))

    # ── Action system ──────────────────────────────────────────────────────────

    def _request_action(self):
        """Send Luca a prompt asking it to propose a structured action
        for the most pressing issue in the current audit."""
        if not self._audit_context or self._streaming:
            return
        if not self._anthropic_key:
            self._prompt_api_key()
            if not self._anthropic_key:
                return
        prompt = (
            "Based on the current audit data, identify the single most pressing "
            "issue that needs immediate attention and propose a specific action "
            "I can take right now. Include a ready-to-send message in your "
            "[ACTION] block. Reference the playbook if you have seen this pattern before."
        )
        # Feed it through the normal ask flow
        self.chat_input.delete(0, "end")
        self.chat_input.insert(0, prompt)
        self._ask_question()

    @staticmethod
    def _parse_action_proposal(text):
        """Extract and parse a [ACTION]...[/ACTION] JSON block from text."""
        m = re.search(r'\[ACTION\](.*?)\[/ACTION\]', text, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            return None

    def _show_action_card(self, action):
        """Populate and reveal the action proposal card below the chat."""
        atype   = action.get("type", "ACTION")
        employee= action.get("employee", "")
        subject = action.get("subject", "")
        message = action.get("message", "")

        self._action_type_lbl.configure(text=f"  {atype}  ")
        self._action_emp_lbl.configure(text=employee)
        self._action_subj_lbl.configure(
            text=f"  |  {subject}" if subject else "")

        self._action_msg.config(state="normal")
        self._action_msg.delete("1.0", "end")
        self._action_msg.insert("end", message)
        self._action_msg.config(state="disabled")

        self._action_frame.grid()

    def _dismiss_action_card(self):
        """Hide the action card without logging."""
        try:
            self._action_frame.grid_remove()
        except Exception:
            pass

    def _copy_action_message(self):
        """Copy the proposed message to the clipboard (does NOT log yet)."""
        if not self._pending_action:
            return
        msg = self._pending_action.get("message", "")
        self.clipboard_clear()
        self.clipboard_append(msg)
        # Brief visual feedback
        self._action_type_lbl.configure(text="  Copied!  ")
        self.after(1400, lambda: self._action_type_lbl.configure(
            text=f"  {self._pending_action.get('type','ACTION')}  "))

    def _log_and_dismiss_action(self):
        """Save the pending action to luca_actions.json + update the playbook,
        then hide the card."""
        if not self._pending_action:
            self._dismiss_action_card()
            return
        action = self._pending_action
        record = {
            "id":           f"act_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp":    datetime.now().isoformat(timespec="seconds"),
            "audit_period": self._audit_period,
            "type":         action.get("type", "NOTE"),
            "employee":     action.get("employee", ""),
            "issue_type":   action.get("issue_type", ""),
            "issue_detail": action.get("issue_detail", ""),
            "subject":      action.get("subject", ""),
            "message":      action.get("message", ""),
            "status":       "logged",
            "outcome":      None,
            "outcome_date": None,
        }
        try:
            save_action(record)
            record_in_playbook(
                record["issue_type"],
                record["employee"],
                record["type"],
            )
        except Exception as exc:
            self._chat_append(
                "System", f"Could not save action: {exc}",
                "name_assistant", "error")
        self._pending_action = None
        self._dismiss_action_card()
        self._chat_append(
            "System",
            f"Action logged to luca_actions.json  "
            f"({record['type']} / {record['employee']})",
            "name_assistant", "thinking")

    def _load_gemini_key(self):
        """Load Gemini API key from env var or config file."""
        return _load_gemini_key_global()

    def _save_gemini_key(self, key):
        """Save Gemini API key to config file."""
        _save_gemini_key_global(key)

    def _save_creds(self):
        """Save Anthropic and Gemini API keys from the sidebar credential fields."""
        ant_key = self.anthropic_key_entry.get().strip()
        if ant_key:
            self._anthropic_key = ant_key
            _save_api_key(ant_key)
        gemini_key = self.gemini_key_entry.get().strip()
        if gemini_key:
            self._save_gemini_key(gemini_key)

    def _prompt_api_key(self):
        from tkinter import simpledialog
        key = simpledialog.askstring(
            "Anthropic API Key",
            ("Paste your Anthropic API key to enable Ask LUCA.\n"
             "Get one at console.anthropic.com\n\n"
             "It will be saved to ~/Documents/Luca/luca_config.json"),
            show="*", parent=self)
        if key and key.strip():
            self._anthropic_key = key.strip()
            _save_api_key(self._anthropic_key)

    def _sync_data(self):
        """Run Ajera cache sync in background thread."""
        self.sync_btn.configure(state="disabled", text="Syncing…")
        self.cache_age_lbl.configure(text="Syncing Ajera data…")

        def _run():
            def _cb(msg):
                self.after(0, lambda m=msg: self.cache_age_lbl.configure(
                    text=m[:55] + "…" if len(m) > 55 else m))
            try:
                sync_ajera_cache(progress_cb=_cb, refresh_mode="full")
                self.after(0, self._sync_done)
            except Exception as e:
                self.after(0, lambda err=str(e): self._sync_error(err))

        threading.Thread(target=_run, daemon=True).start()

    # ── Session persistence ────────────────────────────────────────────────────

    def _save_session(self):
        """Write current chat + audit context to luca_session.json."""
        try:
            session = {
                "saved_at":     datetime.now().isoformat(),
                "audit_period": self._audit_period,
                "audit_context": self._audit_context or "",
                "chat_history": self._chat_history,
                "chat_display": self._chat_display,
                "last_response": self._last_response,
            }
            SESSION_FILE.write_text(
                json.dumps(session, indent=2, default=str), encoding="utf-8"
            )
        except Exception as exc:
            print(f"[SESSION] Save failed: {exc}")

    def _restore_session(self):
        """Reload the last session and re-render the conversation in the chat box."""
        if not SESSION_FILE.exists():
            return
        try:
            session = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            ctx      = session.get("audit_context") or ""
            period   = session.get("audit_period") or ""
            history  = session.get("chat_history") or []
            display  = session.get("chat_display") or []

            if not display:
                return   # nothing to restore

            self._audit_context  = ctx or None
            self._audit_period   = period
            self._chat_history   = history
            self._chat_display   = display
            self._last_response  = session.get("last_response") or ""

            saved_at = session.get("saved_at", "")
            try:
                saved_dt  = datetime.fromisoformat(saved_at)
                saved_lbl = saved_dt.strftime("%b %d, %Y  %I:%M %p")
            except Exception:
                saved_lbl = saved_at[:16]

            # Re-render conversation in the chat box
            self.chat_box.config(state="normal")
            self.chat_box.delete("1.0", "end")

            # Subtle restored-session header
            header = (
                f"↩  Session restored"
                + (f"  ·  {period}" if period else "")
                + f"  ·  last saved {saved_lbl}\n"
                + "─" * 72
            )
            self.chat_box.insert("end", header + "\n\n", "thinking")

            for msg in display:
                sender   = msg.get("sender", "")
                text     = msg.get("text", "")
                name_tag = msg.get("name_tag", "name_user")
                body_tag = msg.get("body_tag", "user")
                if self.chat_box.index("end-1c") not in ("1.0", ""):
                    self.chat_box.insert("end", "\n\n")
                self.chat_box.insert("end", sender + "\n", name_tag)
                self.chat_box.insert("end", text, body_tag)

            self.chat_box.config(state="disabled")
            self.chat_box.see("end")

        except Exception as exc:
            print(f"[SESSION] Restore failed: {exc}")

    def _on_close(self):
        """Save session then close the window."""
        self._save_session()
        self.destroy()

    def _refresh_timesheet_cache_bg(self):
        """Silently refresh the last TS_REFRESH_WEEKS of timesheets after an audit.

        Runs in a daemon thread — does not block the UI or the audit result.
        Uses partial mode: only the 4 most recent weeks are re-fetched to catch
        any retroactive edits employees made during the day.  The remaining 6
        weeks in the rolling window are preserved as-is.
        Skips if no cache exists yet (first-run — user must run Sync Data first).
        """
        def _run():
            try:
                if not load_ajera_cache():
                    return   # no cache yet
                sync_ajera_cache(
                    progress_cb=lambda m: print(f"[CACHE BG] {m}"),
                    refresh_mode="partial",
                )
            except Exception as exc:
                print(f"[CACHE BG] Background timesheet refresh failed: {exc}")

        threading.Thread(target=_run, daemon=True).start()

    def _sync_done(self):
        self.sync_btn.configure(state="normal", text="Sync Data")
        self.cache_age_lbl.configure(text=cache_age_label())

    def _sync_error(self, msg):
        self.sync_btn.configure(state="normal", text="Sync Data")
        self.cache_age_lbl.configure(text=f"Sync error: {msg[:40]}")

    def _audit_error(self, msg):
        self.progress.stop()
        self.progress.set(0)
        self._spinner.stop()
        self.run_btn.configure(state="normal")
        self._set_status(f"Error: {msg}", RED)
        messagebox.showerror("Audit Error", msg)


# ── ENTRY ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = AuditApp()
    app.mainloop()
