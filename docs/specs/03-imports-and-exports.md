# Imports and exports (spec, 5 Nov 2026)

Requested by Sidharth: import and export documentation inside MyERP, with **more than one bill of entry (BOE) per import**.

Status: spec only. Built with Purchase (Phase 3b) for imports and Sales (Phase 4) for exports, because both hang off POs, GRNs, sales invoices and batches. Foreign currencies (company switch, ledger currency, exchange rates) are already live (PR #15).

## Imports

### Import file

One **import file** per foreign purchase (usually one supplier invoice, one shipment). It ties together everything about that import:

| Part | Holds |
| --- | --- |
| Header | Import file number (naming series), company, branch, supplier, currency, Incoterm (FOB, CIF, CFR, EXW...), port of loading, port of discharge, CHA (customs broker, a ledger), IEC used, status |
| Purchase links | One or more POs and supplier commercial invoices (FC amount, invoice rate), proforma and advance payments |
| Shipment | BL or AWB number and date, vessel and voyage or flight, containers (number, size, seal), ETD, ETA, arrival date; tracking through the carriers master (integrations plan) |
| Documents | Commercial invoice, packing list, BL/AWB, certificate of origin (for FTA duty benefit), phytosanitary / health certificate, insurance, FSSAI NOC and other attachments, each with number, date and file |
| Bills of entry | **Many per file** (see below) |
| Charges | Freight, insurance, CHA fees, CFS / port charges, demurrage, detention, transport to factory, each a purchase bill from its own vendor (with GST and TDS as usual) |
| Receipts | The GRN(s) that bring the goods into stock, batch by batch |

### More than one BOE per import file

A file can carry several BOEs because:

1. **Part clearance**: one shipment cleared in lots (different dates, ports, or because only part was needed).
2. **Warehousing**: an **into-bond** BOE (goods kept in a customs-bonded warehouse, duty deferred) followed by several **ex-bond** BOEs as lots are taken out and duty paid.
3. **Re-assessment or amendment**: a BOE amended after assessment; the old one is kept, marked superseded.

Each BOE records:

| Field | Notes |
| --- | --- |
| Type | Home consumption, into-bond (warehousing), ex-bond |
| BOE number, date, port code | Unique per port and date; ex-bond BOE links to its into-bond BOE |
| Exchange rate | Customs notified rate on the BOE date (may differ from the supplier invoice rate) |
| Lines | Item, HSN (CTH), qty and UOM, FC value, assessable value in INR (CIF + landing charges as assessed) |
| Duties per line | BCD, SWS (10% of BCD), IGST, compensation cess, anti-dumping or safeguard duty if any; rates and exemption notification from the dated tariff master, but the amounts as assessed on the BOE are what is booked |
| Payment | Duty challan number, date, amount; paid by us or by the CHA (then CHA's bill) |
| Out-of-charge | OOC date; goods may move only after this |

Rules:

- The quantities on all ex-bond BOEs together cannot exceed the into-bond BOE; MyERP shows the balance still in bond per item.
- The quantities on all BOEs of a file cannot exceed the supplier invoice quantities (warn on excess).
- BOEs are entered (or later pulled from ICEGATE) as drafts and submitted by a person, like every other document.

### What it posts

- **Supplier invoice**: Dr Goods in transit (or GRNI when the GRN comes first), Cr supplier (FC ledger, at the invoice rate).
- **Each BOE**:
  - BCD, SWS, cess and anti-dumping duty: Dr landed cost on the receipt (stock value of those batches), Cr customs duty payable / CHA.
  - IGST on import: Dr IGST input (ITC), Cr customs duty payable / CHA. Matched later to the IMPG section of GSTR-2B.
  - Into-bond BOE posts no duty; the goods sit in a "bonded warehouse" stock location owned by the company.
- **GRN** against a BOE: stock in, batch by batch, at supplier value + duties + allocated charges (landed cost, split by value, weight or volume as chosen). A GRN cannot receive more than its BOE cleared.
- **Payment to supplier**: at the payment rate; the difference from the invoice rate posts to exchange gain/loss (forex).

### Reports

Import register (file, supplier, BOEs, duty by type), goods in transit, stock in bond by BOE, landed cost per batch, duty paid vs IGST credit taken (GSTR-2B IMPG match), open import files, supplier payments due.

## Exports

### Export file

One **export file** per shipment to a foreign buyer.

| Part | Holds |
| --- | --- |
| Header | Export file number, company, branch, buyer, currency, Incoterm, port of loading, port of discharge, final destination, country of origin, CHA, status |
| Sales links | Sales order(s), proforma invoice and advances received |
| Export invoice | The sales invoice in FC, marked export: **under LUT / bond** (zero-rated, no IGST) or **with IGST paid** (refund claimed); LUT number and year from the company master |
| Packing list | Per package: marks and numbers, items, batches, net and gross weight, dimensions (from item UOM master) |
| Shipping bill | Number, date, port, FOB value in INR, exchange rate, LEO (let export order) date, scheme (drawback, RoDTEP), EGM number |
| Shipment | BL or AWB, vessel/voyage or flight, containers and seals, ETD, ETA |
| Certificates | Certificate of origin (preferential / non-preferential), phytosanitary, health, organic (NPOP / NOP transaction certificate), FSSAI export, fumigation, insurance |
| Realisation | Payments received, e-BRC number and date, bank charges, short realisation |
| Incentives | IGST refund status, drawback and RoDTEP amounts claimed and received |

A file can also hold more than one shipping bill when one order ships in parts.

### What it posts

- **Export invoice**: Dr buyer (FC ledger, at the invoice rate), Cr export sales; IGST payable only when exporting with IGST paid.
- **Receipt from buyer**: at the realisation rate; the difference goes to forex gain/loss. Bank charges posted separately.
- **IGST refund, drawback, RoDTEP**: Dr receivable from government, Cr IGST refund receivable / export incentive income, cleared when received. RoDTEP scrips used to pay import duty are tracked as a ledger.
- **Delivery note**: stock out by batch as usual (traceability back to production batches).

### Reports

Export register (invoice, shipping bill, LEO, BL), unrealised exports past due (the FEMA 9-month limit), e-BRC pending, IGST refund pending, RoDTEP / drawback receivable, LUT exports for the GSTR-1 export table.

## Printouts

Generated from the file, in the company's format: commercial invoice, packing list, proforma, shipping instructions for the CHA, certificate-of-origin draft data. Bank documents (bill of exchange, covering letter for collection) later.

## Masters needed

- Ports (UN/LOCODE and Indian customs port codes), countries, Incoterms: global masters.
- Customs tariff (CTH, BCD, SWS, IGST, cess) as **dated** global master data, never constants (CLAUDE.md rule).
- Company: IEC, AD code per bank, LUT number and validity per financial year.
- Party: buyer/supplier country, currency, IEC (supplier side not needed), bank.
- CHAs and shipping lines as ledgers with a role tag.

## Integrations (later)

ICEGATE / e-Sanchit for BOE and shipping bill status, DGFT for e-BRC, carrier tracking: see "Integrations with outside services" in the roadmap (plan PR #5). Until then everything is typed in or uploaded from the CHA's checklist.

## Open questions for Sidharth

1. Several BOEs per import: part-clearances, warehousing (into-bond then ex-bond), or both?
2. Which export documents does Apurvam prepare itself and which does the CHA prepare?
3. Roughly how many import and export files a year, and which ports?
4. Exports under LUT or with IGST paid? Any drawback / RoDTEP claims?
5. Do imports ever arrive before the supplier invoice (GRN first) or always with it?
