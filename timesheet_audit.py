# -*- coding: utf-8 -*-
"""
Ajera Timesheet Audit Tool
Pulls real timesheet data from Ajera API and flags issues before invoicing.

Usage:
  python timesheet_audit.py       -> current week
  python timesheet_audit.py -1    -> last week
  python timesheet_audit.py -2    -> two weeks ago
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
import json
from datetime import datetime, timedelta
from collections import defaultdict

# ── CONFIG ────────────────────────────────────────────────────────────────────
API_ENDPOINT = (
    "https://ajera.com/V004613/AjeraAPI.ashx"
    "?ew0KICAiQ2xpZW50SUQiOiA0NjEzLA0KICAiRGF0YWJhc2VJRCI6IDE5NzI2LA0K"
    "ICAiSXNTYW1wbGVEYXRhIjogZmFsc2UNCn0%3d"
)
USERNAME = "ClaudeTime247"
PASSWORD = "GuinneaPig247!"
MIN_HOURS_PER_DAY = 8.0
OVERHEAD_KEYWORDS = [
    "overhead", "general", "admin", "vacation", "holiday",
    "pto", "sick", "training", "business development", "bd",
    "marketing", "office"
]
WORKDAYS = {0, 1, 2, 3, 4}  # Mon-Fri (weekday() values)


# ── API HELPERS ───────────────────────────────────────────────────────────────

def api_call(payload):
    r = requests.post(
        API_ENDPOINT,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=30
    )
    r.raise_for_status()
    result = r.json()
    code = result.get("ResponseCode")
    if code not in (None, 0, "0", 200, "200"):
        raise RuntimeError(result.get("Message", str(result)))
    return result


def login(version=2):
    resp = api_call({
        "Method": "CreateAPISession",
        "Username": USERNAME,
        "Password": PASSWORD,
        "APIVersion": version
    })
    token = resp.get("SessionToken") or resp.get("Content", {}).get("SessionToken")
    print(f"  Logged in (API v{version})")
    return token


def logout(token):
    try:
        api_call({"Method": "EndAPISession", "SessionToken": token})
    except Exception:
        pass


def list_employees(token):
    resp = api_call({
        "Method": "ListEmployees",
        "SessionToken": token,
        "MethodArguments": {"FilterByStatus": ["Active"]}
    })
    employees = resp.get("Content", {}).get("Employees", [])
    print(f"  Found {len(employees)} active employees")
    return employees


def list_timesheets(token, start_date, end_date):
    resp = api_call({
        "Method": "ListTimesheets",
        "SessionToken": token,
        "MethodArguments": {
            "FilterByEarliestTimesheetDate": str(start_date),
            "FilterByLatestTimesheetDate": str(end_date),
        }
    })
    sheets = resp.get("Content", {}).get("Timesheets", [])
    print(f"  Found {len(sheets)} timesheets")
    return sheets


def get_timesheets(token, ts_keys):
    resp = api_call({
        "Method": "GetTimesheets",
        "SessionToken": token,
        "MethodArguments": {"RequestedTimesheets": ts_keys}
    })
    return resp.get("Content", {}).get("Timesheets", [])


# ── DATE HELPERS ──────────────────────────────────────────────────────────────

def get_week_range(offset_weeks=0):
    """Return (monday, friday) for the current or offset week."""
    today = datetime.today()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset_weeks)
    friday = monday + timedelta(days=4)
    return monday.date(), friday.date()


def day_date_from_sheet(ts_date_str, d_index):
    """
    Ajera TimesheetDate is the FRIDAY (last day) of the week.
    D1=Sat, D2=Sun, D3=Mon, D4=Tue, D5=Wed, D6=Thu, D7=Fri.
    So D1 = ts_date - 6 days.
    """
    ts_date = datetime.strptime(ts_date_str[:10], "%Y-%m-%d").date()
    return ts_date - timedelta(days=6) + timedelta(days=d_index - 1)


def is_workday(d):
    return d.weekday() in WORKDAYS


def is_overhead(description):
    return any(kw in (description or "").lower() for kw in OVERHEAD_KEYWORDS)


# ── AUDIT ─────────────────────────────────────────────────────────────────────

def audit(detailed_sheets, employee_map):
    """
    Returns (flags_dict, raw_entries_list).

    flags keys:
      incomplete_days, missing_notes, full_overhead_days, collab_mismatches
    """
    flags = {
        "incomplete_days":    [],
        "missing_notes":      [],
        "full_overhead_days": [],
        "collab_mismatches":  [],
    }

    # (project_key, date_str) -> list of {employee, hours}
    project_day_log = defaultdict(list)

    raw_entries = []

    for sheet in detailed_sheets:
        emp_key   = sheet.get("EmployeeKey")
        emp_name  = (
            employee_map.get(emp_key)
            or f"{sheet.get('FirstName','')} {sheet.get('LastName','')}".strip()
            or f"Employee #{emp_key}"
        )
        ts_date_str = str(sheet.get("TimesheetDate", ""))

        # ── Collect per-day data ──────────────────────────────────────────────
        # day_date -> {hours, overhead_hours, has_note, entries[]}
        days = defaultdict(lambda: {
            "hours": 0.0, "overhead_hours": 0.0,
            "has_note": False, "entries": []
        })

        # Overhead rows
        for entry in (sheet.get("Overhead", {}).get("Detail") or []):
            desc = entry.get("Timesheet Overhead Group Detail", "")
            for d in range(1, 8):
                hrs  = float(entry.get(f"D{d} Regular") or 0)
                note = (entry.get(f"D{d} Notes") or "").strip()
                if hrs <= 0:
                    continue
                date = day_date_from_sheet(ts_date_str, d)
                days[date]["hours"]          += hrs
                days[date]["overhead_hours"] += hrs
                if note:
                    days[date]["has_note"] = True
                days[date]["entries"].append({
                    "type": "overhead", "description": desc,
                    "hours": hrs, "note": note,
                })

        # Project rows
        for entry in (sheet.get("Project", {}).get("Detail") or []):
            proj_desc = entry.get("Project Description", "")
            phase_desc = entry.get("Phase Description", "")
            activity   = entry.get("Activity", "")
            proj_key   = entry.get("Project Key")
            for d in range(1, 8):
                reg  = float(entry.get(f"D{d} Regular")  or 0)
                ovt  = float(entry.get(f"D{d} Overtime") or 0)
                note = (entry.get(f"D{d} Notes") or "").strip()
                hrs  = reg + ovt
                if hrs <= 0:
                    continue
                date = day_date_from_sheet(ts_date_str, d)
                days[date]["hours"] += hrs
                if note:
                    days[date]["has_note"] = True
                days[date]["entries"].append({
                    "type": "project", "description": proj_desc,
                    "phase": phase_desc, "activity": activity,
                    "hours": hrs, "note": note,
                    "project_key": proj_key,
                })
                project_day_log[(proj_key, str(date))].append(
                    {"employee": emp_name, "hours": hrs}
                )

        # ── Evaluate each worked day ──────────────────────────────────────────
        for date in sorted(days.keys()):
            if not is_workday(date):
                continue
            day = days[date]
            label = date.strftime("%a %m/%d")
            total = day["hours"]

            raw_entries.append({
                "employee": emp_name,
                "date": label,
                "sort_key": (emp_name, date),
                "total_hours": total,
                "entries": day["entries"],
            })

            if total < MIN_HOURS_PER_DAY:
                flags["incomplete_days"].append({
                    "employee": emp_name, "date": label,
                    "hours": total,
                    "missing": round(MIN_HOURS_PER_DAY - total, 2),
                })

            for e in day["entries"]:
                if not e["note"]:
                    flags["missing_notes"].append({
                        "employee": emp_name, "date": label,
                        "description": e.get("description", "-"),
                        "hours": e["hours"], "type": e["type"],
                    })

            if total > 0 and day["overhead_hours"] >= total * 0.9:
                flags["full_overhead_days"].append({
                    "employee": emp_name, "date": label,
                    "hours": total, "has_note": day["has_note"],
                })

    # ── Collaboration mismatches ──────────────────────────────────────────────
    for (proj_key, date_str), entries in project_day_log.items():
        if len(entries) < 2:
            continue
        hrs_list = [e["hours"] for e in entries]
        avg = sum(hrs_list) / len(hrs_list)
        for e in entries:
            if abs(e["hours"] - avg) > 1.5:
                flags["collab_mismatches"].append({
                    "date": date_str, "project_key": proj_key,
                    "employee": e["employee"], "hours": e["hours"],
                    "team_avg": round(avg, 2), "all_entries": entries,
                })

    raw_entries.sort(key=lambda x: x["sort_key"])
    return flags, raw_entries


# ── REPORT ────────────────────────────────────────────────────────────────────

def print_report(flags, raw_entries, start_date, end_date):
    W = 70
    SEP  = "=" * W
    sep  = "-" * W

    print(f"\n{SEP}")
    print(f"  TIMESHEET AUDIT REPORT")
    print(f"  Week: {start_date}  to  {end_date}")
    print(f"  Run:  {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
    print(SEP)

    # Blocked entries
    mn = flags["missing_notes"]
    print(f"\n[BLOCKED] ENTRIES WITHOUT NOTES  ({len(mn)})")
    print("  Cannot be invoiced until a note is added.\n")
    if mn:
        for f in mn:
            print(f"  * {f['employee']}  |  {f['date']}  |  "
                  f"{f['description']}  |  {f['hours']}h  ({f['type']})")
    else:
        print("  OK - all entries have notes.")

    # Incomplete days
    inc = flags["incomplete_days"]
    print(f"\n[WARN] INCOMPLETE DAYS  ({len(inc)})\n")
    if inc:
        for f in inc:
            print(f"  * {f['employee']}  |  {f['date']}  |  "
                  f"{f['hours']}h logged  ({f['missing']}h short)")
    else:
        print("  OK - all employees >= 8h every day.")

    # Full overhead days
    foh = flags["full_overhead_days"]
    print(f"\n[WARN] FULL OVERHEAD / GENERAL DAYS  ({len(foh)})\n")
    if foh:
        for f in foh:
            note_flag = "has note" if f["has_note"] else "NO NOTE"
            print(f"  * {f['employee']}  |  {f['date']}  |  "
                  f"{f['hours']}h to overhead  ({note_flag})")
    else:
        print("  OK - no full overhead days.")

    # Collab mismatches
    cm = flags["collab_mismatches"]
    print(f"\n[WARN] COLLABORATION MISMATCHES  ({len(cm)})\n")
    if cm:
        for f in cm:
            others = ", ".join(
                f"{e['employee']} ({e['hours']}h)"
                for e in f["all_entries"] if e["employee"] != f["employee"]
            )
            print(f"  * {f['employee']}  |  {f['date']}  |  "
                  f"Project #{f['project_key']}  |  {f['hours']}h  "
                  f"(avg {f['team_avg']}h)  |  Others: {others}")
    else:
        print("  OK - no collaboration mismatches.")

    # Full detail
    print(f"\n{SEP}")
    print(f"  FULL DETAIL")
    print(SEP)
    current_emp = None
    for row in raw_entries:
        if row["employee"] != current_emp:
            current_emp = row["employee"]
            print(f"\n  {current_emp}")
            print(f"  {sep}")
        warn = " *** SHORT" if row["total_hours"] < MIN_HOURS_PER_DAY else ""
        print(f"\n    {row['date']}  |  {row['total_hours']}h total{warn}")
        for e in row["entries"]:
            no_note = "  *** NO NOTE" if not e["note"] else ""
            if e["type"] == "project":
                label = e.get("description", "-")
                if e.get("phase"):
                    label += f" / {e['phase']}"
                if e.get("activity"):
                    label += f" [{e['activity']}]"
            else:
                label = f"[OVERHEAD] {e.get('description','-')}"
            note_text = e["note"] or "---"
            print(f"      {e['hours']}h  {label}{no_note}")
            print(f"           Note: {note_text}")

    # Summary
    total_issues = sum(len(v) for v in flags.values())
    print(f"\n{SEP}")
    print(f"  SUMMARY")
    print(sep)
    print(f"  Blocked (no notes):         {len(mn)}")
    print(f"  Incomplete days:            {len(inc)}")
    print(f"  Full overhead days:         {len(foh)}")
    print(f"  Collaboration mismatches:   {len(cm)}")
    print(sep)
    print(f"  TOTAL ISSUES:               {total_issues}")
    if total_issues == 0:
        print(f"\n  All clear - timesheets look good for invoicing.")
    else:
        print(f"\n  Resolve all issues before generating invoices.")
    print(SEP + "\n")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def run_audit(offset_weeks=0):
    start_date, end_date = get_week_range(offset_weeks)
    print(f"\nAjera Timesheet Audit  |  {start_date}  to  {end_date}")
    print("-" * 50)

    token_v1 = token_v2 = None
    try:
        print("\n[1/4] Authenticating...")
        token_v1 = login(version=1)
        token_v2 = login(version=2)

        print("\n[2/4] Loading employees...")
        employees = list_employees(token_v1)
        employee_map = {
            e.get("EmployeeKey"):
            f"{e.get('FirstName','')} {e.get('LastName','')}".strip()
            for e in employees
        }

        print("\n[3/4] Loading timesheets...")
        ts_list = list_timesheets(token_v2, start_date, end_date)
        ts_keys = [t.get("Timesheet Key") for t in ts_list if t.get("Timesheet Key")]

        if not ts_keys:
            print("\n  No timesheets found for this period.")
            return

        detailed = get_timesheets(token_v2, ts_keys)
        print(f"  Loaded detail for {len(detailed)} timesheets")

        print("\n[4/4] Running audit...")
        flags, raw_entries = audit(detailed, employee_map)

        # Write report to file AND print to console
        report_path = (
            f"C:\\Users\\Grupo51\\Claude\\TimeAuditInvoicePrep\\"
            f"audit_{start_date}.txt"
        )
        import io as _io
        buf = _io.StringIO()
        _orig_stdout = sys.stdout
        sys.stdout = _io.TextIOWrapper(
            _io.BytesIO(), encoding='utf-8', errors='replace'
        )
        # Capture into buffer by redirecting through a tee
        sys.stdout = _orig_stdout  # restore first

        # Capture report text
        import contextlib
        report_buf = _io.StringIO()
        with contextlib.redirect_stdout(report_buf):
            print_report(flags, raw_entries, start_date, end_date)
        report_text = report_buf.getvalue()

        # Print to console
        print(report_text, end="")

        # Save to file
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)
        print(f"\n  Report saved to: {report_path}")

    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        for t in [token_v1, token_v2]:
            if t:
                logout(t)
        print("  Sessions closed.")


if __name__ == "__main__":
    offset = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    run_audit(offset_weeks=offset)
