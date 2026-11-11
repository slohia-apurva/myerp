# Shipment (AWB) tracking and daily despatch email (spec, 10 Nov 2026)

Requested by Sidharth: "AWB tracking for sales to be updated daily into system and also consolidated email sent to concerned despatch" team.

Status: spec only, for review. Nothing is built until Sidharth approves it. It hangs off the sales delivery note (Phase 4), but the first steps can run earlier (see "Build order"). Open questions are at the end; which couriers Apurvam uses decides most of the integration work.

Update 11 Nov: Sidharth uses **Delhivery** and gave its PIN serviceability list (21,528 PINs with an ODA flag). It is loaded as a central table in the masters work (see "Courier serviceability by PIN" below), so Delhivery is the first carrier and the first connector. Other couriers' lists are added to the same table later.

Update 11 Nov (later): the couriers are **Delhivery, Blue Dart and DP World** (no API access yet; Sidharth can apply), and Apurvam has a **Shiprocket** account. The choice between couriers is about cost, so MyERP should **suggest the cheapest courier** (see "Cheapest courier" below).

Update 11 Nov (Sidharth): Delhivery and Blue Dart are **direct accounts, two each: one B2C (parcel/express) and one B2B (heavier freight)**. Shiprocket is a separate account. Rate charts for all will be shared. Despatch email at **8:00 am**; recipients to follow. So the first set-up is five carrier accounts: Delhivery B2C, Delhivery B2B, Blue Dart B2C, Blue Dart B2B, Shiprocket (plus DP World).

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

## Cheapest courier

Asked by Sidharth (11 Nov): "It's about cost whom to use. Once a customer is created the system can check the lowest rate per kg with all courier services and suggest whom to use."

### Where the rates come from

Two sources, used side by side; each quote says which one it came from.

| Source | How | Covers |
| --- | --- | --- |
| Live quote from Shiprocket | Shiprocket's serviceability call takes pickup PIN, delivery PIN, weight (and COD or prepaid) and returns every courier on our Shiprocket account that serves the lane, with its freight, estimated delivery days and rating | Couriers booked through Shiprocket |
| Our own rate cards | For couriers we contract with directly (Delhivery, Blue Dart, DP World), their rate card is typed in or imported as **dated master data** per company and carrier account | Direct contracts, and a fallback when the live call fails |

A **rate card** holds what Indian courier contracts usually charge on, all as data, never constants in code:

- **Zones**: how the courier groups lanes (within city, within state, metro to metro, rest of India, special zones such as the North East and J&K), mapped from origin and destination PIN or state.
- **Weight slabs** per zone: first slab (e.g. first 0.5 kg) and each additional slab, or a per-kg rate above a weight; minimum chargeable weight.
- **Volumetric weight**: L × B × H ÷ the courier's divisor (often 5000 for air, varies by courier and mode). Chargeable weight is the higher of actual and volumetric.
- **Add-ons**: fuel surcharge %, ODA charge, COD charge or %, docket charge, minimum per shipment, risk or insurance %, and GST on the total.
- **Mode**: surface or air, with expected transit days per zone.
- Valid from and to dates, so a new rate card applies from its date and old shipments keep the rate they were quoted.
- **One rate card per carrier account**, not per carrier: a courier's B2C and B2B accounts have different rate structures (B2B freight usually has a higher minimum chargeable weight, docket and handling charges, and per-kg pricing by zone; B2C parcel has small slabs). The quote compares every account, so a heavy consignment may come out cheaper on the B2B account and a small one on B2C.

### When MyERP suggests

- **Customer and address forms** (when a customer is created or a ship-to address added): a small table "Courier cost to this PIN" for a **1 kg and a 10 kg** parcel from the company's default ship-from branch: each courier that serves the PIN, its cost per kg, transit days and ODA flag, cheapest first. The cheapest can be saved as the address's **preferred courier**. This is indicative; the real choice is made per shipment.
- **Delivery note** (the real choice): with the actual packages, weight and dimensions (from the item UOMs), MyERP quotes every courier that serves the ship-to PIN and **pre-selects the cheapest that meets the delivery date** (a surface courier that misses the promised date is not suggested over a faster one). The person can pick another and gives a short reason; the quote and the reason are kept on the shipment.
- **Per kg** is shown for comparison, but the suggestion uses the **total landed freight** for that shipment (slabs, minimums, fuel, ODA and COD make per kg alone misleading for small parcels).

Rules: MyERP only suggests; a person picks the courier (decision 0006). A quote is stored with the shipment (source, rate card version, chargeable weight, amount), so a later rate change never changes an old shipment.

### Freight check (later)

When the courier's invoice arrives, each AWB's billed amount is matched with the quote on its shipment; differences (wrong weight, extra ODA, wrong zone) are listed for a claim. Monthly freight by courier, cost per kg by zone, and money saved against the dearest quote go into MIS.

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
6. Rate cards (dated, per carrier account) and the courier cost table on customer and address forms; Shiprocket live quotes.
7. With Phase 4: quote all couriers on the delivery note and pre-select the cheapest that meets the date; quote kept on the shipment.
8. More connectors as needed (Delhivery, Blue Dart, DP World direct once API access arrives); e-way bill Part B from the shipment (with 6a); export AWBs (with spec 03); freight check against courier invoices.

Steps 1 to 4 do not need Phase 4. If Sidharth wants tracking before Sales is built, a shipment can be entered with the customer (a party, already built) and the ERPNext invoice or delivery note number as text, and linked to MyERP delivery notes later. That gives the despatch team the daily email while ERPNext is still in use.

## Open questions for Sidharth

1. **Which couriers, airlines and transporters** do you use for sales today, and roughly what share each? (Answered 11 Nov: Delhivery, Blue Dart, DP World, and a Shiprocket account; no direct API access yet.)
2. Roughly **how many shipments a day**, and how many companies or branches despatch?
3. (Answered 11 Nov: Delhivery and Blue Dart are direct, each with a B2C and a B2B account; Shiprocket is separate; rate charts to be shared.)
4. Is "AWB" here mostly **courier dockets**, or also **airline air cargo** (through a forwarder), or both?
5. **Who should get the email**, one email for everyone or one per company or branch? (Time answered: 8:00 am.) Should it also go to the salesman of each customer?
6. Do you want this **before Phase 4** (shipments entered against ERPNext invoice numbers), or only with Sales in MyERP?
7. Later: should **customers** get dispatch and delivery messages with a tracking link (email or WhatsApp)?
8. Do you book shipments on the carrier's website and then type the AWB, or would you like MyERP to **book the shipment and print the label** (possible through some aggregators)?
