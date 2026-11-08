# AI assistant: ask your data, and other AI tools (spec, 8 Nov 2026)

Requested by Sidharth: connect MyERP to Claude so that a person can ask the system in plain words, for example "make a report of ..." or "show the top 10 customers", and so that other AI tools can work with MyERP too.

Status: spec only, for review. Nothing is built until Sidharth approves it. Open questions are at the end.

This spec builds on the "AI in MyERP" section of [00-architecture-and-roadmap.md](00-architecture-and-roadmap.md) and decision [0006](../decisions/0006-ai-drafts-only.md) (AI makes drafts, never postings). It does not change either; it describes the "Ask your data" feature in detail and adds a way for outside AI tools to connect.

## What it is, in one paragraph

Two ways in, one set of tools behind them, plus scheduled tasks that run reports on their own:

1. **Ask MyERP** (inside the app). An "Ask" button in the top menu opens a chat panel on the right. The person types a question. MyERP sends the question to Claude together with a fixed list of **read-only report tools**. Claude picks a tool and its filters (company, dates, group, top N), MyERP runs it **with that person's permissions** and shows the result as a normal MyERP table with drill-down, and Claude adds a short explanation.
2. **MyERP for other AI tools** (later). A secure connection point (an MCP server, the standard way AI apps such as Claude Desktop, claude.ai and others plug into business systems) that offers **the same read-only tools**. A person connects their own AI app with their own MyERP login, and that app sees exactly what the person could see on screen, no more.

The language model never touches the database. It only chooses which report to run and with which filters; every figure comes from MyERP's own code.

## What works now, and what comes later

The assistant can only answer from data that MyERP holds. Today MyERP has masters only; customers and sales arrive in Phase 4.

| Question | When it can be answered | Tool behind it |
| --- | --- | --- |
| "Which ledgers are under Sundry Debtors in Apurvam Organics LLP?" | Now (masters) | Ledgers list |
| "Top 10 debtors by opening balance" / "Which creditors have bills older than 90 days at books start?" | Now (opening balances and bills) | Opening balances, opening bills |
| "Which licences or certificates expire in the next 60 days?" | Now | Licences and certificates |
| "Who changed the GST number on the Delhi branch, and when?" | Now (audit log) | Change history |
| "Which modules does each company use?", "List branches with their GSTIN" | Now | Companies, branches |
| "Trial balance as on 31 March", "Cash and bank position today", "Day book for yesterday" | Phase 2 (Accounts) | Trial balance, GL, day book, cash/bank book |
| "Stock of 500 g packets by warehouse", "Batches expiring this month" | Phase 3a (Stock) | Stock balance, batch-wise stock, expiry |
| "Pending POs from supplier X", "Purchases by supplier this quarter" | Phase 3b (Purchase) | Pending POs, purchase register |
| **"Top 10 customers by sales this year"**, "Overdue over 60 days in Maharashtra" | Phase 4 (Sales) | Sales register, receivables ageing |
| "Margin by item last quarter vs the one before" | Phase 6c (MIS) | Margin report |

Each new report that a module adds becomes a new assistant tool in the same pull request, so the assistant grows with the system.

## How a question is answered

1. The person asks in the chat panel. The panel knows the current company (the company switch), so "this company" works.
2. The backend sends Claude: a fixed instruction text, the list of tools **this person is allowed to use** (a tool the role cannot see is not even offered), and the conversation so far.
3. Claude replies with a tool call, for example `ledger_balances(company="Apurvam Organics LLP", group="Sundry Debtors", sort="balance desc", limit=10)`.
4. MyERP checks the call (known tool, valid filters, the company is one the person can see), runs it as that person, inside that person's tenant, and stores the result.
5. The result goes back to Claude, and also straight to the screen: the **table on screen is drawn from MyERP's result, not from Claude's text**, so a figure can never be mistyped by the model. Every row links to the record (and, once vouchers exist, to the vouchers).
6. Claude writes one or two sentences on top ("The top 10 debtors hold 62% of all opening receivables; the largest is ..."). It may call more tools first (for example, look up a group name, then run the report).
7. The person can click **"Open as report"** to open the same report on its normal screen with the same filters, or **"Save report"** to keep the question and filters as a saved report (see below), or download it as Excel or CSV.

### "Create a report from the data"

There are two kinds of request, handled differently:

- **A report MyERP already has, with different filters or grouping** ("debtors by state, largest first"). The assistant runs the existing report tool with those settings. This covers most asks.
- **A new combination** ("ledgers with no change in 6 months and a balance over 1 lakh"). The tools allow filters, grouping, sorting, top N and a few totals (sum, count, average) on the fields each report exposes. Claude can combine these, but cannot write SQL. If a question needs data no tool exposes, the assistant says so plainly ("MyERP has no report for that yet") instead of guessing. Those misses are logged, and they are a good list of reports to build next.

A **saved report** stores the definition (tool, filters, columns, sort), not a copy of the figures, so opening it next month shows next month's data. Saved reports are private to the person unless they share them with a role. Saving is the only thing the assistant writes in phase A, and it is a user action (a button), not something Claude does on its own.

Charts (bar, line, pie) come with saved reports in phase A4, drawn by MyERP from the result table.

### Scheduled tasks (added 8 Nov, Sidharth)

A person can ask for something to run on its own on a schedule: "every Monday at 9, send me the top 10 debtors", "on the 1st of each month, list licences expiring in 60 days", later "every morning, cash and bank position with a two-line note".

- **How it is set up.** From any answer or saved report: "Schedule" (daily, weekly on chosen days, monthly on a date, at a time in IST), or by asking in the chat ("send me this every Monday"). In the chat Claude only fills in the schedule form; the person checks it and clicks "Save". A list "My scheduled tasks" shows each one with its next run, last run and a pause / delete button; the Owner sees everyone's.
- **What runs.** A scheduled task is a saved report plus a schedule, and optionally "add an AI note". The report part runs on MyERP's own workers (Celery beat, already in the stack) and costs nothing in AI usage. Only when "add an AI note" is ticked does Claude read the result and write a short comment ("Debtors over 90 days rose by ₹4.2 lakh since last week, mostly two parties"), with the same read-only tools and the same row limit.
- **Whose permissions.** The task always runs as the person who made it, with that person's permissions **checked again at each run**. If their role loses access, or the user is deactivated, the task stops and the Owner is told. A task can be shared only with people who could see the report themselves.
- **Where results go.** Into MyERP: a notification on the bell and an entry in "My scheduled tasks" with the result table (and the Excel file). Email delivery to the person's own login email is an option per task; sending to anyone outside MyERP users is not offered in the first version, so scheduled tasks never send data to outside addresses.
- **Tenant and cost.** The scheduler loops over tenants and runs each task inside its own tenant (the existing rule for scheduled jobs). Tasks count against the same monthly AI cap; a task with "AI note" is skipped (the report still goes out, without the note) when the cap is reached. A tenant has a limit on the number of scheduled tasks (plan setting for SaaS).
- **Never acts.** Like the rest of the assistant, a scheduled task only reads and reports. Later drafting features (for example "every evening, draft payment reminders for overdue customers") would create Drafts for a person to send, each behind its own switch.
- **Logged.** Each run is recorded in "AI activity": which task, when, rows, AI tokens and cost, whether delivery succeeded.

## Security

### Tenant isolation (decision 0003)

- The chat endpoint runs inside the request's tenant, like every other API (the middleware's `use_tenant(...)`). Tool code never takes a tenant argument and never uses `.using(...)`, so a tool can only read the tenant the person logged into.
- Conversations, tool calls and saved reports are stored in the **tenant's own database** (a new tenant-side `ai` app). The platform database holds only the per-tenant AI switch, plan limit and monthly usage counters.
- Claude is called with the same prompt layout for every tenant; nothing from one tenant is ever included in another tenant's request. There is no shared memory or cache of answers across tenants.
- A test asserts that a tool run in tenant A cannot return any row from tenant B, the same way the existing tenancy tests do.

### The person's permissions (decision 0012)

- Each tool declares the permission it needs (for example `masters.view`, `accounts.view`, `reports.view`, `payroll.view`). The tool list sent to Claude is filtered to what the person's role allows. If Claude still asks for a tool the person lacks, MyERP refuses the call and tells Claude "not permitted".
- Company scope: the person sees only companies their role covers; a tool call for another company is refused.
- Payroll and salary data are never offered to the assistant unless the person has `payroll.view`, and even then bank account numbers are masked.
- Using the assistant needs its own permission, `ai.ask` (a new area "AI assistant" on the Roles screen), on by default for Owner and Accountant, off for others until the Owner ticks it.

### Read-only

- Every tool is a read-only function that calls the same query code the report screens use. There is no tool that creates, edits, submits, cancels or deletes anything, and no free-form SQL or "run code" tool.
- Tools run on a read-only database connection where the database supports it, as a second guard.
- When drafting features arrive later (bill capture etc.), they are separate tools that create **Draft** documents only (decision 0006), each switched on separately.

### Prompt injection

Data in MyERP (a ledger name, a note, later a supplier bill) could contain text such as "ignore your instructions". Because every tool is read-only and limited to what the person can already see, the worst such text can do is make an answer wrong; it cannot change data or leak another tenant's data. To reduce wrong answers: tool results are passed to Claude as data, clearly marked; Claude has no web access and no tool that sends anything outside MyERP; and the figures on screen always come from MyERP's table, not from Claude's sentence.

### Audit

Every question is logged in the tenant database: who asked, when, the company, the question, each tool call with its filters, how many rows came back, the answer text, tokens used and cost. The Owner sees this as "AI activity" (a list with filters by person and date). Logs are kept like the audit log (never edited); a tenant can choose to delete conversations older than N months.

### What is sent to Anthropic

- Only the question, the conversation in that panel, and the tool results needed to answer it. Not the whole database.
- Large results are cut down before sending: Claude gets at most a set number of rows (for example 200) plus totals; the full table still shows on screen and in downloads.
- Anthropic's commercial API terms: data sent through the API is not used to train models. Data is held for a limited retention period for abuse monitoring; Anthropic offers zero data retention for eligible business customers on request. This needs checking against Apurvam's and future SaaS customers' needs (open question 5).
- Processing happens outside India (Anthropic's API, or Claude on Google Cloud Vertex AI in a region where it is offered). MyERP's database and backups stay in Mumbai as now.

## Switches, limits and cost

- **On/off**: a plan feature flag for the tenant (SaaS), then a per-company switch, then the `ai.ask` permission per role. MyERP works fully with the assistant off.
- **Spending cap**: a monthly cap per tenant in rupees (set by the Owner, and by plan for SaaS) and an optional daily limit per person. At 80% the Owner gets an alert; at 100% the assistant pauses until the next month or until the Owner raises the cap.
- **API key**: one Anthropic API key held in Google Secret Manager (as other secrets are now), used by the backend only, never sent to the browser. Usage is metered per tenant from each response's token counts.

### Cost estimate

Rough figures, at current Claude API list prices and about ₹88 to the US dollar. A typical question makes 2 to 4 model calls (choose tool, read result, maybe a second tool, answer). The fixed instructions and tool list are cached, which makes repeated parts about 90% cheaper.

| Model | Price per million tokens (input / output) | Cost per typical question | 500 questions a month (about 20 a working day) |
| --- | --- | --- | --- |
| Claude Opus 5.5 (most capable) | $4 / $20 | about ₹6 to ₹10 | about ₹3,000 to ₹5,000 |
| Claude Sonnet 5.5 (faster, cheaper) | $2 / $10 | about ₹3 to ₹5 | about ₹1,500 to ₹2,500 |

These are estimates; the real figure shows in "AI activity" from the first week, and the cap stops any surprise. The model is a setting, not code, so it can be changed later without a release.

## MyERP for other AI tools (MCP server)

"Other AI can be used in the system" is read here as: a person can connect an AI app of their choice (Claude Desktop or claude.ai, other assistants that support MCP, or a company's own agent) and let it read MyERP data for them.

- MyERP publishes an **MCP server** at `https://<tenant address>/mcp`. MCP (Model Context Protocol) is an open standard most AI apps now support for connecting to outside systems.
- It offers **exactly the same tools** as the in-app assistant, with the same permission checks, company scope, row limits and logging. One tool list, two doors.
- **Login**: the person connects their AI app with "Sign in with MyERP" (OAuth, the standard MCP sign-in), which uses their normal MyERP login (Google). The app then acts as that person, inside that tenant only. Each connection appears on the person's profile as "Connected AI apps" and can be revoked; the Owner sees and can revoke all of them.
- **Read-only** in its first version, like the in-app assistant. No outside app can post, edit or delete.
- **Separate switch**: "Allow outside AI apps" per tenant (off by default) and a permission `ai.connect` per role. The Owner decides whether data may flow to AI apps MyERP does not control.
- The cost of outside AI apps is paid by whoever owns that app, not by MyERP; MyERP only logs the tool calls.
- The same tools can later back a plain REST API with personal API tokens, for scripts and BI tools.

## Phasing

Each line is one or more small pull requests, built only after Sidharth sees the one before.

| Step | What | Needs |
| --- | --- | --- |
| A1 | **Plumbing and first tools.** Tenant-side `ai` app (conversation, message, tool call, usage), `ai.ask` permission, tenant and company switches, monthly cap, Anthropic client with key from Secret Manager, chat panel ("Ask" in the top menu), tools over today's masters: companies, branches, ledger groups, ledgers with opening balances, opening bills, licences and certificates, change history. "AI activity" list for the Owner. User manual chapter "Ask MyERP". | Approval of this spec; an Anthropic API key |
| A2 | **Accounts tools**: trial balance, GL, day book, cash and bank book, ageing. | Phase 2 reports |
| A3 | **Stock, purchase and sales tools** as each module's reports land. "Top 10 customers" works from here. | Phases 3 and 4 |
| A4 | **Saved reports and charts**: "Save report", share with a role, bar/line/pie, Excel/CSV download, Home-page tiles from saved reports. | A1 |
| A4b | **Scheduled tasks**: schedule a saved report (daily, weekly, monthly), optional AI note, bell notification and email to the person's own address, "My scheduled tasks" list, re-check of permissions at each run. | A4 |
| A5 | **MCP server** for outside AI apps: OAuth sign-in, "Connected AI apps", tenant switch, `ai.connect` permission. | A1; answer to open question 6 |
| Later | Drafting features from the main plan (bill capture, bank matching, month-end note), each its own spec and switch. | Their module gates |

The main plan places "Ask your data" after the Phase 6 gate. This spec proposes building A1 now, alongside the masters work, because it is small, it is off the cutover path, and each module then adds its tools as it is built instead of all at the end. If Sidharth prefers, A1 can wait for Phase 2, when the answers become much more useful (open question 1).

## Tests (A1)

- A tool returns only rows of the current tenant (two tenants, same data shape).
- A person without `masters.view` is not offered the ledgers tool, and a forced call is refused.
- A company the person's role does not cover is refused.
- No tool writes: each tool runs under a check that fails on any INSERT, UPDATE or DELETE.
- Figures shown on screen equal the report screen's figures for the same filters.
- The cap stops calls at 100% and the alert fires at 80%.
- Every question and tool call is logged with tokens and cost.
- Claude calls are mocked in tests; a small, separate set of real questions (an evaluation set) is run by hand before each model or prompt change, with expected tools and filters.

## Open questions for Sidharth

1. **Start now or wait?** Build A1 now on masters (answers are limited until Accounts exists, but the plumbing is ready and each module adds tools as it goes), or wait until Phase 2 reports exist? Recommendation: now, as a small slice.
2. **Who may use it?** Proposed default: Owner and Accountant on; other roles off until you tick "AI assistant" for them on the Roles screen.
3. **Monthly budget** for the assistant for Apurvam (for example ₹3,000 or ₹5,000), and a daily limit per person?
4. **Model**: Claude Opus 5.5 (best answers, roughly double the cost) or Claude Sonnet 5.5 (faster and cheaper)? Recommendation: start on Opus 5.5 with the cap, look at real cost after a month, and switch if cost matters more.
5. **Data leaving India**: are you comfortable sending questions and report results (ledger names, balances, later customer and sales figures) to Anthropic's API for processing outside India, with no training on the data? Please check with your CA or legal adviser; the same question decides what we tell SaaS customers. Alternative: Claude through Google Cloud (Vertex AI), keeping billing in your Google account; it still runs outside India.
6. **Which "other AI"** do you have in mind: Claude Desktop or claude.ai, ChatGPT or Gemini, an agent of your own, or a BI tool? This decides how soon A5 (MCP server) is worth building and whether a plain API comes first.
7. **Should outside AI apps ever create drafts** (for example a draft sales order from an email)? Recommendation: read-only for now; drafts later, per tool, with their own switch.
8. **Scheduled tasks**: is delivery inside MyERP plus email to the person's own login enough, or do you want WhatsApp, or email to outside addresses (for example your CA)? Outside addresses would need an Owner approval per task.
9. **An Anthropic API account**: do you already have one (console.anthropic.com), or should it be set up under Apurvam's billing?
