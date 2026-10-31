"""Load a realistic Brightloop book: catalog, customers, a year of billing history.

    python manage.py seed_demo                      # ~1,200 subscriptions
    python manage.py seed_demo --subscriptions 20000  # performance demo

History is generated with the same pricing engine and period arithmetic the
billing run uses, but written with bulk inserts so even large books load in
seconds. Deterministic (fixed random seed).
"""

import random
import time
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Customer, Role, User
from apps.catalog.models import PaymentTerm, Product, ProductVariant, RecurringPlan, Tax
from apps.core.models import Activity, OutboundEmail, Sequence
from apps.core.money import ZERO, q
from apps.core.periods import monthly_factor
from apps.core.pricing import DiscountRule, PricedLine, TaxRule, apply_discounts, compute_line
from apps.invoicing.models import (
    BillingRun,
    Invoice,
    InvoiceDiscount,
    InvoiceLine,
    Payment,
)
from apps.invoicing.services import bill_to, period_for
from apps.subscriptions.models import (
    Discount,
    QuotationTemplate,
    QuotationTemplateLine,
    Subscription,
    SubscriptionLine,
)

PASSWORDS = {
    "admin@brightloop.test": "Admin@12345",
    "staff@brightloop.test": "Staff@12345",
    "priya@acmeretail.test": "Customer@123",
}

FIRST = [
    "Aarav",
    "Diya",
    "Kabir",
    "Meera",
    "Rohan",
    "Ananya",
    "Vikram",
    "Isha",
    "Arjun",
    "Neha",
    "Karthik",
    "Pooja",
    "Siddharth",
    "Lakshmi",
    "Rahul",
    "Fatima",
    "Joseph",
    "Sneha",
    "Imran",
    "Gayatri",
    "Nikhil",
    "Tara",
    "Varun",
    "Zoya",
]
LAST = [
    "Sharma",
    "Iyer",
    "Nair",
    "Reddy",
    "Patel",
    "Menon",
    "Gupta",
    "Khan",
    "Das",
    "Pillai",
    "Rao",
    "Joshi",
    "Mehta",
    "Bose",
    "Kulkarni",
    "Fernandes",
    "Singh",
    "Thomas",
]
BIZ_A = [
    "Sunrise",
    "Lotus",
    "Blue Peak",
    "Coastal",
    "Evergreen",
    "Silverline",
    "Monsoon",
    "Saffron",
    "Northstar",
    "Banyan",
    "Indigo",
    "Granite",
    "Riverbend",
    "Cedar",
    "Harbor",
    "Orchid",
    "Summit",
    "Quartz",
    "Maple",
    "Kaveri",
    "Nilgiri",
    "Ashoka",
]
BIZ_B = [
    "Traders",
    "Retail",
    "Foods",
    "Logistics",
    "Clinics",
    "Textiles",
    "Studios",
    "Pharma",
    "Motors",
    "Builders",
    "Hospitality",
    "Tech",
    "Agro",
    "Exports",
    "Labs",
    "Furnishings",
    "Electricals",
    "Academy",
]
CITIES = [
    ("Bengaluru", "Karnataka"),
    ("Mumbai", "Maharashtra"),
    ("Chennai", "Tamil Nadu"),
    ("Hyderabad", "Telangana"),
    ("Pune", "Maharashtra"),
    ("Kochi", "Kerala"),
    ("Delhi", "Delhi"),
    ("Ahmedabad", "Gujarat"),
    ("Jaipur", "Rajasthan"),
    ("Kolkata", "West Bengal"),
    ("Coimbatore", "Tamil Nadu"),
    ("Mysuru", "Karnataka"),
]


class Command(BaseCommand):
    help = "Load demo data (wipes existing business data first)."

    def add_arguments(self, parser):
        parser.add_argument("--subscriptions", type=int, default=1200)
        parser.add_argument("--customers", type=int, default=None)
        parser.add_argument("--yes", action="store_true", help="Do not ask before wiping")

    def handle(self, *args, subscriptions=1200, customers=None, yes=False, **options):
        if not yes and Subscription.objects.exists():
            answer = input("This wipes all subscriptions, invoices and payments. Continue? [y/N] ")
            if answer.strip().lower() != "y":
                raise CommandError("Cancelled.")
        started = time.perf_counter()
        self.rng = random.Random(42)
        self.today = timezone.localdate()
        n_customers = customers or max(60, subscriptions // 3)
        with transaction.atomic():
            self.wipe()
            self.users()
            self.catalog()
            self.customers(n_customers)
            self.subscriptions(subscriptions)
            self.portal_story()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Customer.objects.count()} customers, {Subscription.objects.count()} "
                f"subscriptions, {Invoice.objects.count()} invoices, {Payment.objects.count()} "
                f"payments in {time.perf_counter() - started:.1f}s"
            )
        )
        for email, password in PASSWORDS.items():
            self.stdout.write(f"  {email:28} {password}")

    # ------------------------------------------------------------------ setup

    def wipe(self):
        for model in (
            Payment,
            InvoiceDiscount,
            InvoiceLine,
            Invoice,
            BillingRun,
            Discount,
            SubscriptionLine,
            Subscription,
            QuotationTemplateLine,
            QuotationTemplate,
            Customer,
            ProductVariant,
            Product,
            RecurringPlan,
            PaymentTerm,
            Tax,
            Activity,
            OutboundEmail,
            Sequence,
        ):
            model.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()

    def users(self):
        def make(email, name, role):
            user = User.objects.filter(email=email).first() or User(email=email)
            user.name, user.role, user.is_active = name, role, True
            user.set_password(PASSWORDS[email])
            user.save()
            return user

        self.admin = make("admin@brightloop.test", "Asha Admin", Role.ADMIN)
        self.staff = make("staff@brightloop.test", "Sam Sales", Role.STAFF)
        extra = [("Riya Accounts", "riya@brightloop.test"), ("Dev Support", "dev@brightloop.test")]
        self.team = [self.admin, self.staff]
        for name, email in extra:
            u = User(email=email, name=name, role=Role.STAFF)
            u.set_password("Staff@12345")
            u.save()
            self.team.append(u)

    def catalog(self):
        gst18 = Tax.objects.create(
            name="GST 18%", amount=Decimal("18"), description="CGST 9% + SGST 9%"
        )
        gst5 = Tax.objects.create(name="GST 5%", amount=Decimal("5"))
        Tax.objects.create(
            name="Digital services cess",
            computation=Tax.Computation.FIXED,
            amount=Decimal("2.00"),
            description="₹2 per unit",
            is_active=False,
        )
        self.terms = {
            0: PaymentTerm.objects.create(name="Immediate", due_days=0),
            15: PaymentTerm.objects.create(name="Net 15", due_days=15),
            30: PaymentTerm.objects.create(name="Net 30", due_days=30),
            45: PaymentTerm.objects.create(name="Net 45", due_days=45),
        }

        def product(name, kind, price, cost, notes, taxes=(gst18,), variants=()):
            p = Product.objects.create(
                name=name,
                product_type=kind,
                sales_price=Decimal(price),
                cost_price=Decimal(cost),
                notes=notes,
            )
            p.taxes.set(taxes)
            for attr, value, extra in variants:
                ProductVariant.objects.create(
                    product=p, attribute=attr, value=value, extra_price=Decimal(extra)
                )
            return p

        T = Product.Type
        self.p_crm = product(
            "Brightloop CRM seat",
            T.SOFTWARE,
            "1200",
            "180",
            "Per user, per billing period.",
            variants=[
                ("Brand", "Brightloop", "0"),
                ("Brand", "Odoo", "560"),
                ("Brand", "Zoho", "420"),
            ],
        )
        self.p_books = product(
            "Brightloop Books",
            T.SOFTWARE,
            "2500",
            "400",
            "Accounting with GST returns.",
            variants=[("Edition", "Standard", "0"), ("Edition", "Professional", "1500")],
        )
        self.p_storage = product(
            "Extra storage 100 GB", T.ADDON, "250", "60", "Switch on or off any time."
        )
        self.p_support = product(
            "Priority support", T.SERVICE, "3000", "1200", "4-hour response, named engineer."
        )
        self.p_analytics = product(
            "Analytics add-on", T.ADDON, "900", "150", "Dashboards and scheduled reports."
        )
        self.p_sms = product(
            "SMS pack (1,000)", T.ADDON, "350", "220", "Transactional SMS.", taxes=(gst5,)
        )
        self.p_onboard = product(
            "Onboarding workshop",
            T.SERVICE,
            "15000",
            "6000",
            "Remote setup and training, billed per workshop.",
        )
        self.p_legacy = product("Legacy POS licence", T.SOFTWARE, "800", "100", "Retired.")
        self.p_legacy.is_active = False
        self.p_legacy.save()

        start = self.today - timedelta(days=900)

        def plan(name, period, price, min_qty, **opts):
            p = RecurringPlan.objects.create(
                name=name,
                billing_period=period,
                price=Decimal(price),
                min_quantity=Decimal(min_qty),
                start_date=start,
                **opts,
            )
            p.taxes.set([gst18])
            return p

        P = RecurringPlan.Period
        self.plans = {
            "monthly": plan(
                "Monthly Standard",
                P.MONTHLY,
                "499",
                1,
                pausable=True,
                description="Small teams. Pause any time, cancel any time.",
            ),
            "growth": plan(
                "Quarterly Growth",
                P.MONTHLY,
                "1299",
                3,
                billing_interval=3,
                pausable=True,
                description="Billed every 3 months.",
            ),
            "annual": plan(
                "Annual Enterprise",
                P.YEARLY,
                "4999",
                10,
                auto_close=True,
                closable=False,
                description="12-month contract, closes at term end unless renewed.",
            ),
            "weekly": plan(
                "Weekly Pilot",
                P.WEEKLY,
                "199",
                1,
                auto_close=True,
                description="Short pilots for events and pop-ups.",
            ),
            "daily": plan(
                "Daily Kiosk", P.DAILY, "49", 1, pausable=True, description="Pay-per-day kiosks."
            ),
        }
        RecurringPlan.objects.create(
            name="Festive Season 2026",
            billing_period=P.MONTHLY,
            price=Decimal("299"),
            min_quantity=1,
            start_date=date(self.today.year, 9, 1),
            end_date=date(self.today.year, 11, 30),
            auto_close=True,
            description="Limited-time plan, sold only during the festive season.",
        )

        t1 = QuotationTemplate.objects.create(
            name="Enterprise annual bundle",
            validity_days=21,
            plan=self.plans["annual"],
            payment_term=self.terms[30],
            duration_months=12,
            notes="Includes onboarding and priority support. Prices exclude GST.",
        )
        for i, (prod, qty) in enumerate(
            [
                (self.p_crm, 25),
                (self.p_books, 1),
                (self.p_support, 1),
            ]
        ):
            QuotationTemplateLine.objects.create(
                template=t1, product=prod, quantity=qty, sequence=i
            )
        t2 = QuotationTemplate.objects.create(
            name="Starter monthly",
            validity_days=14,
            plan=self.plans["monthly"],
            payment_term=self.terms[0],
            notes="Cancel any time.",
        )
        for i, (prod, qty) in enumerate([(self.p_crm, 3), (self.p_storage, 1)]):
            QuotationTemplateLine.objects.create(
                template=t2, product=prod, quantity=qty, sequence=i
            )

        self.volume = Discount.objects.create(
            name="Volume: 10% off 20+ seats",
            code="SEATS20",
            kind=Discount.Kind.PERCENT,
            value=Decimal("10"),
            scope=Discount.Scope.PRODUCTS,
            min_quantity=Decimal("20"),
            created_by=self.admin,
        )
        self.volume.products.set([self.p_crm])
        launch = Discount.objects.create(
            name="Launch offer ₹500 off",
            code="LAUNCH500",
            kind=Discount.Kind.FIXED,
            value=Decimal("500"),
            scope=Discount.Scope.SUBSCRIPTION,
            min_purchase=Decimal("5000"),
            start_date=self.today - timedelta(days=10),
            end_date=self.today + timedelta(days=60),
            usage_limit=40,
            created_by=self.admin,
        )
        Discount.objects.create(
            name="Monsoon sale 15%",
            code="MONSOON15",
            kind=Discount.Kind.PERCENT,
            value=Decimal("15"),
            scope=Discount.Scope.SUBSCRIPTION,
            start_date=date(self.today.year, 6, 1),
            end_date=date(self.today.year, 8, 31),
            created_by=self.admin,
        )
        self.rules = [
            DiscountRule(
                self.volume.id,
                self.volume.name,
                "PERCENT",
                Decimal("10"),
                "PRODUCTS",
                frozenset({self.p_crm.id}),
                None,
                Decimal("20"),
            )
        ]
        self.launch = launch
        self.gst18 = gst18

    def customers(self, n):
        rows = []
        used = set()
        for i in range(n):
            first, last = self.rng.choice(FIRST), self.rng.choice(LAST)
            company = f"{self.rng.choice(BIZ_A)} {self.rng.choice(BIZ_B)}"
            if company in used:
                company = f"{company} {i}"
            used.add(company)
            city, state = self.rng.choice(CITIES)
            slug = company.lower().replace(" ", "")
            rows.append(
                Customer(
                    name=f"{first} {last}",
                    company=company,
                    email=f"{first.lower()}@{slug}.test",
                    phone=f"+91 9{self.rng.randint(100000000, 999999999)}",
                    address=f"{self.rng.randint(1, 220)}, {self.rng.choice(['MG Road', 'Park Street', 'Anna Salai', 'Linking Road', 'Residency Road', 'Banjara Hills'])}",  # noqa: E501
                    city=city,
                    state=state,
                    country="India",
                    tax_id=f"{self.rng.randint(10, 37)}ABCDE{self.rng.randint(1000, 9999)}"
                    f"F1Z{i % 10}",
                )
            )
        acme = Customer(
            name="Priya Raman",
            company="Acme Retail",
            email="priya@acmeretail.test",
            phone="+91 98450 12345",
            address="12, Brigade Road",
            city="Bengaluru",
            state="Karnataka",
            country="India",
            tax_id="29AACCA1234B1Z5",
        )
        rows.insert(0, acme)
        Customer.objects.bulk_create(rows, batch_size=1000)
        self.customer_list = list(Customer.objects.order_by("id"))
        self.acme = self.customer_list[0]

    # ------------------------------------------------------------------ history

    def subscriptions(self, n):
        rng, today = self.rng, self.today
        plan_weights = [
            ("monthly", 50),
            ("growth", 18),
            ("annual", 14),
            ("weekly", 6),
            ("daily", 4),
        ]
        keys = [k for k, w in plan_weights for _ in range(w)]
        line_choices = [
            self.p_crm,
            self.p_books,
            self.p_storage,
            self.p_support,
            self.p_analytics,
            self.p_sms,
        ]
        variants = {p.id: list(p.variants.all()) for p in line_choices}
        product_taxes = {
            p.id: [TaxRule(t.id, t.name, t.computation, t.amount) for t in p.taxes.all()]
            for p in line_choices
        }
        plan_tax = [TaxRule(self.gst18.id, self.gst18.name, "PERCENT", self.gst18.amount)]
        S = Subscription.Status

        subs, sub_lines_spec = [], []
        for i in range(n):
            plan = self.plans[rng.choice(keys)]
            customer = self.customer_list[rng.randrange(1, len(self.customer_list))]
            age = {"daily": 60, "weekly": 120}.get(self._key(plan), 430)
            start = today - timedelta(days=rng.randint(-20, age))
            roll = rng.random()
            if start > today:
                status = S.CONFIRMED if roll < 0.6 else S.QUOTATION
            elif roll < 0.05:
                status = S.DRAFT
            elif roll < 0.11:
                status = S.QUOTATION
            elif roll < 0.21:
                status = S.CLOSED
            elif roll < 0.25 and plan.pausable:
                status = S.PAUSED
            else:
                status = S.ACTIVE
            expiry = None
            if plan.billing_period == "YEARLY":
                expiry = start.replace(year=start.year + 1) - timedelta(days=1)
            elif self._key(plan) == "weekly":
                expiry = start + timedelta(weeks=rng.choice([4, 8, 12])) - timedelta(days=1)
            elif rng.random() < 0.3:
                expiry = start + timedelta(days=rng.choice([180, 365])) - timedelta(days=1)
            if status == S.ACTIVE and expiry and expiry < today and plan.auto_close:
                status = S.CLOSED
            closed_at = None
            close_reason = ""
            if status == S.CLOSED:
                if expiry and expiry < today and (plan.auto_close or rng.random() < 0.5):
                    closed_at, close_reason = expiry + timedelta(days=1), "Expired"
                else:
                    lo = min(start + timedelta(days=20), today)
                    closed_at = lo + timedelta(days=rng.randint(0, max((today - lo).days, 0)))
                    close_reason = rng.choice(
                        ["Moved to a competitor", "Budget cuts", "Business closed", "Switched plan"]
                    )
            paused_at = None
            if status == S.PAUSED:
                paused_at = today - timedelta(days=rng.randint(3, 40))
                paused_at = max(paused_at, start)
            term = self.terms[rng.choice([0, 15, 15, 30, 30, 45])]
            sub = Subscription(
                number=f"SUB/{i + 1:05d}",
                customer=customer,
                plan=plan,
                status=status,
                start_date=start,
                expiry_date=expiry,
                payment_term=term,
                salesperson=rng.choice(self.team),
                closed_at=closed_at,
                close_reason=close_reason,
                paused_at=paused_at,
                created_by=self.staff,
                created_at=timezone.make_aware(
                    timezone.datetime.combine(
                        min(start - timedelta(days=rng.randint(3, 25)), today),
                        timezone.datetime.min.time(),
                    )
                ),
            )
            if status in (S.QUOTATION,):
                sub.quotation_sent_at = timezone.now() - timedelta(days=rng.randint(0, 20))
                sub.quotation_valid_until = today + timedelta(days=rng.randint(-5, 25))
            if status in (S.CONFIRMED, S.ACTIVE, S.PAUSED, S.CLOSED):
                sub.confirmed_at = sub.created_at + timedelta(days=2)
            if status in (S.ACTIVE, S.PAUSED, S.CLOSED):
                sub.activated_at = timezone.make_aware(
                    timezone.datetime.combine(start, timezone.datetime.min.time())
                )
            # Lines: plan fee (seats) plus 0-3 add-ons.
            short = plan.billing_period in ("DAILY", "WEEKLY")
            seat_choices = [1, 2, 3] if short else [1, 2, 3, 5, 8, 12, 25, 40]
            seats = Decimal(max(int(plan.min_quantity), rng.choice(seat_choices)))
            spec = [
                (
                    None,
                    None,
                    f"{plan.name} plan ({plan.billing_label})",
                    seats,
                    plan.price,
                    plan_tax,
                )
            ]
            if short:
                addons = [self.p_sms] if rng.random() < 0.3 else []
            else:
                addons = rng.sample(line_choices, rng.randint(0, 3))
            for prod in addons:
                var = rng.choice(variants[prod.id]) if variants[prod.id] else None
                qty = seats if prod is self.p_crm else Decimal(rng.choice([1, 1, 2, 5]))
                price = prod.sales_price + (var.extra_price if var else ZERO)
                desc = prod.name + (f" ({var.attribute}: {var.value})" if var else "")
                spec.append((prod, var, desc, qty, price, product_taxes[prod.id]))
            subs.append(sub)
            sub_lines_spec.append(spec)

        # Totals per subscription
        for sub, spec in zip(subs, sub_lines_spec, strict=True):
            untaxed = tax = ZERO
            for _prod, _var, _d, qty, price, taxes in spec:
                r = compute_line(qty, price, taxes)
                untaxed += r.net
                tax += r.tax
            sub.untaxed_amount, sub.tax_amount, sub.total = untaxed, tax, untaxed + tax
            sub.mrr = q(
                untaxed * monthly_factor(sub.plan.billing_period, sub.plan.billing_interval)
            )
        Subscription.objects.bulk_create(subs, batch_size=1000)
        subs = list(
            Subscription.objects.select_related("plan", "payment_term", "customer").order_by("id")
        )

        lines, line_taxes = [], []
        tax_map = {t.id: t for t in Tax.objects.all()}
        for sub, spec in zip(subs, sub_lines_spec, strict=True):
            for seq, (prod, var, desc, qty, price, taxes) in enumerate(spec):
                r = compute_line(qty, price, taxes)
                lines.append(
                    SubscriptionLine(
                        subscription=sub,
                        product=prod,
                        variant=var,
                        description=desc,
                        quantity=qty,
                        unit_price=price,
                        subtotal=r.net,
                        tax_amount=r.tax,
                        total=r.total,
                        sequence=seq,
                    )
                )
                line_taxes.append([tax_map[t.id] for t in taxes])
        SubscriptionLine.objects.bulk_create(lines, batch_size=2000)
        through = SubscriptionLine.taxes.through
        through.objects.bulk_create(
            [
                through(subscriptionline_id=ln.id, tax_id=t.id)
                for ln, taxes in zip(lines, line_taxes, strict=True)
                for t in taxes
            ],
            batch_size=5000,
        )

        self._history(subs, sub_lines_spec)

    @staticmethod
    def _key(plan):
        return {
            "Monthly Standard": "monthly",
            "Quarterly Growth": "growth",
            "Annual Enterprise": "annual",
            "Weekly Pilot": "weekly",
            "Daily Kiosk": "daily",
        }.get(plan.name, "")

    def _history(self, subs, specs):
        rng, today = self.rng, self.today
        S = Subscription.Status
        invoices, inv_lines, inv_discounts, payments, next_dates = [], [], [], [], {}
        for sub, spec in zip(subs, specs, strict=True):
            if sub.status not in (S.ACTIVE, S.PAUSED, S.CLOSED):
                continue
            stop = today
            if sub.status == S.CLOSED:
                stop = min(stop, sub.closed_at - timedelta(days=1))
            if sub.status == S.PAUSED:
                stop = min(stop, sub.paused_at - timedelta(days=1))
            start = sub.start_date
            per_sub = []
            while start <= stop and (sub.expiry_date is None or start <= sub.expiry_date):
                period = period_for(sub, start)
                priced = [
                    PricedLine(i, s[0].id if s[0] else None, s[3], q(s[3] * s[4] * period.factor))
                    for i, s in enumerate(spec)
                ]
                applied = apply_discounts(priced, self.rules)
                inv = Invoice(
                    subscription=sub,
                    customer=sub.customer,
                    status=Invoice.Status.CONFIRMED,
                    invoice_date=period.start,
                    due_date=period.start + timedelta(days=sub.payment_term.due_days),
                    period_start=period.start,
                    period_end=period.end,
                    payment_term=sub.payment_term.name,
                    bill_to=bill_to(sub.customer),
                    created_by=self.staff,
                    confirmed_at=timezone.make_aware(
                        timezone.datetime.combine(period.start, timezone.datetime.min.time())
                    ),
                )
                inv_rows = []
                totals = [ZERO, ZERO, ZERO, ZERO]
                for (prod, _v, desc, qty, price, taxes), p in zip(spec, priced, strict=True):
                    r = compute_line(qty, price, taxes, discount=p.discount, factor=period.factor)
                    if period.prorated:
                        desc = f"{desc} (prorated {period.factor * 100:.1f}%)"
                    inv_rows.append(
                        dict(
                            product=prod,
                            description=desc[:300],
                            quantity=qty,
                            unit_price=price,
                            gross_amount=r.gross,
                            discount_amount=r.discount,
                            subtotal=r.net,
                            tax_amount=r.tax,
                            total=r.total,
                            taxes=r.tax_breakdown,
                        )
                    )
                    totals[0] += r.gross
                    totals[1] += r.discount
                    totals[2] += r.tax
                    totals[3] += r.total
                (inv.untaxed_amount, inv.discount_amount, inv.tax_amount, inv.total) = totals
                inv.amount_due = inv.total
                per_sub.append((inv, inv_rows, applied))
                start = period.next_start
            next_dates[sub.id] = start
            invoices.extend(per_sub)

        # Number invoices in date order, as a real book would be.
        invoices.sort(key=lambda t: (t[0].invoice_date, t[0].subscription_id))
        counters: dict[int, int] = {}
        for inv, _rows, _applied in invoices:
            y = inv.invoice_date.year
            counters[y] = counters.get(y, 0) + 1
            inv.number = f"INV/{y}/{counters[y]:05d}"
        # A handful of recent ones are still drafts waiting for review.
        recent = [t for t in invoices if (today - t[0].invoice_date).days <= 3]
        for inv, _r, _a in recent[: max(3, len(recent) // 6)]:
            inv.status, inv.number, inv.confirmed_at = Invoice.Status.DRAFT, None, None
        Invoice.objects.bulk_create([t[0] for t in invoices], batch_size=1000)
        for y, count in counters.items():
            Sequence.objects.update_or_create(
                code=f"invoice-{y}",
                defaults={"prefix": f"INV/{y}/", "padding": 5, "next_number": count + 1},
            )
        Sequence.objects.update_or_create(
            code="subscription",
            defaults={"prefix": "SUB/", "padding": 5, "next_number": len(subs) + 1},
        )

        for inv, rows, applied in invoices:
            for seq, row in enumerate(rows):
                inv_lines.append(InvoiceLine(invoice=inv, sequence=seq, **row))
            for rule, amount in applied:
                inv_discounts.append(
                    InvoiceDiscount(invoice=inv, discount_id=rule.id, name=rule.name, amount=amount)
                )
        InvoiceLine.objects.bulk_create(inv_lines, batch_size=2000)
        InvoiceDiscount.objects.bulk_create(inv_discounts, batch_size=2000)

        # Payments: most are paid, some late, some partial, some overdue.
        methods = ["BANK_TRANSFER"] * 5 + ["UPI"] * 4 + ["CARD"] * 3 + ["CHEQUE", "CASH"]
        to_update = []
        for inv, _rows, _applied in invoices:
            if inv.status != Invoice.Status.CONFIRMED or inv.total <= 0:
                continue
            overdue_by = (today - inv.due_date).days
            roll = rng.random()
            if overdue_by > 0:
                full, partial = (0.96, 0.02) if overdue_by > 45 else (0.8, 0.08)
            else:
                full, partial = 0.35, 0.05
            if roll < full:
                amount = inv.total
            elif roll < full + partial:
                amount = q(inv.total * Decimal(rng.choice(["0.25", "0.5", "0.6"])))
            else:
                continue
            latest = min(today, inv.due_date + timedelta(days=10))
            span = max((latest - inv.invoice_date).days, 0)
            pay_date = inv.invoice_date + timedelta(days=rng.randint(0, span))
            method = rng.choice(methods)
            payments.append(
                Payment(
                    invoice=inv,
                    customer_id=inv.customer_id,
                    method=method,
                    amount=amount,
                    payment_date=pay_date,
                    reference=f"TXN{rng.randint(10**8, 10**9 - 1)}",
                    recorded_by=rng.choice(self.team),
                )
            )
            inv.amount_paid = amount
            inv.amount_due = inv.total - amount
            if inv.amount_due == 0:
                inv.status = Invoice.Status.PAID
                inv.paid_at = timezone.make_aware(
                    timezone.datetime.combine(pay_date, timezone.datetime.min.time())
                )
            to_update.append(inv)
        Payment.objects.bulk_create(payments, batch_size=2000)
        Invoice.objects.bulk_update(
            to_update, ["amount_paid", "amount_due", "status", "paid_at"], batch_size=1000
        )
        # Overdue invoices that already got a reminder.
        for inv in Invoice.objects.filter(
            status=Invoice.Status.CONFIRMED, due_date__lt=today - timedelta(days=10)
        )[:200]:
            inv.reminder_count = 1
            inv.last_reminder_at = timezone.now() - timedelta(days=rng.randint(1, 6))
            inv.save(update_fields=["reminder_count", "last_reminder_at"])

        updates = []
        for sub in subs:
            if sub.id in next_dates:
                sub.next_invoice_date = next_dates[sub.id]
                updates.append(sub)
        Subscription.objects.bulk_update(updates, ["next_invoice_date"], batch_size=1000)
        BillingRun.objects.create(
            as_of=today - timedelta(days=1),
            trigger=BillingRun.Trigger.SCHEDULED,
            subscriptions_processed=len(updates),
            invoices_created=len(invoices),
            total_amount=sum((t[0].total for t in invoices), ZERO),
            duration_ms=0,
        )

    # ------------------------------------------------------------------ portal story

    def portal_story(self):
        """A customer with a portal login and something to do in it."""
        from apps.subscriptions import services as subs

        user = User(email="priya@acmeretail.test", name="Priya Raman", role=Role.CUSTOMER)
        user.set_password(PASSWORDS["priya@acmeretail.test"])
        user.save()
        self.acme.user = user
        self.acme.save(update_fields=["user"])
        today = self.today
        # An active monthly subscription with history, billed by the real engine.
        start = today - timedelta(days=75)
        active = subs.create_subscription(
            customer=self.acme,
            plan=self.plans["monthly"],
            start_date=start,
            lines=[
                {
                    "product": None,
                    "description": "Monthly Standard plan (every month)",
                    "quantity": Decimal(22),
                    "unit_price": self.plans["monthly"].price,
                    "taxes": [self.gst18],
                },
                {
                    "product": self.p_crm,
                    "variant": self.p_crm.variants.get(value="Odoo"),
                    "quantity": Decimal(22),
                },
                {"product": self.p_storage, "quantity": Decimal(2)},
            ],
            payment_term=self.terms[15],
            actor=self.staff,
        )
        subs.send_quotation(active, self.staff, email=False)
        subs.confirm(active, self.staff, accepted_by_name="Priya Raman")
        from apps.invoicing import services as billing

        invs = []
        while True:
            active.refresh_from_db()
            if active.next_invoice_date > today:
                break
            invs.append(billing.bill_next_period(active, actor=self.staff, confirm_now=True))
        if invs:
            billing.record_payment(
                invs[0],
                amount=invs[0].amount_due,
                method="UPI",
                payment_date=invs[0].invoice_date + timedelta(days=3),
                actor=self.staff,
            )
        if len(invs) > 1:
            billing.record_payment(
                invs[1],
                amount=q(invs[1].amount_due / 2),
                method="CARD",
                payment_date=min(today, invs[1].invoice_date + timedelta(days=5)),
                actor=self.staff,
            )
        # A quotation waiting for Priya to accept online.
        template = QuotationTemplate.objects.get(name="Enterprise annual bundle")
        quote = subs.create_subscription(
            customer=self.acme,
            plan=template.plan,
            template=template,
            start_date=today + timedelta(days=7),
            actor=self.staff,
        )
        subs.send_quotation(quote, self.staff, email=True)
