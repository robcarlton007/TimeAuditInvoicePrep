# LUCA.md
### Firm Configuration — Carlton Edwards
*Items in this file are firm-specific and cannot be sourced from the Ajera API.*
*The Ajera API is always the primary source for any data it provides (employees, roles, projects, phases, activities, departments, companies).*

---

## Managers / Supervisors

| Name | Studio | Company |
|---|---|---|
| Rob Carlton | Asheville | Carlton Architecture PA |
| Matt Zink | Nashville | Carlton Edwards PLLC |
| Jeff Edwards | Memphis | Carlton Edwards PLLC |

> **Source note:** Employee roles and department assignments should be pulled from Ajera first. This table is the override/supplement only for supervisory relationships not captured in Ajera.

---

## HR Contact

| Role | Name | Organization | Email |
|---|---|---|---|
| HR Manager | Kim Dierking | Craft HR Consultants | hr@carlton-edwards.com |

---

## Access Roles

Three access tiers are defined for Luca. All role data is sourced directly from **Ajera `GetEmployees`** — no separate role store needed.

| Tier | Ajera Field | Who | Access |
|---|---|---|---|
| **Admin** | `IsPrincipal = true` | Rob Carlton (and any other principals) | Full — all studios, backend sync, config, user management, all notifications |
| **Supervisor** | `IsSupervisor = true` | Matt Zink, Jeff Edwards, Rob Carlton | Their studio's reports, escalation notifications, team timesheets |
| **Employee** | All others | All other staff | Their own timesheet data only |

### Supervisor Routing via Ajera
`GetEmployees` returns a `SupervisorKey` field for each employee — the EmployeeKey of their direct supervisor. Luca uses this to:
- Route notifications to the correct supervisor automatically
- Build studio-scoped reports without hardcoded lists
- Handle org changes without any Luca config updates — changes in Ajera propagate automatically

> **No manual employee-to-supervisor mapping is needed in this file.** The table above (Managers section) is kept only as a human-readable reference.

---

## Notification System

Luca delivers notifications via two channels:

| Channel | Method | Used for |
|---|---|---|
| **Email** | Gmail (firm account) | All formal notifications — reminders, escalations, supervisor reports |
| **WhatsApp** | WhatsApp Business API | Lightweight nudges — same-day reminders, quick alerts |

> **Gmail:** SMTP with app password (generated once in Google Account → Security → App Passwords). Stored as a GitHub Secret. No OAuth2 complexity.
> **WhatsApp:** Twilio (twilio.com). Wraps Meta's Business API — one REST call, no webhook setup. ~$15-20/month at this volume.
> Employee email and phone are pulled directly from Ajera `GetEmployees` — no separate contact list. Label a phone field "Mobile" or "WhatsApp" in Ajera and Luca uses it automatically.

---

## Daily Review — AI-Generated Personal Messages

### Philosophy
The daily review is **not** a scripted notification system. There are no static templates. Every message is written fresh by Claude each morning, addressed personally to the employee, and grounded in the specific details of their prior day's work.

The message reads like it came from a knowledgeable colleague who looked at your timesheet and has something genuinely useful to say — not a system alerting you that a rule was broken.

### What the message covers
It is an **analysis**, not a checklist. A message may touch on:
- Missing notes on specific project entries (and which projects — and why it matters for invoicing)
- Hours that look incomplete — and how the week is trending relative to their target
- Overhead-heavy days and whether that's a pattern
- Collaborative entries where a team member's record doesn't align
- Positive acknowledgment when things look right
- A running thread — if the same issue appeared last week, Luca notices

### What makes it fresh every day
Claude receives the employee's data and a directive to write a novel message. No two messages share the same opening. The framing varies — some days it leads with what's going well, some days it leads with the most time-sensitive issue. The day of the week, the employee's weekly trajectory, and any notable patterns in their recent history all inform the tone and content.

Luca never says *"This is a reminder that you have not completed your timesheet."*
Luca might say: *"Tuesday looks mostly solid — Greenway Park and the Riverfront entries are clean. One thing to flag: three entries are missing notes, and two of those are on billable phases that go to invoice Friday. Worth adding those today. You're at 22 hours through midweek, tracking just slightly behind your 40h target — nothing alarming yet."*

### Message generation context
Claude receives the following for each employee message:

| Context | Source |
|---|---|
| Employee name, role, studio, supervisor | Ajera `GetEmployees` |
| Prior day's full timesheet entries | Ajera `Timesheet/List` |
| Current week's running total | Ajera `Timesheet/List` |
| Prior 2–3 weeks of entries (pattern context) | Ajera `Timesheet/List` |
| All flags generated for the prior day | Luca audit engine |
| Action history for this employee | `luca_actions.json` |
| Day of week, week position | System date |
| Tone directive | Friendly, analytical, personal, novel — no canned openers |

### Escalation tiers — tone, not templates
Escalation still exists but Claude calibrates the tone based on severity. There is no canned escalation text.

| Tier | Condition | Tone directive to Claude | Recipients | Channels |
|---|---|---|---|---|
| **Tier 1** | 1 missed day | Warm, low-pressure, give benefit of the doubt | Employee + Supervisor (CC) | Email + WhatsApp |
| **Tier 2** | 2 consecutive missed days | Noticeably more direct, acknowledge the pattern | Employee + Supervisor (CC) | Email + WhatsApp |
| **Tier 3** | 3+ consecutive missed days | Serious, clear about consequences, still respectful | Employee + Supervisor + Kim Dierking (HR) | Email |

For Tier 2 and 3, Luca acknowledges the history: *"This is the second day in a row with no entries — I flagged the same thing yesterday..."* It does not pretend this is the first time.

### Supervisor daily report
The supervisor report is also AI-generated — not a table dump. Claude receives the full studio picture and writes an analytical brief: what's clean, what needs attention, where there are patterns forming across the team, and any cross-reference issues between collaborating employees.

Rob Carlton, Matt Zink, and Jeff Edwards each receive a report scoped to their studio only. Rob sees all three as Admin.

---

## Supervisor Report

Each supervisor receives a **comprehensive daily report** covering all staff under their supervision:

- Employees missing timesheets (with escalation tier)
- Incomplete hours (flagged days, shortfall)
- Entries without notes (project entries only)
- Collaborative work citations involving their team
- Cross-reference status: collaborative entries where both employees are logging correctly to the same project and phase

Reports are segmented — Matt Zink sees only Nashville, Jeff Edwards sees only Memphis, Rob Carlton sees Asheville (and can access all studios as Admin).

---

## Spelling / Typo Detection

Luca should flag potential misspellings or typos in timesheet entry notes. Detection approach:
- Run notes through a dictionary/spell-check pass
- Flag words that are not in a standard English dictionary AND not in the firm's known-terms list
- Known terms (project names, phase codes, proper nouns, acronyms) defined in the `known_terms` section below

### Known Terms (not to be flagged)
```
Ajera, PLLC, PA, SD, DD, CD, CA, IDP, RFI, RFP, OAC, BIM, Revit,
Carlton, Zink, Edwards, Asheville, Nashville, Memphis
```
> Add to this list as needed.

---

## Collaborative Work — Cross-Reference Rules

When Employee A's note mentions Employee B collaboratively:
1. Both employees must have entries for that date
2. Both entries should reference the same project
3. Both entries should reference the same phase (or a phase that makes sense in context)
4. Hour totals for that project on that date should be within a reasonable range of each other

**Flag if:**
- Mentioned employee has no entry that day
- Projects don't match
- Phases don't match
- Hours are wildly disproportionate (threshold: TBD — suggest 2× difference)

---

## Backend Data Sync (Admin Only)

The following Ajera data should be kept current in the background, accessible only to Admin users. No employee or supervisor has access to the sync controls.

| Data | Ajera Method | Sync frequency |
|---|---|---|
| Employee roster + keys | `ListEmployees` | Daily at 5:50 AM (before the 6 AM report) |
| Projects + ProjectKeys | `ListProjects` | Daily |
| Project phases + PhaseKeys | `GetProjects` | Daily |
| Activity codes + ActivityKeys | `ListActivities` | Daily |
| Companies | `ListCompanies` | Weekly |
| Departments | `ListDepartments` | Weekly |

Synced data is cached locally and used by the audit and notification engines. The cache is at `~/Documents/Luca/ajera_cache.json`.

---

## Scheduled Daily Tasks

| Time | Task |
|---|---|
| 5:50 AM | Backend sync — refresh employee, project, phase, activity data from Ajera |
| 6:00 AM | Pull prior day's timesheets → run audit → send notifications → deliver supervisor reports |
| 8:00 AM | Auto-update documentation (.md files) |

All times local (Eastern). Tasks run on a cloud server — see **Infrastructure** section below.

---

## Infrastructure — Daily Automation

### Decision: Cloud server, not local workstation
Local machines have too many failure modes (sleep, reboot, Windows Update, power loss). The daily 6 AM run must be uninterrupted.

### Recommended: GitHub Actions (free)
GitHub Actions provides a hosted scheduler that runs Python scripts in the cloud on a cron schedule. No server to provision, no maintenance, no cost at this volume.

**How it works:**
1. The Luca automation script (`luca_daily.py`) lives in the GitHub repository
2. A GitHub Actions workflow file (`.github/workflows/daily_run.yml`) schedules it via cron: `0 11 * * 1-5` (6 AM Eastern = 11 AM UTC, weekdays only)
3. GitHub runs the script in a cloud container — calls Ajera API, processes timesheets, sends Gmail and WhatsApp notifications, delivers supervisor reports
4. No machine at Carlton Edwards needs to be on

**Cost:** Free (GitHub Actions free tier = 2,000 minutes/month; this job runs ~2 min/day = ~44 min/month)

**Reliability:** GitHub's uptime is 99.9%+. Failure notifications go to the repo owner automatically.

### Alternative: DigitalOcean Droplet (~$6/month)
A small Linux VPS running a cron job. More control, but requires occasional maintenance (OS updates, monitoring). Reasonable fallback if GitHub Actions has any limitations.

### Not recommended
- Local Windows workstation → too many failure modes
- Windows Task Scheduler alone → only runs when machine is on and logged in

### Setup steps (to be done once)
- [ ] Create private GitHub repository and push current codebase
- [ ] Add secrets to GitHub repo: `AJERA_URL`, `AJERA_USER`, `AJERA_PASS`, `GMAIL_CREDENTIALS`, `WHATSAPP_TOKEN`, `ANTHROPIC_API_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- [x] ~~Write `luca_daily.py`~~ — headless audit + notification engine (complete)
- [x] ~~Create `.github/workflows/luca_daily.yml`~~ — cron: 6 AM Eastern, weekdays (complete)
- [ ] Test with manual trigger (`workflow_dispatch`) before enabling the live schedule
- [ ] Provision Twilio WhatsApp number
- [ ] Generate Gmail app password and add as `GMAIL_APP_PASSWORD` secret

---

## Local Memory Architecture

Luca maintains a local data layer so that core functions operate even when the Ajera API is unavailable. The API is always the primary source; local cache is the fallback.

### Cache file: `~/Documents/Luca/ajera_cache.json`
Refreshed on every **Sync Data** click and after every audit run. Also refreshed daily at 5:50 AM before the 6 AM automation. Contains:
- Employee roster (keys, names, departments, supervisors, roles, email, phone)
- Projects (ProjectKey, ID, description, status)
- Phases (PhaseKey, ID, description, per project)
- Activity codes
- Companies and departments
- **10 weeks of full timesheet history** (updated on every Sync and every Audit run)

If the API is unreachable, Luca uses the cache and notes its age. Reference data is considered stale after **24 hours**. Timesheets are always fetched live for the active audit period.

### Reference files (manually maintained, firm-specific)
| File | Contents |
|---|---|
| `luca_reference.json` | Overhead codes, per-employee hour targets, billable targets |
| `luca_knowledge.yaml` | Business rules, phase definitions, CEC distinction, scope evaluation, billing confusions |
| `luca_clients.json` | *(planned)* Client roster with project associations |
| `LUCA.md` | This file — firm config, managers, HR, escalation rules |

### Knowledge base: `luca_knowledge.yaml`
The firm's complete knowledge framework for timesheet and invoice evaluation. Covers:
- Entity definitions (Carlton Architecture PA, Carlton Edwards PLLC, CEC)
- Project naming conventions and the CEC prefix rule
- The three common billing confusions
- Phase definitions (what work belongs in SD, DD, CD, CA, ID, PM)
- Scope evaluation framework (how Luca decides if a note fits the phase)
- LLM provider strategy

---

## Login System *(roadmap)*

Three-tier access system. Employee identity is sourced from Ajera (`IsPrincipal`, `IsSupervisor`, `SupervisorKey`). Login credentials stored locally with hashed passwords.

| Tier | Access |
|---|---|
| **Admin** | All studios, backend sync, config, user management, all reports |
| **Supervisor** | Own studio only — team reports, escalation notifications |
| **Employee** | Own timesheet data only |

Login screen appears on app launch. Session persists until closed. Offline login uses the local employee cache if Ajera is unreachable.

---

## Business Rules — Excel to YAML Migration

The firm's existing billing rules (currently in Excel) should be converted to `luca_knowledge.yaml`. YAML is the right format because:
- Human-readable — anyone can edit it in Notepad
- Machine-parseable — Luca reads it directly as context
- Version-controllable — changes are tracked in git
- Structured — rules have categories, conditions, and examples

**How to migrate:**
1. Share the Excel file — I will convert each rule to a YAML entry under the appropriate section (`billing_confusions`, `phases`, `scope_evaluation`)
2. Rules with if/then logic become `flag_trigger` entries
3. Lists of acceptable vs. not-acceptable activities map directly to `typical_activities` / `NOT_typical`
4. Luca loads the full YAML into its context before every audit

---

## Items NOT Available from Ajera

The following firm-specific items must be maintained here because they are not available via the Ajera API:

- **Supervisor–employee relationships** (Ajera has department but not explicit reporting lines)
- **HR contact(s)**
- **Escalation tier rules and message templates**
- **Known terms / spell-check whitelist**
- **Access role tier assignments** (unless Ajera EmployeeType maps cleanly — to be verified)
- **Billable hour targets per employee** (if not in Ajera)
- **Notification delivery preferences** (email vs. Teams vs. both)

---

## Open Questions

- [x] ~~Does Ajera `EmployeeType` field map to Admin / Supervisor / Employee roles?~~ → Using `IsPrincipal`, `IsSupervisor`, and `SupervisorKey` from `GetEmployees` — no separate mapping needed.
- [x] ~~What is the HR contact?~~ → Kim Dierking, Craft HR Consultants, hr@carlton-edwards.com
- [x] ~~What notification system?~~ → Gmail (email) + WhatsApp
- [ ] Should supervisor reports be delivered by email, or viewable inside Luca, or both?
- [ ] Define message templates for Tier 1, 2, and 3 escalations.
- [ ] What is the hour-discrepancy threshold for collaborative cross-reference mismatch?
- [ ] Should employees have a login to Luca, or is it admin/supervisor-only?
- [x] ~~Should the 6 AM task require a server/always-on machine?~~ → GitHub Actions (cloud-hosted, free, zero maintenance). See Infrastructure section.
- [x] ~~Gmail — OAuth2 or app password?~~ → App password. Simpler, persistent, no token refresh needed.
- [x] ~~WhatsApp — Meta direct or Twilio?~~ → Twilio. 20-min setup, one REST call, Twilio handles Meta complexity.
- [ ] What Twilio WhatsApp number should outbound messages come from? (provision via twilio.com)
- [x] ~~Employee contacts — manual config or from Ajera?~~ → Pulled live from Ajera `GetEmployees`. `Email` field for email; phone labeled "Mobile" or "WhatsApp" in Ajera is auto-detected. No manual contact list needed — update in Ajera and Luca picks it up automatically.
- [x] ~~Should actions require admin approval?~~ → No. LUCA acts fully autonomously. Actions are detected in AI responses and executed immediately, then logged to `luca_actions.json`. No approval card or admin initiation required.

---

*LUCA.md — Carlton Edwards firm configuration · Last updated March 2026*
