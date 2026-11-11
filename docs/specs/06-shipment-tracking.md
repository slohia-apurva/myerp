# Shipment (AWB) tracking and daily despatch email (spec, 10 Nov 2026)

Requested by Sidharth: "AWB tracking for sales to be updated daily into system and also consolidated email sent to concerned despatch" team.

Status: spec only, for review. Nothing is built until Sidharth approves it. It hangs off the sales delivery note (Phase 4), but the first steps can run earlier (see "Build order"). Open questions are at the end; which couriers Apurvam uses decides most of the integration work.

Update 11 Nov: Sidharth uses **Delhivery** and gave its PIN serviceability list (21,528 PINs with an ODA flag). It is loaded as a central table in the masters work (see "Courier serviceability by PIN" below), so Delhivery is the first carrier and the first connector. Other couriers' lists are added to the same table later.

## What it does, in one paragraph

Every sales consignment that leaves by courier, air cargo or transporter gets a **shipment** in MyERP with its AWB (or docket / LR) number. Once a day, and sooner where the carrier can push updates, MyERP fetches the latest status of every shipment that is not yet delivered and stores each tracking event. Each morning the despatch team gets **one consolidated email** per company (or per branch): what was delivered, what is out for delivery, what is stuck or coming back, and which deliveries left without an AWB. The same list is on a **Shipments** screen. Tracking never posts to the ledgers.

## Words used here

| Word | Meaning |
| --- | --- |
| AWB | Air waybill number. Couriers in India call their docket number an AWB too; airlines use an 11-digit AWB (3-digit airline prefix + 8 digits). Here "AWB" means any carrier's tracking number |
| LR | Lorry receipt from a road transporter (also a tracking number, usually without an API) |
| Carrier | The courier, airline, forwarder or transporter that carries the goods |
| Aggregator | A service that books and tracks with many carriers through one API (e.g. Shiprocket, ClickPost, AfterShip) |
| EDD | Expected delivery date given by the carrier |
| POD | Proof of delivery: delivered date and time, receiver's name, sometimes a signature or photo |
| RTO | Return to origin: the carrier could not deliver and is bringing the goods back |

## Courier serviceability by PIN

Asked by Sidharth (11 Nov): when a customer or supplier is added, show which courier can deliver to its PIN code.

- Two central (platform-side, read-only in each tenant) tables, built in the masters work: the **PIN list** (PIN, city, state) that fills address forms, and **courier serviceability** (courier, PIN, serviceable, ODA flag, the courier's centres), one row per courier per PIN. Delhivery's list is loaded first; each new courier's list is added beside it, never mixed into the PIN list.
- **Party and address forms** show, under the PIN, which couriers deliver there and whether it is **ODA** (out of delivery area, usually extra charge and slower).
- **Delivery note**: the carrier is suggested from the ship-to PIN (a courier that serves it, not ODA where possible), and a warning shows when the chosen courier does not serve that PIN or it is ODA.
- **Despatch email**: ODA shipments are marked, and their "past EDD" check allows the extra days.
- The courier in this table is the same record as the **Carrier** master below, so tracking and serviceability share one list of couriers.
- Lists go out of date; each courier's list keeps its "as of" date, is replaced when a new file or the courier's serviceability API gives a newer one, and the screen shows that date.

## Where it hooks into Sales

```
Sales order → pick list → delivery note ──→ shipment(s) ──→ tracking events (daily)
                                │                │
                                │                ├─→ delivered date → "on delivery" due date
                                │                └─→ RTO → draft sales return for a person to check
                                └─→ sales invoice / e-way bill (Part B takes the AWB or LR number)
```

- **Delivery note** (Phase 4) gets a **Shipments** section: carrier, mode, AWB, booked date, number of packages, weight. The weight and package count come from the item UOMs on the lines (roadmap: "Item units of measure").
- **One delivery note can have several AWBs** (a multi-piece consignment, or part goes by air and part by road). **One AWB can cover several delivery notes** for the same customer and address. The link is many to many.
- The AWB is entered on the desktop, or scanned from the carrier's label in the **Dispatch** workspace of the warehouse mobile app at the "Load" step (spec 05). A carrier's AWB format (length, check digit, prefix) is checked as it is typed or scanned.
- **E-way bill** (Phase 6a): Part B takes the transport document number and date; for a courier or air consignment that is the AWB, for road the LR. MyERP fills it from the shipment.
- **Credit terms** (decision 0019): a term part "On delivery" is due from the delivery date. When a shipment shows Delivered, MyERP fills the delivery note's **delivered date** from the POD, and the due date of that part follows from it. A person can correct it. This changes a due date on the bill, never a ledger entry.
- **RTO**: when a shipment turns to RTO, MyERP alerts the sales and despatch teams and makes a **draft sales return** against the delivery note for a person to check and submit when the goods arrive back (AI and automation make drafts only, decision 0006).
- **Exports** (spec 03): the export file's "Shipment" part (BL or AWB, flight) uses the same shipment record, so export AWBs are tracked the same way. **Imports and purchase** receipts can use it later for inbound tracking.

## How statuses reach MyERP

Cloud Run can call out to any carrier or aggregator on the internet, so here (unlike attendance) MyERP pulls. Three routes; each carrier account picks one.

| Route | How it works | Covers | Notes |
| --- | --- | --- | --- |
| A. Aggregator | One API for many carriers. MyERP registers each AWB with the aggregator; the aggregator sends a **webhook** on every status change, and MyERP also asks it once a day | Most Indian couriers (Blue Dart, Delhivery, DTDC, Ekart, Xpressbees, Shadowfax, Ecom Express, India Post) through one contract | Least work for us; a monthly fee per shipment or per plan. Some aggregators (Shiprocket, NimbusPost) also **book** the shipment and print the label, which gives the AWB without typing it |
| B. Carrier's own API | MyERP calls the carrier's tracking API with our business account's key (e.g. Blue Dart, Delhivery, DTDC give an API to contract customers) | Only shipments booked on our own account with that carrier | No middleman fee; one connector to build and keep up per carrier |
| C. No API (typed in) | The despatch team updates the status by hand from the carrier's website, or MyERP opens the carrier's tracking page from a link built from the AWB | Small transporters, LRs, airlines without an API | Still listed in the daily email (as "update by hand"), so nothing is forgotten |

Air cargo (airline AWBs, usually booked through a forwarder) is tracked through a cargo-tracking service that reads airline AWBs by their prefix, or through the forwarder's own updates (route C) when volumes are small.

Which services are used, their prices and API terms are confirmed once we know the carriers (open question 1). No carrier or aggregator is fixed in code: each is a **connector** chosen per carrier account, and adding one is data plus a small adapter, never tenant-specific code.

### Carrier statuses mapped to one list

Every carrier uses its own words. Each connector maps them to one **MyERP status**, and keeps the carrier's own code and text beside it:

| MyERP status | Meaning | Shipment is |
| --- | --- | --- |
| Booked | AWB made, not picked up yet | Open |
| Picked up | Carrier has it | Open |
| In transit | Moving between hubs | Open |
| Out for delivery | With the delivery person today | Open |
| Delivery failed | Attempted, not delivered (customer away, address problem, refused) | Open, needs action |
| Held | Held by the carrier (documents, e-way bill, payment, damage) | Open, needs action |
| RTO | Being returned to us | Open, needs action |
| Delivered | POD received | Closed |
| RTO delivered | Back with us | Closed |
| Lost or damaged | Declared by the carrier | Closed, claim to follow |
| Cancelled | Booking cancelled before pickup | Closed |

A carrier code MyERP has not seen before is stored as **Unknown** and shown in the email, so a new code is mapped once and not missed.

## What is stored

Following design rule 1 (posted records are immutable), the raw events are never edited.

| Record | Holds | Rules |
| --- | --- | --- |
| Carrier (global master) | Name, kind (courier, airline, forwarder, transporter), AWB format (pattern, check digit, airline prefix), tracking page link pattern, connectors that support it | Maintained once on the platform side, synced read-only into each tenant (like HSN codes). A tenant can add its own local transporter |
| Carrier account (per company) | Carrier, company, our account or customer code with the carrier, route (A/B/C), connector, active flag | API keys are kept in Google Secret Manager under the tenant, never in the database or in code. Never deleted, only deactivated |
| Shipment | Company, branch, carrier, mode (courier, air cargo, road, ocean), AWB or LR number and date, linked delivery notes, customer and ship-to address (copied from the delivery note), packages, weight, declared value, payment (prepaid, to pay, COD amount), EDD, current MyERP status, last event time and place, delivered date and time, receiver name, POD file, RTO flag | AWB is unique per carrier. Current status is worked out from the events. A shipment can be cancelled (wrong AWB entered), never deleted |
| Tracking event | Shipment, event time, place, carrier code and text, MyERP status, source (webhook, daily pull, typed by a user), received at, raw reply from the carrier | **Never edited or deleted.** The same event arriving twice (same shipment, time, code) is dropped. A typed status is an event too, with the user's name |

## The daily update

- A scheduled job (Celery beat, or Cloud Run job + Cloud Scheduler, as in the hosting plan) runs **every morning before the email**, by default at 7:00 IST, and can run again in the afternoon if Sidharth wants.
- It goes tenant by tenant, and inside each tenant only through `use_tenant(...)`. For each active carrier account it asks for the latest events of every **open** shipment.
- Shipments still open after 30 days (the number is a setting) stop being asked and are flagged "No update for 30 days", so a forgotten AWB does not cost API calls for ever.
- Webhooks (route A, and route B where the carrier offers them) update a shipment within minutes. The daily pull is still run as a safety net for missed webhooks. A webhook is accepted only with the secret agreed with that service, and is matched to the tenant through a platform-side table of webhook keys (the same pattern as the attendance device registry).
- Calls stay within each service's rate limits, are retried with back-off, and a failed carrier is reported in the email ("Delhivery: could not update 12 shipments, last success yesterday 07:00") rather than failing silently.
- Each run is logged: when, how many shipments asked, updated, failed.

## The consolidated despatch email

### Who gets it

- A **notification list** per company, and optionally per branch: MyERP users (by role, e.g. everyone with the Dispatch role at that branch) plus outside email addresses (a transporter coordinator, a shared despatch mailbox). Set on a small master screen; changes are audit-logged like other masters.
- One email per list per day, at a set time (default 8:00 IST, after the 7:00 update). A list can choose "only send if something needs action".
- Sent from the transactional email service in the plan (SendGrid, SES or similar), from a MyERP address with the company name.

### What it contains

Subject: `Despatch status, Apurvam Organics LLP, Tue 10 Nov: 3 need action, 18 delivered`

1. **Summary line**: open shipments, delivered yesterday, out for delivery today, need action.
2. **Needs action** (first, because it is why the email is read):
   - Delivery failed, Held, RTO, Lost or damaged, with the carrier's reason.
   - Past EDD and not delivered.
   - No movement for 3 days (a setting) while in transit.
   - Booked more than 24 hours ago and not picked up.
   - **Delivery notes submitted yesterday with no AWB entered.**
   - Status could not be updated (carrier errors), and carriers with no API to update by hand.
3. **Delivered yesterday**: customer, delivery note, AWB, delivered at, receiver.
4. **Out for delivery today**.
5. **In transit**: count by carrier, with the list in an attached Excel sheet so the email stays short.

Every row shows customer, city, delivery note and invoice number, carrier, AWB (a link to the carrier's tracking page), MyERP status, last event and its time, days since dispatch. Each section links to the Shipments screen filtered the same way. The email shows only what the list's members may see (company and branch).

The email is a fixed scheduled report. When the generic scheduled reports in the AI assistant spec (PR #35) are built, it can move onto that, with the same content.

### Customer notifications (later)

Sending the customer a "dispatched, track here" message by email or WhatsApp, and "delivered" confirmations, uses the same events. Left for later; see open question 7.

## Screens

- **Shipments**: list with filters (company, branch, carrier, status, customer, date, needs action), the same sections as the email, and a "Refresh now" button for one shipment. Opening a shipment shows its events as a timeline, the linked delivery notes, the POD, and the Activity column on the right (as on other screens).
- **Delivery note**: a Shipments section to add AWBs, and its current status at the top.
- **Carriers** and **Carrier accounts** under Masters, and **Notification lists** under Settings (or Masters).
- Layout B3 with the PageHeader band; every form's submit button says Save; the user manual gets its chapter in the same PR, as for every screen.

## Company modules and plans

- Tracking is part of the **Sales** module (decision 0014), not a module of its own; its screens hide when Sales is off.
- For SaaS, "shipment tracking" and each paid connector are **plan feature flags** (no tenant-specific code); a tenant brings its own carrier or aggregator account.

## Build order (one PR each, each after the previous is seen)

1. Carrier master (with AWB formats), carrier accounts, shipment and tracking event records, the Shipments screen with status typed by hand (route C). Tests: AWB format checks, duplicate events dropped, current status from events.
2. The first connector (the aggregator or the carrier Apurvam uses most), the daily update job and its run log. Tested against recorded replies from that service.
3. The daily despatch email and notification lists.
4. Webhooks for that connector.
5. With Phase 4: link shipments to delivery notes, the delivered date and "on delivery" due dates, AWB scan in the Dispatch workspace, the "no AWB entered" check, draft sales return on RTO.
6. More connectors as needed; e-way bill Part B from the shipment (with 6a); export AWBs (with spec 03).

Steps 1 to 4 do not need Phase 4. If Sidharth wants tracking before Sales is built, a shipment can be entered with the customer (a party, already built) and the ERPNext invoice or delivery note number as text, and linked to MyERP delivery notes later. That gives the despatch team the daily email while ERPNext is still in use.

## Open questions for Sidharth

1. **Which couriers, airlines and transporters** do you use for sales today, and roughly what share each? (Answered in part, 11 Nov: Delhivery. Which others, and do you have a Delhivery business account with API access?)
2. Roughly **how many shipments a day**, and how many companies or branches despatch?
3. Do you have **business accounts with API access** at any of them, or use an aggregator already (Shiprocket, ClickPost, NimbusPost, AfterShip)? Would you rather pay an aggregator for one connection, or connect directly to one or two carriers?
4. Is "AWB" here mostly **courier dockets**, or also **airline air cargo** (through a forwarder), or both?
5. **Who should get the email**, one email for everyone or one per company or branch, and **at what time**? Should it also go to the salesman of each customer?
6. Do you want this **before Phase 4** (shipments entered against ERPNext invoice numbers), or only with Sales in MyERP?
7. Later: should **customers** get dispatch and delivery messages with a tracking link (email or WhatsApp)?
8. Do you book shipments on the carrier's website and then type the AWB, or would you like MyERP to **book the shipment and print the label** (possible through some aggregators)?
