import csv
import io
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.member import Membership
from app.models.order import Order, OrderItem, WebshopProduct
from app.models.user import User
from app.schemas.order import OrderCreate, OrderResponse, ProductResponse
from app.services.email import send_order_confirmation

router = APIRouter(tags=["orders"])


def _next_confirmation_number(db: Session) -> str:
    year = date.today().year
    prefix = f"RM-{year}-"
    last = (
        db.query(Order)
        .filter(Order.confirmation_number.like(f"{prefix}%"))
        .order_by(Order.id.desc())
        .first()
    )
    if last:
        seq = int(last.confirmation_number.split("-")[-1]) + 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


@router.get("/products", response_model=List[ProductResponse])
def list_products(db: Session = Depends(get_db)):
    return db.query(WebshopProduct).filter(WebshopProduct.is_active == True).all()


@router.post("/orders", response_model=OrderResponse)
def create_order(data: OrderCreate, db: Session = Depends(get_db)):
    # Determine member status
    is_member = data.is_member
    if data.member_id and not is_member:
        membership = (
            db.query(Membership)
            .filter(
                Membership.member_id == data.member_id,
                Membership.year == date.today().year,
                Membership.is_active == True,
            )
            .first()
        )
        is_member = membership is not None

    total = 0
    order_items = []
    for item in data.items:
        product = db.query(WebshopProduct).filter(WebshopProduct.id == item.product_id).first()
        if not product or not product.is_active:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
        unit_price = float(product.member_price if is_member and product.member_price else product.regular_price)
        total += unit_price * item.quantity
        order_items.append((product, item.quantity, unit_price))

    confirmation_number = _next_confirmation_number(db)
    order = Order(
        confirmation_number=confirmation_number,
        member_id=data.member_id,
        customer_name=data.customer_name,
        customer_email=data.customer_email,
        is_member=is_member,
        total_amount=total,
        payment_status="PENDING",
        notes=data.notes,
    )
    db.add(order)
    db.flush()

    for product, qty, unit_price in order_items:
        db.add(OrderItem(order_id=order.id, product_id=product.id, quantity=qty, unit_price=unit_price))

    db.commit()
    db.refresh(order)

    try:
        send_order_confirmation(
            to_email=order.customer_email,
            name=order.customer_name,
            order=order,
        )
    except Exception:
        pass

    return order


@router.get("/orders", response_model=List[OrderResponse])
def list_orders(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return db.query(Order).order_by(Order.created_at.desc()).all()


@router.get("/orders/export")
def export_orders(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    orders = db.query(Order).order_by(Order.created_at.asc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Bevestigingsnummer", "Naam", "Email", "Lid", "Totaal", "Betaalstatus", "Datum", "Producten"])
    for order in orders:
        items_str = "; ".join(
            f"{item.quantity}x {item.product.name} (€{item.unit_price})"
            for item in order.items
        )
        writer.writerow([
            order.confirmation_number,
            order.customer_name,
            order.customer_email,
            "Ja" if order.is_member else "Nee",
            f"€{order.total_amount}",
            order.payment_status,
            order.created_at.strftime("%d/%m/%Y %H:%M"),
            items_str,
        ])
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bestellingen.csv"},
    )


@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post("/payments/webhook")
def mollie_webhook(db: Session = Depends(get_db)):
    # Mollie calls this endpoint after payment; real integration would verify the payment ID
    return {"status": "ok"}
