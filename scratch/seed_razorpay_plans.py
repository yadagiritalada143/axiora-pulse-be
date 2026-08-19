"""
scratch/seed_razorpay_plans.py
────────────────────────────────────────────────────────────────────────────────
One-off helper: create the Razorpay Plans for each local plan and back-fill the
`plans.razorpay_plan_id_monthly / _yearly` columns.

For every active local plan with a non-zero price, this creates a monthly and a
yearly Razorpay Plan (amount = rupees × 100, in paise) and stores the returned
`plan_...` ids on the row. It is idempotent: a column that is already filled is
skipped, so re-running it only fills the gaps.

Prerequisites (see the runbook):
  1. RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET set to your **Test** keys in .env.
  2. DATABASE_URL pointing at the DB where migration 0022 has been applied
     (a LOCAL/staging DB — never prod).

Run from the backend repo root:
    .venv/Scripts/python.exe scratch/seed_razorpay_plans.py
Add --dry-run to preview without calling Razorpay or writing to the DB.
"""
import asyncio
import os
import sys

# Ensure the repo root is importable when run as a plain script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.db.database import AsyncSessionLocal, engine  # noqa: E402
from app.db.models import Plan  # noqa: E402
from app.services.razorpay_service import razorpay_service  # noqa: E402

DRY_RUN = "--dry-run" in sys.argv

# period name → (db column, human suffix)
PERIODS = (
    ("monthly", "razorpay_plan_id_monthly", "Monthly"),
    ("yearly", "razorpay_plan_id_yearly", "Yearly"),
)


def _create_plan(plan: Plan, period: str, label: str, amount_rupees: int) -> str:
    """Create one Razorpay Plan and return its id."""
    amount_paise = amount_rupees * 100
    payload = {
        "period": period,          # "monthly" | "yearly"
        "interval": 1,
        "item": {
            "name": f"{plan.name} ({label})",
            "amount": amount_paise,
            "currency": plan.currency or "INR",
            "description": plan.description or plan.name,
        },
        "notes": {"plan_code": plan.code, "billing_period": period},
    }
    if DRY_RUN:
        print(f"  [dry-run] would create {period} plan: {payload['item']['name']} "
              f"= {amount_paise} paise")
        return f"plan_DRYRUN_{plan.code}_{period}"

    client = razorpay_service._get_client()  # noqa: SLF001 (one-off script)
    created = client.plan.create(payload)
    print(f"  created {period} plan → {created['id']} "
          f"({payload['item']['name']}, {amount_paise} paise)")
    return created["id"]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        plans = (
            await db.execute(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.tier))
        ).scalars().all()

        if not plans:
            print("No active plans found. Did migration 0022 run against this DATABASE_URL?")
            return

        for plan in plans:
            print(f"\nPlan '{plan.code}' ({plan.name}):")
            for period, column, label in PERIODS:
                amount_rupees = plan.price_monthly if period == "monthly" else plan.price_yearly
                if amount_rupees <= 0:
                    print(f"  {period}: price is 0 — free tier, skipping (no Razorpay plan).")
                    continue
                if getattr(plan, column):
                    print(f"  {period}: already set ({getattr(plan, column)}) — skipping.")
                    continue
                plan_id = _create_plan(plan, period, label, amount_rupees)
                setattr(plan, column, plan_id)

        if DRY_RUN:
            print("\n[dry-run] no changes committed.")
        else:
            await db.commit()
            print("\n✓ Committed razorpay_plan_id_* back to the plans table.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
