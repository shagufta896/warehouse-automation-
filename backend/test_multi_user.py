from sqlalchemy.orm import Session
from app.database.database import SessionLocal, current_tenant_id
from app.database.models import User, Product
import uuid

def test_multi_user():
    db = SessionLocal()
    try:
        # Get users
        u1 = db.query(User).filter(User.email == 'koushikp72@gmail.com').first()
        u2 = db.query(User).filter(User.email == 'paulkoushik786@gmail.com').first()
        
        if not u1 or not u2:
            print("Users not found")
            return

        print(f"User 1: {u1.id}")
        print(f"User 2: {u2.id}")

        # Try to insert product for User 2 with same product_id as User 1
        # User 1 has 50 products, let's pick one
        p1 = db.query(Product).filter(Product.user_id == u1.id).first()
        if not p1:
            print("User 1 has no products")
            return
        
        pid = p1.product_id
        print(f"Testing with Product ID: {pid}")

        # Set tenant to User 2
        current_tenant_id.set(u2.id)
        print(f"Tenant set to: {current_tenant_id.get()}")

        # Check if User 2 sees User 1's product (should NOT)
        p_check = db.query(Product).filter(Product.product_id == pid).first()
        if p_check:
            print(f"ERROR: User 2 sees product from User 1! Owner: {p_check.user_id}")
        else:
            print("SUCCESS: User 2 does not see User 1's product")

        # Try to insert for User 2
        try:
            new_p = Product(
                product_id=pid,
                product_name="User 2 Version",
                category="Test",
                current_stock=10,
                selling_price=100.0
            )
            db.add(new_p)
            db.commit()
            print(f"SUCCESS: User 2 inserted product with same ID {pid}")
            
            # Cleanup
            db.delete(new_p)
            db.commit()
        except Exception as e:
            print(f"FAILURE: User 2 could not insert product: {e}")
            db.rollback()

    finally:
        db.close()

if __name__ == "__main__":
    test_multi_user()
