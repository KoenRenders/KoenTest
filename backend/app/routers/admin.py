from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin, get_password_hash
from app.database import get_db
from app.models.activity import Activity, Registration
from app.models.family import Family, Membership
from app.models.idea import Idea
from app.models.order import Order, WebshopProduct, PaymentStatusEnum
from app.models.user import AdminUser
from app.schemas.auth import AdminUserResponse
from app.schemas.order import ProductResponse

router = APIRouter(tags=["admin"])


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    today = date.today()
    return {
        "families": db.query(func.count(Family.id)).scalar(),
        "active_members": db.query(func.count(Membership.id))
            .filter(Membership.year == today.year, Membership.is_active == True)
            .scalar(),
        "upcoming_activities": db.query(func.count(Activity.id))
            .filter(Activity.date >= today, Activity.is_archived == False)
            .scalar(),
        "open_ideas": db.query(func.count(Idea.id))
            .filter(Idea.is_reviewed == False)
            .scalar(),
        "pending_orders": db.query(func.count(Order.id))
            .filter(Order.payment_status == PaymentStatusEnum.pending)
            .scalar(),
    }


@router.get("/product-totals")
def get_product_totals(
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    from app.models.order import OrderItem
    results = (
        db.query(
            WebshopProduct.name,
            func.sum(OrderItem.quantity).label("total_quantity"),
            func.sum(OrderItem.quantity * OrderItem.unit_price).label("total_revenue"),
        )
        .join(OrderItem, OrderItem.product_id == WebshopProduct.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.payment_status == PaymentStatusEnum.paid)
        .group_by(WebshopProduct.id, WebshopProduct.name)
        .all()
    )
    return [
        {"product": r.name, "quantity": int(r.total_quantity or 0), "revenue": float(r.total_revenue or 0)}
        for r in results
    ]


@router.post("/products", response_model=ProductResponse)
def create_product(
    data: ProductResponse,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    product = WebshopProduct(
        name=data.name,
        regular_price=data.regular_price,
        member_price=data.member_price,
        category=data.category,
        is_active=data.is_active,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.post("/seed-admin")
def seed_admin(db: Session = Depends(get_db)):
    existing = db.query(AdminUser).filter(AdminUser.username == "admin").first()
    if existing:
        raise HTTPException(status_code=400, detail="Admin already exists")
    user = AdminUser(username="admin", hashed_password=get_password_hash("changeme"))
    db.add(user)
    db.commit()
    return {"detail": "Admin created with username=admin password=changeme — change immediately!"}
