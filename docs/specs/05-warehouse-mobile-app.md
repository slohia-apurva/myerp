# Warehouse mobile app (spec, 9 Nov 2026)

Requested by Sidharth: a mobile app to make floor work easier when receiving purchases (GRN), receiving a customer's material for processing (job work), delivering sales, delivering a customer's own goods back to them, and moving any stock inside a factory or between sites.

Status: spec only, for review. Nothing is built until Sidharth approves it. The documents the app works on (GRN, delivery note, stock entry, job work) belong to Phases 3 to 5, so the app is built alongside them, screen by screen. Open questions are at the end; the answers on devices, offline use and labels decide part of the design.

## The idea in one line

One **MyERP mobile app** for everyone who works away from a desk. It opens a **workspace** that fits the person's role (Stores, Dispatch, Job work, Salesman, Owner). On the floor, work is done by **scanning**: scan the document, scan the item or carton, scan the bin. The app fills in the rest, and the result is the same GRN, delivery note or stock entry that the desktop screens make. There is no separate "mobile data".

## One app, many workspaces

The planned salesman order app (customers and approved items, orders as draft sales orders) and this warehouse app are the same app with different workspaces. One sign-in, one install, one set of updates.

| Workspace | Who | What they do on the phone |
| --- | --- | --- |
| Receive | Stores | Gate entry, GRN against a PO, put-away into bins, quality checks on receipt |
| Job work | Stores, Production | Receive a customer's material, return processed goods and leftovers to the customer |
| Dispatch | Stores, Dispatch | Pick against a sales order or pick list, pack, load, deliver |
| Move | Stores | Bin to bin, warehouse to warehouse, branch to branch (send and receive), issue to production |
| Count | Stores | Stock count of a bin, a rack or the whole warehouse; look up any item, batch or bin |
| Sales | Salesman | Own customers only, approved items per customer, post orders as draft sales orders (Phase 4) |
| Approvals | Owner, managers | Approve POs, credit-limit breaches, excess receipts; see key figures |

A person sees only the workspaces their role allows (decision 0012) and only for companies that have the matching module on (decision 0014). For example, a trading company without Production never shows Job work or "issue to production".

## Web app first, installed on the phone

**Recommendation:** build it as an installable web app (a PWA) from the same React code as the desktop, served at `/m` on each tenant's address. It installs from the browser to the home screen, opens full screen, and updates itself on every deploy.

Why not a native Android/iOS app first:

- One codebase, one deploy, same login and permissions; no Play Store review for every change.
- Rugged scanner phones (Zebra, Honeywell, Urovo, Newland and similar) send each scan as typed text ("keyboard wedge"), which a web app reads like any input. Ordinary phones scan with the camera, which a web app can do too.
- If we later need something only a native app can do (vendor scanner SDK, Bluetooth label printers, long offline work), we wrap the same code with Capacitor rather than start again.

Screens are built for one hand and gloves: big buttons, one task per screen, large text, a beep and a vibrate on every scan (a different sound for an error), and nothing that needs typing if a scan can do it.

## How scanning works

Every scan is looked up in one place on the server and answered with what it is:

| Scanned code | Recognised as |
| --- | --- |
| Item UOM barcode (piece, inner, carton; already in the item UOM table) | Item, UOM, quantity in stock units (one carton scan = 24 units) |
| GS1 label (GS1-128 or GS1 DataMatrix) | Item (GTIN), batch (10), expiry (17), manufacturing date (11), quantity (30/37), pallet (SSCC 00) |
| MyERP label (our own print) | Batch, carton or pallet with its contents |
| Supplier's or customer's own barcode | Mapped once to our item (a "their code" list per party), then recognised every time |
| Bin label | Warehouse location (site, zone, rack, bin; rule 9) |
| Document QR | PO, SO, pick list, transfer, job work challan; opens it in the app |

An unknown code is never guessed. The app asks the person to pick the item once and offers to save the mapping (with permission).

## Rules the app keeps

These are the project's existing rules, applied to every mobile screen.

1. **Batch on every movement.** Batch-tracked items cannot be received, moved or delivered without a batch. At receipt the app takes the supplier's batch number, manufacturing date and expiry (from the label scan where possible) and creates the MyERP batch with QC status **quarantine** (rule 12). Picking offers only released batches, earliest expiry first.
2. **From → to on every movement.** Each line records where the stock came from and where it went (supplier, customer, bin, in-transit, production, scrap), so batch traceability backwards and forwards works from the stock ledger alone.
3. **Branch on every voucher.** A person works at one branch at a time (picked once, shown at the top). Every document made in the app carries that company and branch.
4. **Excess receipt is accepted, with an alert.** Receiving more than the PO quantity is allowed. The app shows a warning, the GRN posts, and an alert goes to the Purchase team and the Owner naming the PO, item, ordered and received quantity and who received it.
5. **Perpetual inventory.** A submitted GRN, delivery or issue posts to both ledgers at once, exactly as decision 0017 says. The app calls the same posting service as the desktop (rule 10); it has no posting logic of its own.
6. **Draft, then submit.** Work on the floor builds a draft. Submit is a separate tap, allowed only to roles that may submit that document (Stores may submit GRN, stock entries and delivery notes). Posted documents are never edited; corrections are cancel and amend from the desktop.
7. **Every action is logged.** Each document shows who scanned, on which device, when, and any photos, in its Activity column (decision 0016).

## What each workspace does

### Receive (GRN)

1. **Gate entry** (optional step): vehicle number, driver, LR or docket number, e-way bill number, supplier invoice number and date, photo of the invoice. This also starts the AI bill capture in the background when that is switched on (it only makes a draft).
2. **Pick the PO**: scan its QR or choose from the supplier's open POs. Receiving without a PO is allowed only for roles given that right.
3. **Scan in**: each carton scan adds to the line; the app shows ordered, received so far and the difference. Short and excess show in colour; excess triggers rule 4.
4. **Batch**: taken from the label or keyed once per batch; the app can **print MyERP batch labels** on the spot for suppliers whose labels we cannot read.
5. **Quality on receipt** (the optional quality add-on, per company): a short checklist per GRN or per batch.
   - **Carton (CFC) check**: carton condition (good, crushed, wet, torn), count of damaged cartons, and photos.
   - **Batch code print check**: is the batch code printed, legible and matching the label and the document; photo of the print.
   - The checklist items are master data, so more checks can be added later without code. A failed check keeps the batch in quarantine, or marks the damaged quantity rejected.
6. **Put-away**: the app suggests a bin (the item's usual bin, or an empty one in its zone); the person scans the bin to confirm.
7. **Submit**: the GRN posts (Dr Stock, Cr GRNI).

### Job work: a customer's material for processing

When a customer sends their own material for us to process and send back (we are the job worker), that stock is **not ours**: it carries no value in our books and must not mix with our own stock.

- **Customer-owned stock** is kept in the same stock ledger with an **owner** set to the customer, at zero value. Our own stock has no owner. Every stock report can show "own", "customer-owned" or both, and the stock GL check (stock value equals the stock ledgers) ignores customer-owned rows.
- **Receive customer material**: scan in against the customer's delivery challan (number, date, photo), with the customer's batch codes kept. Optional: link it to a job work order that says what we will make and the expected yield.
- **Process**: in production, customer material is issued and the processed goods come out also owned by the customer (Phase 5 job cards). Scrap and waste are recorded the same way.
- **Return / deliver customer goods**: scan out the processed goods, any unused material and scrap (if it goes back), and print a **delivery challan** for the movement of their goods. A separate **job work charges invoice** (a service, SAC 9988) bills our processing charges. Only the charges touch our GL.
- **Reconciliation per customer and job**: received, consumed, made, returned, scrap, and balance still with us. This is what the customer needs for their ITC-04 filing, and what we need to answer "whose goods are in this bin".

### Dispatch (sales delivery)

1. Open the pick list (scan its QR, or from the list of SOs due today at this branch). Stock was reserved against a rack group (rule 9); the app now guides the picker bin by bin, in walking order.
2. Scan bin, then scan carton. A wrong item, a quarantined or expired batch, or a batch other than the suggested one is refused or warned, according to the item's rules.
3. Pack: optionally scan cartons onto a pallet and print a pallet or carton label with contents.
4. Load: vehicle number, driver, seal number, photo of the loaded vehicle.
5. Submit the delivery note: it posts Dr COGS, Cr Stock at FIFO cost. The sales invoice, e-way bill and e-invoice follow on the desktop (or automatically, once GST is built).

### Move

- **Bin to bin** and **warehouse to warehouse** at one site: scan from-bin, scan items, scan to-bin. No GL change unless the warehouses use different stock ledgers.
- **Branch to branch**: the sending branch scans out to **in-transit**; the receiving branch scans in and the app shows short or excess against what was sent. Within one GSTIN this is a plain transfer with a delivery challan (and an e-way bill when the law needs it). Between two GSTINs or two companies it becomes a tax invoice and matching purchase (rule 13); the app makes the drafts, the person submits.
- **Issue to production**: scan the work order, then the material; posts Dr WIP, Cr Stock.

### Count

- Count a bin, a rack, or the whole warehouse, by scanning. Counts are blind (the app does not show the book quantity) unless the role allows it.
- Differences become a draft stock reconciliation for a supervisor to submit (Dr or Cr stock adjustment).
- **Look up**: scan anything to see what it is and where it is: an item shows stock by bin and batch; a batch shows where it is and where it came from; a bin shows its contents and owner.

## Poor network and offline

Factory and godown corners often have weak Wi-Fi or mobile signal. The plan:

1. **Works on a weak network** from the start: small requests, retries, and a clear "not sent yet" mark on any scan the server has not confirmed.
2. **Scans are kept on the phone** until the server confirms them, so nothing is lost if the signal drops or the app is closed. Each scan carries an ID made on the phone, so sending it twice never counts it twice.
3. **Submit needs the server.** Posting checks stock, batch status and permissions on the server, so submitting waits for a connection. A full offline mode (picking and receiving with no network at all for hours) is much more work and is built only if the answers below say it is needed.

## Sign-in and shared devices

- Personal phones: Sign in with Google, the same as the desktop (or the planned email OTP).
- **Shared scanner devices** that stay in the warehouse: an admin registers the device to a company and branch once; workers then sign in on it with their own short PIN. Each scan is still recorded against the person, not the device. A lost device is switched off from the desktop.
- Tenant comes from the address, as on the desktop (decision 0003); a registered device belongs to one tenant only.

## Company modules and SaaS

- The app is not a module of its own. Its workspaces follow the company's modules: Receive needs Purchase, Dispatch needs Sales, Move and Count need Stock, Job work needs the job work module, Sales needs Sales.
- **Job work for customers** is a new module code **`job_work`** ("Job work for customers": customer-owned stock, job work orders, challans, charges invoice), needing Stock. A company that never processes others' goods leaves it off.
- For SaaS, the mobile app is a plan feature flag (some plans may not include it), and registered devices count against a plan limit, like users.

## Labels and printing

- **Batch and carton labels** (GS1-128 where we have GTINs, else our own code), **pallet labels** (SSCC), **bin labels**, and **document QR codes** printed on POs, pick lists, transfers and challans.
- From the desktop on a normal or label printer (PDF), and from the phone to a network label printer at the dock. Bluetooth printers clipped to the belt need the native wrapper and come later if wanted.
- Label layouts are print formats (data, per company), not code.

## Build order (one PR each, each after the previous is seen)

The app is built alongside the documents it uses, not ahead of them.

1. **App shell** (can follow the Items master in Phase 1): installable web app at `/m`, sign-in, branch pick, workspaces by role and module, the scan box (camera and hardware scanner), and the **Look up** screen using the item UOM barcodes.
2. **Bin labels, Move (bin to bin) and Count** with Phase 3a (stock entries, batches, warehouses tree).
3. **Receive**: GRN against a PO with batch capture, excess receipt alert and put-away, with Phase 3b.
4. **Quality on receipt**: CFC carton check and batch code print check, with photos.
5. **Branch to branch transfers** with in-transit, delivery challan and the rule 13 drafts.
6. **Job work for customers**: customer-owned stock, receive, return and the reconciliation (needs the `job_work` module; the processing step comes with Phase 5).
7. **Dispatch**: pick, pack, load and deliver, with Phase 4.
8. **Sales workspace** (salesman orders) with Phase 4.
9. **Shared devices with PIN sign-in**, and full offline mode or the native wrapper only if the answers below need them.

Where this sits in the roadmap: the plan listed "mobile app" as out of scope for v1. This spec brings the warehouse workspaces into v1 alongside Phases 3 to 5, because they are how stores will actually use those modules; the salesman and approval workspaces stay with Phase 4 and later.

## Open questions for Sidharth

1. **Devices**: ordinary Android phones with the camera, or rugged scanner phones (which brand/model, if any are already in use)? Are any iPhones used on the floor?
2. **Shared or personal**: do store workers carry their own phone, or would devices stay in the warehouse and be shared across shifts? Do the workers have Google accounts or email?
3. **Network**: is there Wi-Fi in every godown, cold room and loading bay at each site, or mobile data only? Are there places with no signal at all, where work would have to be done fully offline?
4. **Labels today**: do your suppliers' cartons carry barcodes (GS1 with batch and expiry, or only the product barcode)? Do you print your own batch or carton labels now, and on what printer?
5. **Bins**: are racks and bins already numbered at each site, so bin labels can be put up?
6. **Job work**: which customers send material for processing, roughly how often, and what comes back (the processed product only, or also leftover material and scrap)? Do you also send your own material out to other job workers?
7. **Branch transfers**: which sites send stock to each other, and are any of them under a different GSTIN or the other company?
8. **Quality on receipt**: who does the carton and batch-code checks today (stores or a QC person), and should a failed check stop the GRN or only put the goods in quarantine?
9. **Priority**: which of these hurts most today (receiving, dispatch, transfers, counts or job work)? That one can be the first workspace after the app shell.
