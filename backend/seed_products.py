"""Run once to populate webshop products and create admin user."""
from app.database import SessionLocal
from app.models.order import WebshopProduct
from app.models.user import User, UserRole
from app.auth import get_password_hash

PRODUCTS = [
    ("Barbecue (3 stuks vlees)", 18.00, 13.00, "Barbecue"),
    ("Barbecue (2 stuks vlees)", 16.00, 11.00, "Barbecue"),
    ("Kinderoptie", 10.00, 5.00, "Barbecue"),
    ("Vegetarische Barbecue (3 stuks)", 18.00, 13.00, "Vegetarisch"),
    ("Vegetarische Barbecue (2 stuks)", 16.00, 11.00, "Vegetarisch"),
    ("Vegetarische Kinderoptie", 10.00, 5.00, "Vegetarisch"),
]

ADMIN_EMAIL = "admin@raakmillegem.be"
ADMIN_PASSWORD = "changeme"

db = SessionLocal()
try:
    for name, regular, member, category in PRODUCTS:
        if not db.query(WebshopProduct).filter(WebshopProduct.name == name).first():
            db.add(WebshopProduct(name=name, regular_price=regular, member_price=member, category=category, is_active=True))

    admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if not admin:
        admin = User(email=ADMIN_EMAIL, password_hash=get_password_hash(ADMIN_PASSWORD), is_active=True)
        db.add(admin)
        db.flush()
        db.add(UserRole(user_id=admin.id, role_code="ADMIN"))
        print(f"Admin created: email={ADMIN_EMAIL} password={ADMIN_PASSWORD} — change immediately!")

    db.commit()
    print("Seed done.")
finally:
    db.close()
