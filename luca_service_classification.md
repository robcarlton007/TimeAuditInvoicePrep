# Service Classification Guide
### Luca — Carlton Edwards Intelligence
*Work-in-progress reference for reasoning about time entry classification.*

> **This file is a reasoning aid, not a source of truth.** It is derived from the firm's
> working reference spreadsheet, Ajera project structures, and ongoing conversations
> about how time should be classified. It will be refined as edge cases are documented.
>
> Spreadsheet source: [Interior Design vs. Construction Services](https://docs.google.com/spreadsheets/d/1TzZ-rdSHM3No1GaaVKnZ9i6zFyuFSrdLLw8N1NxZ00Q)

---

## Project Types in Ajera

Every project in Ajera is one of four types. The type determines which phases are available and what kind of time can be entered.

### 1. Full-Service Architecture Project

> *Example: 24.04 — Dirx Residence*

A complete architecture engagement that may include every service the firm offers. This is the most comprehensive project type — it covers design through construction administration, plus interior architecture, furnishings, landscape, and additional services.

**Ajera phases (in order of typical project timeline):**

| Phase | Description |
|---|---|
| **Pre-Design & Schematic Design** | Programming, site analysis, feasibility, zoning research. Then: preliminary design direction — massing, space planning, adjacencies, concept development. Client presentations and approval of design concept. Typical deliverables: site plan, floor plans, elevations, 3D massing studies. |
| **Design Development** | Refining and coordinating the approved schematic design. All building systems (structural, mechanical, electrical, plumbing) are coordinated and sized. Preliminary material and finish selections. Door, window, and hardware schedules. Energy code compliance. Updated cost estimate. |
| **Construction Documents** | Producing full permit-ready and bid-ready construction documents. Complete drawings and specifications. Permit submission and responses to plan review comments. Bidding assistance and addenda. |
| **Construction Administration** | The architect's role during construction. Site observation visits and field reports, submittal review (shop drawings, product data, samples), RFI responses, change order review, pay application review, substantial completion inspection, punch list, and project closeout. This is the architect's oversight — not hands-on construction management. |
| **Interior Architecture, Fixtures and Finishes** | All interior-specific design work: finish selections, material specifications, fixture selections, tile layouts, paint schedules, millwork design, interior elevations, lighting design. This is where the specifics of the interior environment are defined — as distinct from the generic architectural definition of the space. |
| **Furnishings - Design & Selections** | Selection and specification of furniture, FF&E. Identification of products and finishes, cost analysis, client presentations of furniture options, vendor evaluation. Design intent — what the furniture should be. |
| **Furnishings - Procurement** | Ordering, purchasing, and tracking furniture after selections are approved. Vendor coordination, purchase orders, order verification (does the order match the design intent, the desired finish, the correct products?), payment, and handoff. |
| **Furnishings - Installation** | Receiving, coordinating delivery, placement, and oversight of furniture installation. Review of items on arrival, damage inspection, final placement, and punch. |
| **Art Selections & Coordination** | Selection, procurement, and placement of artwork. Often overlaps with interior architecture and furnishings but billed separately when it is a distinct scope. |
| **Landscape Design** | Site design, planting plans, hardscape, irrigation. Separate scope from the building architecture. |
| **Additional Services** | Work outside the original contract scope. Typically redesign work, cost reduction exercises, scope changes requested by the owner after design approval. Each additional service should be named descriptively (e.g., "Redesign, 10/2025, Cost Reduction"). |
| **Reimbursables** | Pass-through expenses: printing, travel, shipping, permits. Not labor — no design time should be entered here. |

---

### 2. Interior Architecture Project (no base architecture)

> *Example: 24.18 — Saputo Lot 1109*

A project where the firm is providing interior architecture and furnishings services but is **not** the architect of record for the building. The base architecture phases (Pre-Design, SD, DD, CD) are absent. The client may have a separate architect, or the building may already exist.

**Ajera phases:**

| Phase | Description |
|---|---|
| **Interior Architecture, Fixtures and Finishes** | Same scope as on a full-service project: finish selections, material specifications, fixture selections, tile layouts, paint schedules, millwork, interior elevations, lighting. This is the primary phase where most time is logged. |
| **Construction Administration** | The interior architect's oversight role during construction — but scoped to interior work only. Review of finish samples and shop drawings, verification that installed finishes match design intent, field observation of interior conditions. |
| **Furnishings - Design & Selections** | Same as full-service: furniture and FF&E selection and specification. |
| **Furnishings - Procurement** | Same as full-service: ordering, purchasing, tracking, vendor coordination. |
| **Furnishings - Installation** | Same as full-service: delivery coordination, placement, punch. |
| **Art Selections & Coordination** | Same as full-service: artwork selection and placement. |
| **Reimbursables** | Pass-through expenses only. No labor. |

**Key distinction from full-service:** There are no Pre-Design, SD, DD, or CD phases. If an employee's note describes building-level design work (structural, envelope, site), it does not belong on this project type.

---

### 3. Furnishings Project (product only — no labor)

> *Example: 24.19.1 — Saputo 1110 Furnishing Inv. 001*

A project established purely for tracking **product costs** — furniture purchases, freight, sales tax, and reimbursables. This is an accounting vehicle for pass-through product billing.

**Ajera phases:**

| Phase | Description |
|---|---|
| **Furnishings Expense - Invoice XXX** | The cost of the furniture products themselves. |
| **Freight - Invoice XXX** | Shipping and delivery charges for the products. |
| **Sales Tax - XXX** | Tax on the products. |
| **Reimbursables - XXX** | Any other pass-through costs. |

**Critical rule: No time should be entered to furnishings product projects.** These projects exist only for expense tracking and client invoicing of products. Any labor (design time, procurement time, installation oversight) belongs on the parent project's Furnishings phases, not here.

If Luca sees time entries on a furnishings product project, flag it immediately — it is always an error.

---

### 4. CEC Construction Project

> *Example: 2025.09 — CEC - Dirx Residence*

A Carlton Edwards Construction project for construction management and owner's representative services. CEC projects exist when the firm is both designing and building — this project captures the **intercompany billing** between the design entity (Carlton Architecture PA or Carlton Edwards PLLC) and the construction entity (Carlton Edwards Construction).

CEC projects are for circumstances where the design team may be doing work **on behalf of the construction company** related to that project.

**Ajera phases:**

| Phase | Description |
|---|---|
| **Project Management** | Overall construction project oversight: schedule management, budget tracking, contractor coordination, owner-contractor meetings, reporting. The owner's representative role. |
| **Site Coordination** | On-site presence: field observation, contractor coordination on-site, quality oversight, logistics, deliveries, receiving materials, verifying installation work. |
| **Estimating** | Cost estimating, budget development, control estimates, value engineering. Producing and maintaining the construction budget. |
| **Procurement** | Negotiation of contracts, scopes of work for subcontractors and suppliers, purchase orders, change orders, vendor management, material ordering and tracking. |
| **Design Coordination** | Work the design team does on behalf of the construction company — coordinating design changes during construction, resolving field conflicts, answering contractor questions that require design input. This is the bridge between the architecture project and the CEC project. |
| **Warranty** | Post-completion warranty work: defective item processing, warranty claims, manufacturer coordination, warranty binder compilation. |

**Key distinction:** CEC phases describe construction-side activities. If the note describes design work (selecting finishes, drawing, specifying materials), it belongs on the architecture or interior architecture project — not the CEC project. The CEC prefix is the definitive signal.

---

## How the Same Client Can Have Multiple Projects

A single client engagement may generate **multiple simultaneous projects** in Ajera:

| Project | Example | What it covers |
|---|---|---|
| Architecture project | 24.04 Dirx Residence | All design labor — architecture, interiors, furnishings |
| CEC project | 2025.09 CEC - Dirx Residence | Construction management labor — intercompany billing |
| Furnishings product project | (e.g., Dirx Furnishing Inv. 001) | Product costs only — no labor |

Employees must code their time to the correct project based on **what they were doing**, not just the client name.

---

## The Four Service Categories

Beyond project types, every activity falls into one of four service categories. These categories map to phases within projects.

| Category | What it is | Where to code it |
|---|---|---|
| **Interior Architecture** | Interior specs, selections, and their application to the architecture — finishes, materials, fixtures, layouts, interior details | "Interior Architecture, Fixtures and Finishes" phase |
| **Architecture** | Structural, framework, building — generic definition of spaces and generic finishes | Pre-Design/SD, DD, CD, or CA phases |
| **CEC (Construction Services)** | Construction management, procurement, contractor coordination, owner's representative | CEC project phases (PM, Site Coord, Estimating, Procurement, Design Coord, Warranty) |
| **Furnishings** | Furniture selection, procurement, and installation — FF&E as a standalone scope | Furnishings - Design & Selections, Procurement, or Installation phases |

### Interior Architecture vs. Architecture — The Distinction

> *Example: (ARCH) Generic tile hatch vs. (IA) specific tile layout and placing jollys*

- **Architecture** defines the space generically — dimensions, structure, systems, generic finishes
- **Interior Architecture** defines the specifics within that space — which tile, which finish, which fixture, which material, and exactly how it's applied

When both scopes exist on the same project, an employee's note determines which phase the work belongs to. Generic drawings = Architecture phases. Specific product selection, finish specification, or material coordination = Interior Architecture phase.

---

## CEC Workflow Activities

CEC activities are fundamentally different from design activities. They center on procurement, logistics, financial tracking, and contractor management.

| Category | Activities |
|---|---|
| **Correspondence** | Anything associated with the CEC items below |
| **Procurement** | Negotiation of contracts, scopes of work (labor for: cabinets, low voltage, plaster, countertops, upholstery, window treatments, closets) |
| **Purchase Order** | Writing, distributing |
| **Change Order** | Writing, distributing, reviewing, value engineering |
| **Shipping** | Coordination of a delivery (logistics) |
| **Handling** | Accepting receipt of materials, correspondence associated, receiving |
| **Budget Tracking** | Creating, entering info, maintaining (data entry), control estimate entering |
| **Client Invoicing** | Reviewing of invoicing |
| **Sub-contractor Invoices** | Coding, reviewing of invoicing |
| **Payment** | Inquiring about a payment, responding to an outstanding payment, establishing payment terms |
| **Project Management** | Project management meetings, schedules and task lists review |
| **Co-Construct** | Job log updates, schedule updates |

---

## Interior Architecture Workflow Activities

The sequential phases of interior architecture work within a project:

| Category | Activities |
|---|---|
| **01 Selection** | Identification of products, identification of finishes, identifying product costs, selecting a product, analyzing pros/cons of selections (including price), verify availability |
| **02 Client Management** | Collecting material samples, presentation boards, client meetings, client approvals |
| **03 Documentation** | Drawings (creating, revising, updating), schedules (creating, revising, updating), specification of products and descriptions, project manual management |
| **04 Interior Procurement** | Selecting a vendor, verification that order matches design intent, verification order matches desired finish, verification order includes correct products, purchase (initial payment), handoff |
| **05 Interior Administration** | Construction admin associated with interiors, review of finish samples, review of shop drawings for design intent, review of technical drawings, task lists management, project management meetings representing interiors, warranty binder preparation |

---

## Product / Material Responsibility Matrix

This is the critical split: **who is responsible for what product or material?** The same physical item may be touched by Interior Architecture (spec & finish) and CEC (procurement & installation). Getting the project code wrong here is the most common billing error.

### Split Items — Highest Confusion Risk

These materials are **split** between Interior Architecture and CEC. Both entities touch them, but the *nature of the work* determines which project code to use.

| Material | Interior Architecture (spec & finish) | CEC (procurement & installation) |
|---|---|---|
| **Cabinetry** | Door style, details, finish, shop drawing review | Generically draw, dimension; procurement, installation labor |
| **Countertops** | Material and finish, shop drawing review | Generically draw, dimension; procurement, installation labor |
| **Wood Flooring** | Spec and finishes only | Everything but finishes and specs |
| **Wood Paneling** | Spec and finishes only | Everything but finishes and specs |
| **Wood Ceilings** | Spec and finishes only | Everything but finishes and specs |
| **Plaster** | Product, color, texture, locations | Procurement, everything but finishes and specs |
| **Appliances** | Specs, selections, and integration | Procurement |
| **Arch Grille** | Style/type, finish, shop drawing review | Stock sizes, procurement, purchasing |
| **Interior Doors** | Finish and design | Finish only (CEC on casework projects) |
| **Window Treatment** | Decorative fabrics and design | Integrated |

### Interior Architecture Exclusively Owns

Tile (material, grout, accessories, layouts) · Plumbing fixtures (except hosebib) · Lighting fixtures (integrated and decorative) · Door hardware (excludes pocket door tracks) · Wall coverings and wall paper · Paint (product, color, texture, locations, finish, schedule) · Low voltage equipment approval

### CEC Exclusively Owns

Concrete · Masonry · Steel · Wood (structural) · Decking · Siding · Soffits · Pocket door tracks · Ditra heat · Attic access panels

---

## Classification Decision Rules

When Luca evaluates a timesheet entry, apply these rules in order:

### Rule 1: Check the project type
- **CEC prefix** → CEC project. The note must describe CEC-type activities. If it describes design work, flag as potential miscoding.
- **Furnishings product project** (has "Inv." or "Invoice" in name, phases are expense/freight/tax) → **No time should be entered.** Flag immediately.
- **No CEC prefix, has architecture phases** → Full-service architecture project. Proceed to Rule 2.
- **No CEC prefix, no architecture phases** → Interior Architecture project. Proceed to Rule 2.

### Rule 2: Check the phase
- Is the entry on the correct phase for the work described?
- Architecture phases (Pre-Design/SD, DD, CD, CA) → note should describe building-level work
- Interior Architecture phase → note should describe interior-specific selections, finishes, fixtures
- Furnishings phases → note should describe furniture/FF&E work
- If the note describes a different type of work than the phase implies, flag for review

### Rule 3: What does the note describe?
- **Structural, framework, building envelope, generic space definition** → Architecture phases
- **Specific materials, finishes, fixtures, selections, interior details** → Interior Architecture phase
- **Furniture products, FF&E, furniture procurement/installation** → Furnishings phases
- **Contractor coordination, procurement, logistics, payments, scheduling** → CEC project

### Rule 4: Check split materials
If the note references a specific material from the split items table:
- **Spec/finish** verbs (selected, specified, reviewed finish, chose color) → Interior Architecture
- **Procurement/installation** verbs (ordered, received, installed, tracked shipment, paid vendor) → CEC

### Rule 5: Ambiguous entries
Some activities legitimately span categories:
- "Client meeting" can occur in any service type — the project and phase determine the billing
- "Review" depends on what is being reviewed — submittals (CA), finishes (IA), invoices (CEC)
- "Coordination" depends on who — consultants (Arch), vendors (IA/CEC), contractors (CEC)

When the note is too vague to classify, flag for review rather than guessing.

---

## Common Confusion Patterns

### 1. Interior Architecture work coded to CEC (or vice versa)
**Most common error.** Employee selects tile finishes (Interior Architecture) but codes to the CEC project because the client is the same. The CEC prefix is the definitive indicator — if the project says CEC, only CEC activities belong there.

### 2. Time entered on a Furnishings product project
Furnishings product projects (with expense/freight/tax phases) are for product costs only. Any labor — design, procurement, installation oversight — belongs on the parent project's Furnishings phases.

### 3. CEC procurement coded to Interior Architecture
Employee orders materials or coordinates with a vendor (CEC procurement activity) but codes it to the architecture project because they were selecting the product earlier in the same week.

### 4. Furnishings coded to Interior Architecture phase
Furniture procurement and installation are separate from interior architecture finish work. If the note describes furniture products specifically (not built-in architectural elements), it belongs in the Furnishings phases.

### 5. Interior Administration confused with Construction Administration
"Interior Administration" (within IA scope) covers review of finish samples and shop drawings for design intent. "Construction Administration" (CA phase) is the architect's oversight role during construction. They overlap but bill to different phases.

### 6. Design work coded to CEC Design Coordination
The CEC "Design Coordination" phase is for design work done **on behalf of the construction company** — resolving field conflicts, answering contractor questions. It is not for original design work, which belongs on the architecture project.

### 7. Split materials billed to wrong entity
Wood flooring specs and finishes = Interior Architecture. Wood flooring installation and everything else = CEC. The same physical material, two different project codes depending on whether you're specifying it or installing it.

---

## Scopes of Work — CSI Division Phase Matrix

For specific CSI divisions, this maps which phase handles each task. Phase codes: **X** (applicable), **KR** (key responsibility), **KR/MLI** (lead with shared input), **KR/MB** (lead with shared input), **MLI** (supporting role), **N/A** (not applicable).

### 05 52 00 — Ornamental Railings
| Task | Arch | Int. Arch | Furnishings | Construction |
|---|---|---|---|---|
| Design - Concept | X | | | |
| Finishes | X | | | |
| Review | X | X | | |
| Drawings | KR | | | |
| Sample Review | KR/MLI | X | | |
| Specifications/QC | KR/MB | | | |
| Shop drawing review | KR | | | |

### 06 22 00 — Wall Finishes
| Task | Arch | Int. Arch | Furnishings | Construction |
|---|---|---|---|---|
| Selections | X | | | |
| Review | X | X | | |
| Schedules/Cutsheets | N/A | N/A | | |
| Drawings | X | | | |
| Sample Review | MLI | X | | |
| Specifications/QC | KR/MB | | | |

### 06 22 00 — Ceiling Finishes
| Task | Arch | Int. Arch | Furnishings | Construction |
|---|---|---|---|---|
| Selections | KR/MLI | | | |
| Review | KR/MLI | X | | |
| Schedules/Cutsheets | N/A | N/A | | |
| Drawings | X | | | |
| Sample Review | MLI | X | | |
| Specifications/QC | KR/MB | | | |

### 06 22 00 — Millwork (Interior Trim)
| Task | Arch | Int. Arch | Furnishings | Construction |
|---|---|---|---|---|
| Selections | X | | | |
| Review | X | X | | |
| Drawings | X | | | |
| Sample Review | N/A | N/A | | |
| Specifications/QC | X | | | |
| Shop drawing review | N/A | N/A | | |

### 06 43 00 — Stair Systems
| Task | Arch | Int. Arch | Furnishings | Construction |
|---|---|---|---|---|
| Design | X | | | |
| Review | X | X | | |
| Drawings | KR | | | |
| Sample Review | MLI | X | | |
| Specifications/QC | KR/MB | | | |
| Shop drawing review | KR | | | |

### 06 44 00 — Fireplace Mantles
*(Phase assignments not yet defined.)*

### 08 14 00 — Interior Doors
| Task | Arch | Int. Arch | Furnishings | Construction |
|---|---|---|---|---|
| Selections - Slab Style, Material | X | | | |
| Finishes | X | | | |
| Review | X | X | | |

---

*luca_service_classification.md — Carlton Edwards service type reasoning guide · March 2026*
*Sources: Ajera project structures, "Interior Design vs. Construction Services" Google Sheet*
