from app.config import settings


def create_mollie_payment(order_id: int, amount: float, description: str, redirect_url: str) -> dict:
    """Stub for Mollie payment creation. Replace with actual Mollie API calls."""
    return {
        "payment_id": f"tr_stub_{order_id}",
        "checkout_url": redirect_url,
    }
