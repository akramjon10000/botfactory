from app import app, db
from models import User, Payment
from datetime import datetime

with app.app_context():
    # 1. Create a dummy user
    dummy_email = "testpayment@botfactory.uz"
    user = User.query.filter_by(email=dummy_email).first()
    if not user:
        user = User(username="testpayment", email=dummy_email)
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        print("Created dummy user.")
    
    # 2. Simulate User reporting a payment
    print(f"Creating a pending payment for {user.username} (Premium, Paynet)")
    payment = Payment(
        user_id=user.id,
        amount=590000,
        method="Paynet",
        status="pending",
        subscription_type="premium",
        transaction_id=f"TEST_{datetime.utcnow().strftime('%M%S')}"
    )
    db.session.add(payment)
    db.session.commit()
    print(f"Payment {payment.id} created with status '{payment.status}'.")

    # 3. Simulate Admin approving payment
    print(f"Simulating Admin Approval for Payment {payment.id}...")
    p = Payment.query.get(payment.id)
    p.status = 'completed'
    u = p.user # Relationship test
    u.subscription_type = p.subscription_type
    db.session.commit()
    
    print(f"User {u.username} is now on '{u.subscription_type}' subscription.")
    if p.status == 'completed' and u.subscription_type == 'premium':
        print("SUCCESS! Verification complete.")
    else:
        print("ERROR: Something went wrong.")

