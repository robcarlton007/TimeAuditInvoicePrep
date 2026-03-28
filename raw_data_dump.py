# -*- coding: utf-8 -*-
"""
Raw API data dump — exports every field from every timesheet entry to CSV.
"""
import sys, io, json, csv, requests
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_ENDPOINT = (
    "https://ajera.com/V004613/AjeraAPI.ashx"
    "?ew0KICAiQ2xpZW50SUQiOiA0NjEzLA0KICAiRGF0YWJhc2VJRCI6IDE5NzI2LA0K"
    "ICAiSXNTYW1wbGVEYXRhIjogZmFsc2UNCn0%3d"
)
USERNAME = "ClaudeTime247"
PASSWORD = "GuinneaPig247!"
OUTPUT   = Path(r"C:\Users\Grupo51\Claude\TimeAuditInvoicePrep\raw_dump_2026-03-18.csv")

def call(payload):
    r = requests.post(API_ENDPOINT,
                      headers={"Content-Type": "application/json"},
                      data=json.dumps(payload), timeout=90)
    r.raise_for_status()
    return r.json()

def login(v):
    resp = call({"Method":"CreateAPISession","Username":USERNAME,
                 "Password":PASSWORD,"APIVersion":v})
    return resp["Content"]["SessionToken"]

def logout(t):
    try: call({"Method":"EndAPISession","SessionToken":t})
    except: pass

TARGET_DATE = "2026-03-18"

# Ajera timesheets are keyed by the Friday end-of-week.
# Find the Friday that ends the week containing TARGET_DATE.
target_dt   = datetime.strptime(TARGET_DATE, "%Y-%m-%d").date()
days_to_fri = (4 - target_dt.weekday()) % 7   # 4 = Friday
week_friday = target_dt + timedelta(days=days_to_fri)
# Query the full week so Ajera returns the right timesheet records
week_saturday = week_friday - timedelta(days=6)

print(f"Pulling all timesheet data for {TARGET_DATE}...")
print(f"  (querying week {week_saturday} to {week_friday})")

t1 = login(1)
t2 = login(2)

# ── Employees ─────────────────────────────────────────────────────────────────
emp_resp = call({"Method":"ListEmployees","SessionToken":t1,
                 "MethodArguments":{"FilterByStatus":["Active"]}})
employees = emp_resp["Content"]["Employees"]
emp_map = {e["EmployeeKey"]: e for e in employees}
print(f"  Employees: {len(employees)}")

# ── Timesheet list ────────────────────────────────────────────────────────────
ts_resp = call({"Method":"ListTimesheets","SessionToken":t2,
                "MethodArguments":{
                    "FilterByEarliestTimesheetDate": str(week_saturday),
                    "FilterByLatestTimesheetDate":   str(week_friday)}})
ts_list = ts_resp["Content"]["Timesheets"]
ts_keys = [t["Timesheet Key"] for t in ts_list if t.get("Timesheet Key")]
print(f"  Timesheets found: {len(ts_keys)}")

# ── Detailed timesheets ───────────────────────────────────────────────────────
all_detail = []
for i in range(0, len(ts_keys), 10):
    chunk = ts_keys[i:i+10]
    resp = call({"Method":"GetTimesheets","SessionToken":t2,
                 "MethodArguments":{"RequestedTimesheets":chunk}})
    all_detail.extend(resp["Content"]["Timesheets"])
print(f"  Detail records: {len(all_detail)}")

logout(t1); logout(t2)

# ── Determine target day index ────────────────────────────────────────────────
# Ajera: TimesheetDate = Friday end of week; D1=Sat, D7=Fri
# 2026-03-18 is Wednesday. Find which D index it falls on per sheet.

def d_index_for_date(ts_date_str, target):
    ts = datetime.strptime(ts_date_str[:10], "%Y-%m-%d").date()
    for d in range(1, 8):
        candidate = ts - timedelta(days=6) + timedelta(days=d-1)
        if candidate == target:
            return d
    return None

target = datetime.strptime(TARGET_DATE, "%Y-%m-%d").date()

# ── Build rows ────────────────────────────────────────────────────────────────
rows = []

for sheet in all_detail:
    ek       = sheet.get("EmployeeKey")
    emp      = emp_map.get(ek, {})
    emp_name = f"{emp.get('FirstName','')} {emp.get('LastName','')}".strip() or f"#{ek}"
    dept     = emp.get("Department", "")
    ts_date  = str(sheet.get("TimesheetDate",""))
    ts_key   = sheet.get("TimesheetKey")
    submitted= sheet.get("Submitted", "")
    ts_total = sheet.get("TimesheetTotal", "")

    d = d_index_for_date(ts_date, target)
    if d is None:
        continue  # this sheet doesn't cover the target date

    # Overhead entries
    for entry in (sheet.get("Overhead", {}).get("Detail") or []):
        hrs  = entry.get(f"D{d} Regular") or 0
        note = entry.get(f"D{d} Notes") or ""
        rows.append({
            "TimesheetKey":      ts_key,
            "TimesheetDate":     ts_date,
            "EmployeeKey":       ek,
            "Employee":          emp_name,
            "Department":        dept,
            "Submitted":         submitted,
            "TimesheetTotal":    ts_total,
            "EntryType":         "Overhead",
            "ProjectKey":        entry.get("Project Key",""),
            "ProjectDesc":       "",
            "PhaseKey":          "",
            "PhaseDesc":         "",
            "ActivityKey":       entry.get("Activity Key",""),
            "Activity":          "",
            "OverheadGroupKey":  entry.get("Timesheet Overhead Group",""),
            "OverheadGroupDetail": entry.get("Timesheet Overhead Group Detail",""),
            "OverheadGroupDetailKey": entry.get("Timesheet Overhead Group Detail Key",""),
            "Row":               entry.get("Row",""),
            "RequireNotes":      entry.get("RequireNotes",""),
            f"D{d}_Regular":     hrs,
            f"D{d}_Notes":       note,
            "Date":              TARGET_DATE,
            "DayIndex":          d,
            # All 7 days raw for reference
            "D1_Regular": entry.get("D1 Regular",""), "D1_Notes": entry.get("D1 Notes",""),
            "D2_Regular": entry.get("D2 Regular",""), "D2_Notes": entry.get("D2 Notes",""),
            "D3_Regular": entry.get("D3 Regular",""), "D3_Notes": entry.get("D3 Notes",""),
            "D4_Regular": entry.get("D4 Regular",""), "D4_Notes": entry.get("D4 Notes",""),
            "D5_Regular": entry.get("D5 Regular",""), "D5_Notes": entry.get("D5 Notes",""),
            "D6_Regular": entry.get("D6 Regular",""), "D6_Notes": entry.get("D6 Notes",""),
            "D7_Regular": entry.get("D7 Regular",""), "D7_Notes": entry.get("D7 Notes",""),
        })

    # Project entries
    for entry in (sheet.get("Project", {}).get("Detail") or []):
        reg  = entry.get(f"D{d} Regular")  or 0
        ovt  = entry.get(f"D{d} Overtime") or 0
        note = entry.get(f"D{d} Notes")    or ""
        rows.append({
            "TimesheetKey":      ts_key,
            "TimesheetDate":     ts_date,
            "EmployeeKey":       ek,
            "Employee":          emp_name,
            "Department":        dept,
            "Submitted":         submitted,
            "TimesheetTotal":    ts_total,
            "EntryType":         "Project",
            "ProjectKey":        entry.get("Project Key",""),
            "ProjectDesc":       entry.get("Project Description",""),
            "PhaseKey":          entry.get("Phase Key",""),
            "PhaseDesc":         entry.get("Phase Description",""),
            "ActivityKey":       entry.get("Activity Key",""),
            "Activity":          entry.get("Activity",""),
            "OverheadGroupKey":  "",
            "OverheadGroupDetail": "",
            "OverheadGroupDetailKey": "",
            "Row":               entry.get("Row",""),
            "RequireNotes":      entry.get("RequireNotes",""),
            f"D{d}_Regular":     reg,
            f"D{d}_Notes":       note,
            "Date":              TARGET_DATE,
            "DayIndex":          d,
            "D1_Regular": entry.get("D1 Regular",""), "D1_Notes": entry.get("D1 Notes",""),
            "D2_Regular": entry.get("D2 Regular",""), "D2_Notes": entry.get("D2 Notes",""),
            "D3_Regular": entry.get("D3 Regular",""), "D3_Notes": entry.get("D3 Notes",""),
            "D4_Regular": entry.get("D4 Regular",""), "D4_Notes": entry.get("D4 Notes",""),
            "D5_Regular": entry.get("D5 Regular",""), "D5_Notes": entry.get("D5 Notes",""),
            "D6_Regular": entry.get("D6 Regular",""), "D6_Notes": entry.get("D6 Notes",""),
            "D7_Regular": entry.get("D7 Regular",""), "D7_Notes": entry.get("D7 Notes",""),
        })

# ── Write CSV ─────────────────────────────────────────────────────────────────
if rows:
    fields = list(rows[0].keys())
    with open(OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nDone. {len(rows)} rows written to:\n  {OUTPUT}")
else:
    print("\nNo entries found for that date.")
