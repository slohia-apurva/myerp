# Biometric attendance (spec, 7 Nov 2026)

Requested by Sidharth: bring punches from the biometric attendance devices into MyERP, so attendance feeds payroll (module 8a) without re-keying.

Status: spec only, for review. Nothing is built until Sidharth approves it. Open questions are at the end; the device brand and model decide part of the design.

## The problem in one line

The devices sit on the office or factory LAN, and MyERP runs on Cloud Run in Mumbai. Cloud Run cannot reach a device on a LAN, so **the device (or something next to it) must send punches out to MyERP**, never the other way round.

## How punches reach MyERP

Three routes, in order of preference. One tenant can use different routes at different sites.

| Route | How it works | Needs at the site | When to use |
| --- | --- | --- | --- |
| A. Device pushes (ADMS / "cloud server" mode) | Most current ZKTeco, eSSL and similar devices have a "Cloud server" or ADMS setting. We enter MyERP's address there, and the device sends each punch over the internet within seconds, and re-sends anything it held while offline | Internet on the device (LAN cable or Wi-Fi). Nothing else | Default for every device that supports it |
| B. Bridge on a site PC | A small MyERP Bridge program on any always-on PC at the site reads the devices over the LAN (the vendor SDK or the standard TCP protocol on port 4370) every few minutes and sends the punches to MyERP over HTTPS | One Windows or Linux PC that stays on | Older devices without push, or devices that can only do plain HTTP |
| C. Vendor's cloud | If the punches already go to the vendor's cloud software (e.g. eSSL eTimeTrack cloud, ZKBioTime), MyERP pulls them from its API on a schedule | A vendor subscription with API access | Only if a site already runs it and the vendor gives an API |

Notes on route A:

- The push protocol has no real login. MyERP accepts punches only from **registered device serial numbers**, checks the device's comm key where the firmware supports it, and rate-limits each device. An unknown serial number is logged and refused.
- Many older firmwares speak only plain HTTP, and Cloud Run serves HTTPS only. If the chosen model cannot do HTTPS, that site uses route B. We check this on the real device before building.
- MyERP answers each push with the server time, so device clocks stay correct (a drifting clock is the usual cause of wrong late marks).

## Which tenant and company a punch belongs to

MyERP is multi-tenant (decision 0003): each tenant has its own database. A device does not know about tenants, so:

- A small **platform-side device registry** maps each serial number to one tenant. A serial number can belong to only one tenant at a time.
- Inside the tenant, the **device master** says which company and branch the device stands at.
- The push endpoint looks up the serial number, then stores the punch inside `use_tenant(...)` for that tenant only.

## What is stored

Following design rule 1 (posted records are immutable):

| Record | Holds | Rules |
| --- | --- | --- |
| Device | Serial number, name, model, company, branch, route (A/B/C), last seen, active flag | Never deleted, only deactivated (same as ledgers) |
| Device user link | Device user ID (the number enrolled on the device) to employee, from a date | One employee keeps the same device ID on every device, so one person punching at two branches is one employee |
| Raw punch | Device, device user ID, punch time (IST), verify mode (finger, face, card, PIN), in/out key if pressed, received at, route | **Never edited or deleted.** Duplicates (same device, ID, time) are dropped on arrival. Punches from an ID not yet linked are kept and shown as "unmatched" until someone links the ID |
| Daily attendance | Employee, date, shift, first in, last out, hours worked, late by, early by, overtime, status (present, absent, half day, weekly off, holiday, leave, on duty) | Worked out from raw punches. Recalculated when late punches arrive (a device that was offline) until the month is locked |
| Correction (regularisation) | Employee, date, the time or status asked for, reason, requested by, approved by | The only way to change a day. The raw punches stay as they were; the day shows both |

## Masters that drive the daily calculation

All dated master data (design rule 14), per company or branch:

- **Shifts**: start, end, grace minutes, half-day and absent thresholds, break, overnight flag (for a shift that ends after midnight, punches are tied to the day the shift started).
- **Shift roster**: which employee works which shift from which date; rotating rosters later.
- **Weekly off** per employee or branch, and **holiday list** per branch per year (states differ).
- **Overtime rule**: from how many minutes after shift end, rounding, and whether it needs approval.
- **Leave types and balances**: built with payroll (8a); attendance shows a day as leave once a leave is approved.

## Month end and payroll

- The month's attendance summary (paid days, absent days, leave by type, approved overtime hours) is what the payroll run reads.
- When the month's payroll run is submitted, that month's attendance is **locked**. A correction after that goes into the next month as an arrear or deduction line, never into the locked month.

## Company modules

Per decision 0014 we add a module code **`attendance`** ("Attendance": devices, shifts, daily attendance, corrections).

- **Payroll needs Attendance** (payroll pays on attendance). Attendance can be on without payroll, for a company that only wants to track time.
- A device can only be placed at a branch of a company that has Attendance on. If a company switches it off, its devices stop being accepted (punches are refused and logged), and the screens hide.

## Screens

- **Devices**: list per company and branch, last seen, punches today, unmatched IDs, a "not heard from in 1 hour" flag.
- **Punches**: raw punches by date, device, employee; unmatched punches with a "link to employee" action.
- **Daily attendance**: a grid of employees by date for a month (P, A, HD, WO, H, L), with late and overtime shown; clicking a cell shows its punches and its corrections.
- **Corrections**: request, approve, reject.
- Layout B3 with the PageHeader band, like the other screens; every form's submit button says Save.

## Build order (one PR each, each after the previous is seen)

1. Device master, platform registry, and the push endpoint (route A) storing raw punches. Tested against a real device, or a recorded session from one.
2. A minimal employee master (name, code, company, branch, device ID), so punches can be linked. Payroll later adds the statutory fields to the same employee.
3. Shifts, weekly offs, holidays, and the daily attendance calculation with its tests (late, early, half day, overnight shift, missing out-punch).
4. The monthly attendance grid and corrections with approval.
5. The month-end summary and lock, ready for payroll.
6. The Bridge for route B, only if a site needs it.
7. Later: send new employees to the devices from MyERP (the push protocol lets the server send "add user" commands), so enrolment is done once.

Where this sits in the roadmap: the plan has attendance inside Payroll (Phase 8). Steps 1 to 4 do not depend on payroll and could be built earlier if Sidharth wants punches collected before then.

## Open questions for Sidharth

1. Device brand and model at each site (a photo of the model label or the "About" screen is enough). Do they use fingerprint, face or card?
2. How many sites (locations) and devices, and which company and branch is each at?
3. Does each device have internet (LAN cable or Wi-Fi), or only a local network?
4. Is any attendance software running today (e.g. eSSL eTimeTrackLite on a PC, or a vendor cloud)? Can we look at its settings?
5. Roughly how many employees punch, and are contract workers (through a labour contractor) on the same devices?
6. Any night shift or rotating shifts?
7. Do you want punches collected before payroll is built, or only with payroll in Phase 8?
