"""
app/services/razorpay_service.py
────────────────────────────────────────────────────────────────────────────────
Thin wrapper around the Razorpay Python SDK. Every Razorpay API call lives here so
routers stay free of SDK details and credentials are read from the environment in
one place.

Environment (see .env):
  RAZORPAY_KEY_ID          public key id  (rzp_test_… in Test mode, rzp_live_… in Live)
  RAZORPAY_KEY_SECRET      secret key — never sent to the client
  RAZORPAY_WEBHOOK_SECRET  shared secret configured on the dashboard webhook

Flow reminder (Subscriptions):
  1. create_subscription() against a Razorpay plan_id → returns { id, short_url, … }.
  2. The client opens Checkout with that subscription id; the customer authorizes.
  3. Razorpay auto-charges each cycle and fires webhooks — the webhook is the
     source of truth for status, verified with verify_webhook_signature().
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

# Number of billing cycles Razorpay will attempt before a subscription completes.
# 120 ≈ 10 years of monthly billing — effectively "until cancelled" for our purposes.
_DEFAULT_TOTAL_COUNT = int(os.getenv("RAZORPAY_TOTAL_COUNT", "120"))


class RazorpayService:
    """Stateless wrapper — the underlying SDK client is created lazily on first use."""

    def __init__(self) -> None:
        self._client = None

    @property
    def key_id(self) -> str:
        return _KEY_ID

    @property
    def total_count(self) -> int:
        return _DEFAULT_TOTAL_COUNT

    def _get_client(self):
        """Build (once) and return the Razorpay SDK client."""
        if self._client is None:
            if not _KEY_ID or not _KEY_SECRET:
                raise RuntimeError(
                    "Razorpay is not configured. Set RAZORPAY_KEY_ID and "
                    "RAZORPAY_KEY_SECRET in the environment."
                )
            import razorpay  # imported lazily so the app boots even without the dep installed

            self._client = razorpay.Client(auth=(_KEY_ID, _KEY_SECRET))
            self._client.set_app_details({"title": "Axiora Pulse", "version": "1.0.0"})
        return self._client

    # ── Subscriptions ───────────────────────────────────────────────────────────

    def create_subscription(
        self,
        razorpay_plan_id: str,
        *,
        total_count: int | None = None,
        notes: dict | None = None,
        customer_notify: bool = True,
    ) -> dict:
        """Create a Razorpay subscription against a plan. Returns the raw SDK dict."""
        client = self._get_client()
        payload = {
            "plan_id": razorpay_plan_id,
            "total_count": total_count or _DEFAULT_TOTAL_COUNT,
            "customer_notify": 1 if customer_notify else 0,
        }
        if notes:
            payload["notes"] = notes
        logger.info("Creating Razorpay subscription for plan_id=%s", razorpay_plan_id)
        return client.subscription.create(payload)

    def fetch_subscription(self, subscription_id: str) -> dict:
        """Fetch the current state of a subscription from Razorpay (reconciliation)."""
        client = self._get_client()
        return client.subscription.fetch(subscription_id)

    def cancel_subscription(self, subscription_id: str, *, cancel_at_cycle_end: bool = True) -> dict:
        """Cancel a subscription, by default at the end of the current billing cycle."""
        client = self._get_client()
        logger.info(
            "Cancelling Razorpay subscription %s (cycle_end=%s)",
            subscription_id, cancel_at_cycle_end,
        )
        return client.subscription.cancel(
            subscription_id, {"cancel_at_cycle_end": 1 if cancel_at_cycle_end else 0}
        )

    # ── Signature verification ────────────────────────────────────────────────────

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """
        Verify the X-Razorpay-Signature header against the RAW request body using the
        webhook secret. MUST be given the exact bytes received — re-serialized JSON
        will not match the HMAC.
        """
        if not _WEBHOOK_SECRET:
            raise RuntimeError("RAZORPAY_WEBHOOK_SECRET is not configured.")
        client = self._get_client()
        try:
            client.utility.verify_webhook_signature(
                body.decode("utf-8"), signature, _WEBHOOK_SECRET
            )
            return True
        except Exception as exc:  # razorpay.errors.SignatureVerificationError
            logger.warning("Razorpay webhook signature verification failed: %s", exc)
            return False

    def verify_subscription_payment_signature(
        self, razorpay_payment_id: str, razorpay_subscription_id: str, razorpay_signature: str
    ) -> bool:
        """
        Verify the signature returned by Checkout's success handler for a subscription
        payment. Secondary confirmation only — never the source of truth.
        """
        client = self._get_client()
        try:
            client.utility.verify_subscription_payment_signature(
                {
                    "razorpay_payment_id": razorpay_payment_id,
                    "razorpay_subscription_id": razorpay_subscription_id,
                    "razorpay_signature": razorpay_signature,
                }
            )
            return True
        except Exception as exc:
            logger.warning("Razorpay subscription payment signature verification failed: %s", exc)
            return False


# Module-level singleton, matching the pattern of the other services.
razorpay_service = RazorpayService()
