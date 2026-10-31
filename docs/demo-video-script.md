# Demo video script — Brightloop Subscription Management System

**Length:** about 6 minutes (a 2-minute cut is at the end).
**Format per scene:** what to show on screen → what to say.

---

## Before you record

1. Reset the demo data so every story is fresh (the quotation is unaccepted and the overdue invoice is unpaid):
   ```bash
   cd backend
   uv run python manage.py seed_demo --yes
   ```
2. Start both servers (`runserver 127.0.0.1:8000` in `backend/`, `npm run dev` in `frontend/`) and open http://127.0.0.1:5173.
3. Browser at 1440×900 or larger, zoom 100 %, dark mode on (moon icon, top right). Close other tabs and notifications.
4. Keep this open in a second window: admin `admin@brightloop.test` / `Admin@12345`, customer `priya@acmeretail.test` / `Customer@123`.
5. Rehearse once: the clicks below assume the seeded data.

---

## Scene 1 — The problem (0:00–0:30)

**Screen:** Login page (the left panel lists the four promises).

> "Brightloop sells software on subscription. Today their subscriptions live in a spreadsheet, renewals are remembered by whoever notices, invoices are typed by hand and payments are matched by scrolling bank statements. Nobody can say how much recurring revenue they actually have.
> We built one platform that runs the whole subscription business — from plans and quotations to billing day, payments and the finance view."

---

## Scene 2 — Sign-up, security and roles (0:30–1:10)

**Screen:** Click **Create an account**. Type a name and email, then type a weak password slowly, e.g. `brightloop`, and watch the checklist; then change it to `Brightloop#26`.

> "A new customer signs up with their email. Each email can belong to only one account, and the password has to be more than eight characters with an uppercase letter, a lowercase letter and a special character — checked as you type, and enforced again on the server."

**Screen:** Go back, click **Forgot password?**, enter `priya@acmeretail.test`, **Send reset link**.

> "If they forget it, a one-time reset link arrives at their registered email, valid for 24 hours. We'll see that email later in the outbox."

**Screen:** Sign in as admin (use the **Admin** demo button, then **Sign in**). Point at the sidebar.

> "Not everyone sees the same thing. The admin controls everything, internal staff do the day-to-day work with limited access, and customers get a portal with only their own subscriptions and invoices. Only the admin can add staff — that's the Team page here."

---

## Scene 3 — The dashboard (1:10–1:50)

**Screen:** Dashboard. Hover a point on the chart. Change **This month** to **Last 12 months**, then pick a plan in **All plans**, then set both back.

> "This is the finance lead's month-end view, live. Active subscriptions, monthly recurring revenue and ARR, what we collected against what we invoiced, and what is overdue. The chart compares invoiced and collected over twelve months, and receivables ageing shows how old the unpaid money is. Everything filters by period and by plan."

**Screen:** Point at the footer, bottom right (e.g. `GET /api/reports/dashboard/ · 40ms`).

> "The brief asked for every page under two seconds with thousands of subscriptions. This book has twelve hundred subscriptions and six thousand invoices, and the footer shows the server time of every request. A test loads three thousand subscriptions and fails if any page takes two seconds."

---

## Scene 4 — Launching a plan (1:50–2:30)

**Screen:** **Products** → point at *Brightloop CRM seat* and its variants → click **Edit** to show the variant rows, then **Cancel**.

> "The admin sets up products with a type, sales price, cost price — so we see the margin — and notes. Products come in variants: choosing the Odoo brand adds 560 to the price."

**Screen:** **Recurring plans** → point at *Annual Enterprise* and *Monthly Standard* rule lists.

> "Plans decide how often we bill — daily, weekly, monthly or yearly — the minimum quantity, and the dates the plan is on sale. And the admin decides plan by plan what customers may do: Annual Enterprise closes on its own at the end of the contract and can't be closed early; Monthly Standard can be paused or closed any time."

---

## Scene 5 — Quote to subscription (2:30–3:30)

**Screen:** **Subscriptions** → point at the status tabs and counts → **New subscription**. Search a customer (e.g. type `Sunrise`, pick one) → **Quotation template**: *Enterprise annual bundle* → **Create draft**.

> "A sales rep is preparing an offer for a large customer. Instead of building it from scratch, they start from a quotation template that already has the plan, the product lines, the payment terms and how long the quote stays valid."

**Screen:** On the new draft, point at the lines, the totals, and **First invoice preview**.

> "We get a numbered subscription with the customer, plan, start and expiry dates, payment terms and lines — product, quantity, unit price, taxes and amount. The plan's base fee was added automatically. And this preview shows the first invoice before it exists — including two discounts that will apply by themselves."

**Screen:** Click **Send quotation** → **Confirm**. Point at the stepper as it moves to *Active*, then at the **Timeline** card.

> "Draft, quotation, confirmed, active — anyone on the team can see exactly where it stands and who moved it. Every step is on the timeline."

---

## Scene 6 — Billing day (3:30–4:20)

**Screen:** **Billing runs**. Point at the preview numbers and rows, then **Billing health check**.

> "It's billing day. Nobody types invoices. The preview is a dry run: it shows exactly which subscriptions are due, which periods, which discounts apply and the total — without writing anything."

**Screen:** **Run billing** → **Create … invoice(s)**. Point at the green "Run complete" panel and the preview now saying *Nothing to bill*.

> "One click creates them all, with customer details, lines, taxes and totals filled in. Run it again and nothing happens — the database allows only one live invoice per subscription period, so nothing is ever billed twice. The health check re-derives every period of every subscription and shows a green shield when nothing was skipped."

**Screen:** Click **View the new invoices** → open one → point at **Send**, **Print**, **PDF**.

> "Each invoice can be confirmed, cancelled, emailed with a PDF attached, or printed. It moves from draft to confirmed to paid."

---

## Scene 7 — Discounts and payments (4:20–5:05)

**Screen:** **Discounts** → point at *Volume: 10% off 20+ seats*: conditions, usage and *Given* columns.

> "Only the admin creates discount rules: a percentage or a fixed amount, a minimum quantity or purchase, start and end dates, and a usage limit. They apply to specific products or to whole subscriptions. Once a rule applies, it appears on the next invoice on its own, and it stops when it expires or runs out."

**Screen:** **Invoices** → **Unpaid** tab → open one → **Register payment** → change the amount to roughly half → method *UPI* → **Record payment**. Then **Register payment** again with the rest → status becomes **Paid**.

> "Payments arrive by different methods on different days. Each is recorded with its method, amount, date and a note, against the right invoice. Part payments are fine — the balance updates — and when it reaches zero the invoice is paid and the customer gets a receipt."

**Screen:** Back to **Invoices** → click the **Overdue** tab.

> "At any moment the team sees what's paid, what's outstanding and what's overdue, with days late — and overdue invoices get an automatic reminder every week."

---

## Scene 8 — The customer's side (5:05–5:45)

**Screen:** Sign out → sign in as **Customer** (Priya). Point at the quotation banner and the overdue banner.

> "Now the customer. Priya from Acme Retail sees only her own account: a quotation waiting for her, and an overdue invoice."

**Screen:** **Review & accept** → **Accept quotation** → type `Priya Raman` → **I accept**. Then **Home** → **Pay now** → open the overdue invoice → **Pay** → **UPI** → **Pay ₹…** → status **Paid**.

> "She accepts the quotation online by signing with her name, and pays the overdue invoice in two clicks — no emails back and forth. She can pause, renew or close subscriptions herself, as far as her plan allows, and download every invoice as a PDF."

---

## Scene 9 — Behind the scenes and close (5:45–6:15)

**Screen:** Sign in as admin → **Email outbox** → open the *Reset your password* email, then an *Invoice* email with the PDF attachment. Press **Ctrl + K**, type `acme`, press Enter.

> "Every email the platform sent is in the outbox: the reset link from earlier, quotations, invoices with PDFs, receipts and reminders. Ctrl+K finds any subscription, customer or invoice instantly."

**Screen:** Back to the **Dashboard**.

> "Plans, quotations, subscriptions, automated billing, discounts, payments and a live finance view — in one place. Money is exact to the paisa, every action is audited, and seventy automated tests run on SQLite and PostgreSQL. Brightloop finally knows how much recurring revenue it has. Thank you."

---

## 2-minute cut

| Time | Show | Say (short) |
|---|---|---|
| 0:00 | Login page | "Brightloop runs its subscription business on spreadsheets. We replaced that with one platform." |
| 0:10 | Dashboard, footer timing | "Live MRR, collections and overdue, every page under two seconds." |
| 0:30 | New subscription from template → Send quotation → Confirm | "Quotes start from templates and move Draft → Quotation → Confirmed → Active." |
| 0:55 | Billing runs → Run billing → health check | "Billing day is one click; nothing billed twice, nothing skipped." |
| 1:20 | Invoice → Register payment → Paid | "Payments by any method, partial or full, against the right invoice." |
| 1:40 | Priya's portal → accept quote, pay invoice | "Customers self-serve in their own portal." |
| 1:55 | Dashboard | "One place for the whole subscription business." |

## Recording tips

- Record at 1080p or higher; move the mouse slowly and pause one second after each click.
- Re-run `seed_demo --yes` before every take so the data matches this script.
- Wait for charts to finish animating before talking about them.
- If something looks different, invoice and subscription numbers change when you create new ones — pick any row in the same tab.
