# Luca
### Carlton Edwards Intelligence · Timesheet Audit & Daily Review System

---

## About the Name

This application is named in honor of **Luca Pacioli** (c. 1447–1517), a 15th-century Franciscan friar and mathematician widely regarded as the *"Father of Accounting."*

In 1494, Pacioli codified the double-entry bookkeeping system in his landmark work *Summa de Arithmetica, Geometria, Proportioni et Proportionalità* — the first printed treatise on accounting. His work enabled precise, systematic tracking of revenue, expenses, and time-based costs, laying the foundation for every modern financial and cost accounting practice in use today.

The app icon is drawn from the **rhombicuboctahedron** illustration in Pacioli's *De Divina Proportione* (1509), drawn by Leonardo da Vinci.

*Luca* carries that tradition forward: ensuring that every hour of work is captured, coded correctly, and accounted for before a single invoice goes out the door.

---

## Modes of Operation

Luca operates in two modes:

### Manual Audit (current)
Run on demand from the desktop app:
1. Open `Luca.exe`
2. Select a date range using the preset buttons or the **From / To** date pickers in the sidebar
3. Select studios — check/uncheck **Asheville**, **Nashville**, **Memphis**
4. Click **Run Audit** — Luca pulls timesheets and generates the report (reference data served from local cache; timesheets always fetched live)
5. When complete, click **Open Report** to view in your browser, or **Print Report** to send to a printer

### Automated Daily Mode *(roadmap)*
Luca runs automatically every morning at **6:00 AM**, pulls the prior day's timesheets, and delivers targeted reports and notifications without any manual action:
- Employees with no timesheet entries receive a personalized AI-written reminder (CC: their supervisor)
- Incomplete entries trigger a separate notification
- Supervisors receive a comprehensive AI-written report for their studio
- Escalation messages fire automatically based on consecutive missed days
- All reference data syncs from Ajera at **5:50 AM** before the report runs

See `LUCA.md` for notification rules, escalation tiers, manager assignments, and scheduling details.

---

## Sidebar Controls

| Control | Description |
|---|---|
| **Date presets** | This Week / Last Week / 2 Weeks Ago / This Month / Last Month |
| **From / To pickers** | Manual date range entry |
| **Asheville / Nashville / Memphis** | Filter by studio; uncheck to exclude a location |
| **Sync Data** | Refresh local Ajera cache (employees, projects, phases, activities) — also fetches 10 weeks of timesheet history |
| **Run Audit** | Runs the full audit; uses cached reference data, fetches live timesheets |
| **Open Report** | Opens the most recent HTML report in your browser |
| **Print Report** | Opens the report ready to print |
| **About** | App version and credits |

---

## Date Range Presets

| Button | Range |
|---|---|
| This Week / Last Week / 2 Weeks Ago | Saturday–Friday payroll week |
| This Month / Last Month | First to last day of the calendar month |

---

## Local Cache — Cache-First Architecture

Luca maintains a local data layer at `~/Documents/Luca/ajera_cache.json`. Reference data (employees, projects, phases, activities, companies, departments) is served from this cache and only re-fetched from Ajera when the cache is older than **24 hours** or when **Sync Data** is clicked.

### Rolling Timesheet Window

The cache stores **10 weeks** of full timesheet detail in a week-keyed rolling structure (one entry per payroll Friday). This enables two sync modes:

| Mode | Trigger | What it fetches |
|---|---|---|
| **Full sync** | Sync Data button | All reference data + 10 weeks of timesheets |
| **Partial sync** | Background refresh after each audit | Last 4 weeks of timesheets only (reference data untouched) |

After every sync, weeks older than 10 weeks are automatically dropped. The partial mode ensures retroactive timesheet edits by employees are always captured without re-fetching the entire history.

**Why this matters:** Most chat questions — *"How has Emily's hours trended over the last month?"* — are answered instantly from local data. Live API calls only happen when you query dates outside the cached window, or when running a fresh audit.

---

## Access Roles *(roadmap)*

| Tier | Who | Access |
|---|---|---|
| **Admin** | Rob Carlton + designated | Full — all studios, backend sync, config, notifications |
| **Supervisor** | Matt Zink (Nashville), Jeff Edwards (Memphis), Rob Carlton (Asheville) | Their studio's reports and team notifications |
| **Employee** | All other staff | Their own timesheet data |

Employee roles are sourced from Ajera first (`IsPrincipal`, `IsSupervisor`, `SupervisorKey`). `LUCA.md` defines the supervisory relationships and any overrides not available in Ajera.

---

## What Gets Flagged

### Blocked — Project Entries Without Notes
Any **project** time entry with no description note is flagged and blocked from invoicing. Marked with a red indicator. A note must be added before the invoice can go out.

### PTO / Overhead Entries Without Notes — OK
Overhead entries for PTO, vacation, holiday, or sick leave **do not** require notes. These are marked with a green check and excluded from the blocked count.

### Incomplete Days
Any working day (Mon–Fri) where an employee logged less than their daily minimum:
- Standard employees: **8 h/day** (40 h/week)
- Non-standard employees (e.g., Gordon Shisler): **6.4 h/day** (32 h/week — configured in `luca_reference.json`)

Each flag shows: hours logged, shortfall, **current-week total**, and **prior-week total** (to identify makeup patterns across weeks).

Weekend hours (Saturday/Sunday) count toward the weekly total but are never flagged as incomplete days.

### Full Overhead / General Days
Any day where 90% or more of an employee's hours were coded to overhead or general codes with no project work. Shows the overhead code and whether a note was present.

### Missing Timesheet — No Entry *(automated mode)*
Employee has no timesheet entry at all for a prior business day. Triggers a personalized AI-written message to the employee with supervisor CC.

### Escalations — Consecutive Missed Days *(roadmap)*
Escalation tiers exist but the messages are not scripted — Claude writes each one fresh based on the severity and history. See `LUCA.md` for tier definitions and tone directives.

### Spelling / Typo Detection *(roadmap)*
Notes are checked against a standard dictionary plus a firm-specific whitelist of known terms (project names, phase codes, acronyms). Flagged words are highlighted in the report for review. Whitelist managed in `LUCA.md`.

---

## Report Layout

| Tab | Contents |
|---|---|
| **Flags** | All issues grouped by type — blocked entries, incomplete days, overhead days |
| **Teamwork** | Every collaborative work entry across the team, organized by employee |
| **By Employee** | Full period per employee, day by day, with every entry and note |
| **By Project** | Every project with all employees, phases, activities, hours, and notes |

Click the **Print** button in the report header (or **Print Report** in the app) to print. All tabs print on separate pages.

---

## Teamwork Section

The **Teamwork** tab in the report shows every instance of collaborative work for the audit period — organized by employee.

**Detection:** Any time entry note that contains a synchronous-collaboration indicator is captured:
- Direct verbs: *met with, discussed, reviewed with, worked with, called with, synced with*
- Group sessions: *team meeting, charrette, workshop, kickoff, coordination call, working session*
- Indirect but real-time: *together, co-working, joint review, presentation with*

Asynchronous or possessive references (*"watched Rob's Loom," "reviewed Matt's markups," "per Emily's comments"*) are filtered out — only real-time joint work is included.

**Each entry shows:** date · project · phase · hours · verbatim note

---

## Supervisor Reports *(roadmap)*

Each supervisor receives a daily AI-written report scoped to their studio only:
- Employees missing timesheets + escalation tier
- Incomplete hours (flagged days, shortfall per employee)
- Project entries without notes
- Collaborative citations involving their team
- Cross-reference status: are both collaborating employees logging to the same project and phase?

| Supervisor | Studio |
|---|---|
| Rob Carlton | Asheville |
| Matt Zink | Nashville |
| Jeff Edwards | Memphis |

---

## Collaboration Citations

In addition to the Teamwork section, Luca tracks **citations** — when one employee names a colleague in a collaborative note. Citations are organized by the **mentioned person**.

Each citation shows: who mentioned them · date · project · phase · verbatim note.

### Cross-Reference Validation
Beyond detecting citations, Luca cross-references that **both employees** in a collaborative pair are recording their time consistently:
- Same project
- Same phase
- Hours within a reasonable range

Mismatches (wrong project, missing entry, wrong phase) are flagged separately from the citation itself.

---

## Ask Luca — AI Chat

The **Ask Luca** panel sits at the bottom of the app window. It is powered by **Claude (Anthropic)** with automatic fallback to **Gemini (Google)**.

The chat is a **persistent, scrollable session** — conversation history survives across questions and is automatically saved to `luca_session.json` when the app closes. When you reopen the app, the prior session is restored with a header showing the period and last-save timestamp.

### Context available to Luca
- Complete audit-period timesheet data (all flags, per-employee log, per-project log)
- **10 weeks** of rolling timesheet history (for trend analysis — served from local cache)
- Full active employee roster with studio and company assignments
- Firm reference data: overhead code definitions, per-employee hour targets, billable targets
- Firm organizational structure (companies and departments)
- The firm's action log and learned playbook
- Business rules, phase definitions, and billing confusion patterns from `luca_knowledge.yaml`

### Live Ajera Queries
Luca can query the Ajera API directly, on demand, during the chat — independent of the time audit. When the requested data is already in the local cache, it is served instantly without an API call.

| What to ask | What Luca does |
|---|---|
| *"Show all active employees with their employee keys"* | Returns from cache (or live if stale) |
| *"List all active projects"* | Returns from cache (or live if stale) |
| *"Show phases for the Riverfront project"* | Returns from cache (or live if stale) |
| *"What activity codes are in the system?"* | Returns from cache (or live if stale) |
| *"Pull Emily's timesheets for February"* | Fetches from Ajera if outside cached window |

### Session Persistence
The full chat session is saved automatically when the app closes (including conversation history and audit context). On relaunch, the session is restored exactly — no data is lost.

To start fresh, use **Save Session** to archive the current session, then close and reopen the app.

### Example questions
- *"Who has the most missing notes this week?"*
- *"Is Emily's hours trend improving compared to last month?"*
- *"Which projects have incomplete entries that could hold up invoicing?"*
- *"Has Gordon made up his hours for the short days flagged this week?"*
- *"How many hours did Carlton Edwards PLLC log to overhead in March?"*
- *"What is the ProjectKey for the Greenway Park project?"*

---

## Action System — Fully Autonomous

LUCA detects action opportunities within its responses and **executes them immediately** — no admin initiation required, no approval step.

When LUCA determines that an action is warranted (sending a reminder, flagging an escalation, logging a note), it:
1. Generates the action inline within its response
2. Executes it automatically
3. Confirms the execution in the chat: *"Action executed — REMINDER / Emily Archer"*
4. Logs the record to `luca_actions.json`
5. Updates the playbook in `luca_playbook.json`

**This is by design.** LUCA is not a tool that waits for an administrator to approve each communication. It is a system that acts, communicates with the team, and reports back. Actions are always logged and auditable.

### Playbook / Reinforcement Learning
Every executed action is recorded in `luca_actions.json`. Luca maintains a **playbook** (`luca_playbook.json`) tracking patterns by employee and issue type: how many times an issue has occurred, what actions were taken, and what the outcomes were.

On future audits, Luca references this history: *"I've sent two reminders to Emily about missing notes — both resolved within a day. Recommend the same."*

To record an outcome, tell Luca in chat: *"Mark the reminder to Emily as resolved"* or *"Log that this was escalated to management."*

---

## AI Models

| Role | Provider | Model |
|---|---|---|
| **Primary** | Anthropic (Claude) | `claude-opus-4-6` |
| **Secondary fallback** | Google (Gemini) | `gemini-2.0-flash` |
| **Tertiary fallback** | Local (Qwen via Ollama) | `qwen2.5:7b` *(planned)* |
| **Offline fallback** | Rule-based Python logic | No AI required *(planned)* |

Fallback is automatic — if Claude is overloaded or unavailable, the request is retried with Gemini transparently.

---

## Backend Data Sync *(Admin only — roadmap)*

Project, phase, and activity data are kept current automatically from Ajera. No employee or supervisor has access to sync controls — this is an Admin-only backend function.

| Data | Source | Frequency |
|---|---|---|
| Employee roster | `ListEmployees` | Daily, 5:50 AM |
| Projects | `ListProjects` | Daily |
| Phases | `GetProjects` | Daily |
| Activity codes | `ListActivities` | Daily |
| Companies / Departments | `ListCompanies` + `ListDepartments` | Weekly |
| Timesheet history (10 wks) | `Timesheet/List` + `Timesheet/Detail` | On every Sync Data and every Audit run |

Cached to `~/Documents/Luca/ajera_cache.json`. Stale after **24 hours**.

---

## Firm Structure

| Company | Department | Studio |
|---|---|---|
| Carlton Architecture PA | Asheville | Asheville |
| Carlton Edwards PLLC | Nashville | Nashville |
| Carlton Edwards PLLC | Memphis | Memphis |
| — | Consultant | (excluded from studio filter) |

---

## Configuration Files

All config and output files are stored in `~/Documents/Luca/`.

| File | Purpose |
|---|---|
| `ajera_cache.json` | Local Ajera data cache — employees, projects, phases, activities, 10 weeks of timesheets |
| `luca_session.json` | Persisted chat session — conversation history, audit context, last audit period |
| `luca_config.json` | Anthropic API key (auto-created on first Ask Luca use) |
| `luca_reference.json` | Firm reference: overhead codes, per-employee hour targets, billable target % |
| `luca_actions.json` | Running log of all actions executed |
| `luca_playbook.json` | Learned patterns: issue frequency, action types, outcomes |
| `audit_YYYY-MM-DD.html` | HTML report for each audit start date |

### luca_reference.json
Auto-created on first run. Edit in any text editor to customize:

```json
{
  "overhead_codes": {
    "General": "Non-billable general overhead",
    "PTO": "Paid time off — no note required"
  },
  "employee_weekly_hours": {
    "Gordon Shisler": 32.0
  },
  "billable_target_pct": 75
}
```

---

## API Connection

- **System:** Deltek Ajera
- **Endpoint:** `https://ajera.com/V004613/AjeraAPI.ashx`
- **API User:** ClaudeTime247 (read-only)
- **Auth:** Ajera session token (v1 for employees / org / projects; v2 for timesheets)
- **Payroll week:** Saturday–Friday (TimesheetDate = Friday; D1=Sat, D7=Fri)
- **Live fetch:** Timesheets for the audit period (reference data served from cache)

### Available API Methods

| Method | API Version | Returns |
|---|---|---|
| `ListEmployees` | v1 | EmployeeKey, name |
| `ListProjects` | v1 | ProjectKey, ID, description |
| `GetProjects` | v1 | Full project detail + phases (PhaseKey, ID, description) |
| `ListActivities` | v1 | ActivityKey, description |
| `ListCompanies` | v1 | CompanyKey, description |
| `ListDepartments` | v1 | DepartmentKey, name |
| `Timesheet/List` | v2 | All time entries for a date range |
| `Timesheet/Detail` | v2 | Full entry detail for a list of timesheet keys |

---

## Troubleshooting

**Timeout on monthly reports** — The app batches requests in groups of 10 with a 90-second timeout. Try again; it usually succeeds on retry.

**No timesheets found** — Ajera keys timesheets to the Friday end-of-week. Querying a mid-week date alone returns nothing; the app automatically adjusts to the containing week.

**Open Report button disabled** — Run an audit first. The button activates after the first successful run.

**Print opens browser but doesn't print** — Click the **Print** button in the top-right of the HTML report, or press Ctrl+P in the browser.

**Ask Luca says "API key required"** — Paste your Anthropic API key in the Credentials section of the sidebar. Keys are saved locally and only ever sent to Anthropic's API.

**"Invalid format string" error on audit** — Update to the latest `Luca.exe`. This was a Windows-specific `strftime` bug fixed in March 2026.

**Chat session lost after restart** — Session is auto-saved on close to `luca_session.json`. If the file is missing or corrupt, the session starts fresh.

---

## Application Files

| File | Purpose |
|---|---|
| `audit_gui.py` | Complete source — GUI, chat, audit engine, cache, session persistence |
| `luca_daily.py` | Headless daily automation — audit + notifications (GitHub Actions) |
| `timesheet_audit.py` | Original single-file CLI audit prototype |
| `raw_data_dump.py` | Utility — exports raw Ajera timesheet fields to CSV |
| `dist/Luca.exe` | Standalone Windows executable (no Python required) |
| `luca_logo.png` | Polyhedron logo source image (Luca Pacioli / Leonardo da Vinci) |
| `audit_icon.ico` | Windows icon — black polyhedron on white, 6 sizes (16–256px) |
| `make_icon.py` | Regenerates `audit_icon.ico` from `luca_logo.png` |
| `luca.spec` | PyInstaller build spec |
| `build_luca.bat` | One-click build script |
| `.github/workflows/luca_daily.yml` | GitHub Actions cron schedule — 6 AM Eastern, weekdays |
| `APPGUIDE.md` | This document |
| `APPGUIDE.html` | User-facing HTML guide (bundled with Luca.exe) |
| `LUCA.md` | Firm-specific config: managers, HR, escalation rules, notification settings |
| `luca_knowledge.yaml` | Business rules, phase definitions, billing confusion patterns |

---

## Design

The Luca interface uses a **black, white, and warm bronze** palette with **Segoe UI** (GUI, 11–18px range; chat body and inputs at 16px) and **Inter** (HTML reports) — clean, screen-optimized typography in the spirit of Anthropic's design language. Built with `customtkinter` for a modern native Windows feel.

The polyhedron mark in the header, taskbar, and desktop icon is taken directly from Leonardo da Vinci's illustration for Luca Pacioli's *De Divina Proportione* — black lines on white, rendered at 6 sizes for crisp display at every scale.

---

## Architecture Principle — LLM for Reasoning Only

All data fetching, aggregation, counting, flag detection, cache management, and lookups are deterministic Python code. The LLM (Claude / Gemini) is only invoked for tasks that require reasoning, narrative generation, or natural-language interpretation:

- Writing personalized daily review messages
- Generating supervisor report narratives
- Answering freeform chat questions that require judgment
- Detecting action opportunities in conversation context

This separation ensures reliable, repeatable audit results regardless of LLM availability or model behavior.

---

## Source Repository

**GitHub:** `github.com/robcarlton007/TimeAuditInvoicePrep` (private)

---

*Luca — Built for Carlton Edwards with Claude · Anthropic · March 2026*
