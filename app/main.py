import csv
import io
import os
import uuid
from datetime import date
from typing import List
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

from .database import engine, get_db, Base, SessionLocal
from .models import Chit, Transaction, User
from .ocr import extract
from .security import hash_password, verify_password

app = FastAPI(title="Chitfunds Parser")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "development-only-change-this-secret"),
    https_only=os.getenv("COOKIE_HTTPS", "false").lower() == "true",
)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "app", "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "app", "templates"))


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user'"))
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_approved INTEGER NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active INTEGER NOT NULL DEFAULT 1"))
    db = SessionLocal()
    try:
        email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@chitfunds.local").strip().lower()
        password = os.getenv("DEFAULT_ADMIN_PASSWORD", "ChangeMeNow123!")
        name = os.getenv("DEFAULT_ADMIN_NAME", "Administrator").strip()
        admin = db.query(User).filter(User.email == email).first()
        if not admin:
            admin = User(
                email=email,
                password_hash=hash_password(password),
                display_name=name,
                role="admin",
                is_approved=1,
                is_active=1,
            )
            db.add(admin)
            db.commit()
        else:
            changed = False
            if admin.role != "admin":
                admin.role = "admin"
                changed = True
            if not admin.is_approved:
                admin.is_approved = 1
                changed = True
            if not admin.is_active:
                admin.is_active = 1
                changed = True
            if changed:
                db.commit()
    finally:
        db.close()


def current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    try:
        return db.query(User).filter(User.id == uuid.UUID(user_id)).first()
    except (ValueError, AttributeError):
        request.session.clear()
        return None


def require_user(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    if not user.is_active or not user.is_approved:
        request.session.clear()
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def require_admin(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


def get_owned_chit(db: Session, chit_id: str, user: User):
    try:
        chit_uuid = uuid.UUID(chit_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Chit not found")
    chit = db.query(Chit).filter(Chit.id == chit_uuid, Chit.owner_id == user.id).first()
    if not chit:
        raise HTTPException(status_code=404, detail="Chit not found")
    return chit


def get_owned_transaction(db: Session, transaction_id: str, user: User):
    try:
        transaction_uuid = uuid.UUID(transaction_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Transaction not found")
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_uuid,
        Transaction.owner_id == user.id,
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_decimal(value):
    if not value:
        return None
    try:
        return Decimal(value.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "error": None})


@app.post("/signup")
def signup(
    request: Request,
    display_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if len(password) < 8:
        return templates.TemplateResponse("signup.html", {
            "request": request,
            "error": "Password must be at least 8 characters.",
        }, status_code=400)
    normalized_email = email.strip().lower()
    if db.query(User).filter(User.email == normalized_email).first():
        return templates.TemplateResponse("signup.html", {
            "request": request,
            "error": "An account with this email already exists.",
        }, status_code=400)
    user = User(
        display_name=display_name.strip(),
        email=normalized_email,
        password_hash=hash_password(password),
        role="user",
        is_approved=0,
        is_active=1,
    )
    db.add(user)
    db.commit()
    return RedirectResponse("/login?pending=1", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, pending: int = 0):
    error = "Registration received. Wait for administrator approval before signing in." if pending else None
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Email or password is incorrect.",
        }, status_code=401)
    if not user.is_active:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "This account is disabled.",
        }, status_code=403)
    if not user.is_approved:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Your account is waiting for administrator approval.",
        }, status_code=403)
    request.session["user_id"] = str(user.id)
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "user": admin,
        "users": users,
    })


@app.post("/admin/users/{user_id}/approve")
def approve_user(request: Request, user_id: str, db: Session = Depends(get_db)):
    require_admin(request, db)
    target = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.is_approved = 1
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/{user_id}/toggle-active")
def toggle_user_active(request: Request, user_id: str, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    target = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")
    target.is_active = 0 if target.is_active else 1
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/{user_id}/toggle-role")
def toggle_user_role(request: Request, user_id: str, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    target = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot change your own role")
    target.role = "admin" if target.role != "admin" else "user"
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    chits = db.query(Chit).filter(Chit.owner_id == user.id).order_by(Chit.created_at.desc()).all()
    chit_cards = []
    for chit in chits:
        transactions = db.query(Transaction).filter(Transaction.chit_id == chit.id).all()
        paid = sum((Decimal(str(row.amount_transferred)) for row in transactions if row.amount_transferred is not None), Decimal("0"))
        chit_cards.append({
            "chit": chit,
            "transaction_count": len(transactions),
            "total_chit_amount": chit.chit_amount * len(transactions),
            "paid": paid,
        })
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "chit_cards": chit_cards})


@app.post("/chits")
def create_chit(
    request: Request,
    name: str = Form(...),
    chit_amount: str = Form(...),
    start_date: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    amount = parse_decimal(chit_amount)
    if amount is None or amount <= 0:
        raise HTTPException(status_code=400, detail="Chit amount must be a positive number")
    chit = Chit(owner_id=user.id, name=name.strip(), chit_amount=amount, start_date=parse_date(start_date), notes=notes.strip() or None)
    db.add(chit)
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/chits/{chit_id}/edit")
def edit_chit(
    request: Request,
    chit_id: str,
    name: str = Form(...),
    chit_amount: str = Form(...),
    start_date: str = Form(""),
    status: str = Form("active"),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    chit = get_owned_chit(db, chit_id, user)
    amount = parse_decimal(chit_amount)
    if amount is None or amount <= 0:
        raise HTTPException(status_code=400, detail="Chit amount must be a positive number")
    chit.name = name.strip()
    chit.chit_amount = amount
    chit.start_date = parse_date(start_date)
    chit.status = status if status in {"active", "completed", "archived"} else "active"
    chit.notes = notes.strip() or None
    db.commit()
    return RedirectResponse(f"/chits/{chit_id}", status_code=303)


@app.post("/chits/{chit_id}/delete")
def delete_chit(request: Request, chit_id: str, db: Session = Depends(get_db)):
    user = require_user(request, db)
    chit = get_owned_chit(db, chit_id, user)
    db.delete(chit)
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/chits/{chit_id}", response_class=HTMLResponse)
def chit_detail(request: Request, chit_id: str, db: Session = Depends(get_db)):
    user = require_user(request, db)
    chit = get_owned_chit(db, chit_id, user)
    transactions = db.query(Transaction).filter(Transaction.chit_id == chit.id).order_by(Transaction.transaction_date.desc()).all()
    other_chits = db.query(Chit).filter(Chit.owner_id == user.id, Chit.id != chit.id, Chit.status == "active").order_by(Chit.name.asc()).all()
    paid = sum((Decimal(str(row.amount_transferred)) for row in transactions if row.amount_transferred is not None), Decimal("0"))
    total_chit_amount = chit.chit_amount * len(transactions)
    return templates.TemplateResponse("chit_detail.html", {
        "request": request,
        "user": user,
        "chit": chit,
        "transactions": transactions,
        "paid": paid,
        "total_chit_amount": total_chit_amount,
        "other_chits": other_chits,
    })


@app.post("/chits/{chit_id}/transactions")
def create_manual_transaction(
    request: Request,
    chit_id: str,
    transaction_date: str = Form(""),
    amount_transferred: str = Form(""),
    transaction_id: str = Form(""),
    status: str = Form("verified"),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    chit = get_owned_chit(db, chit_id, user)
    transaction = Transaction(
        owner_id=user.id,
        chit_id=chit.id,
        transaction_date=parse_date(transaction_date),
        amount_transferred=parse_decimal(amount_transferred),
        transaction_id=transaction_id.strip() or None,
        status=status if status in {"verified", "needs_review"} else "needs_review",
        notes=notes.strip() or None,
    )
    db.add(transaction)
    db.commit()
    return RedirectResponse(f"/chits/{chit_id}", status_code=303)


@app.post("/chits/{chit_id}/upload")
def upload_transaction(
    request: Request,
    chit_id: str,
    file: UploadFile = File(...),
    extra_chit_ids: List[str] = Form([]),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    chit = get_owned_chit(db, chit_id, user)
    if file.content_type not in {"image/jpeg", "image/png", "image/webp", "image/bmp"}:
        raise HTTPException(status_code=400, detail="Upload a JPEG, PNG, WebP, or BMP image")

    image_bytes = file.file.read()
    max_bytes = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024
    if len(image_bytes) > max_bytes:
        raise HTTPException(status_code=400, detail="Image exceeds upload limit")

    try:
        result = extract(image_bytes)
    except Exception as exc:
        result = {"text": "", "confidence": 0, "transaction_date": None, "amount_transferred": None, "transaction_id": None}

    selected_ids = [value for value in extra_chit_ids if value]
    transaction = Transaction(
        owner_id=user.id,
        chit_id=chit.id,
        transaction_date=result["transaction_date"],
        amount_transferred=None if selected_ids else (Decimal(str(result["amount_transferred"])) if result["amount_transferred"] is not None else None),
        transaction_id=result["transaction_id"],
        status="needs_review",
        source_file_name=file.filename,
        ocr_text=result["text"],
        ocr_confidence=Decimal(str(result["confidence"])),
        image_data=image_bytes,
        image_content_type=file.content_type,
    )
    db.add(transaction)

    selected_ids = [value for value in extra_chit_ids if value]
    for selected_id in selected_ids:
        selected_chit = get_owned_chit(db, selected_id, user)
        if selected_chit.id == chit.id:
            continue
        db.add(Transaction(
            owner_id=user.id,
            chit_id=selected_chit.id,
            transaction_date=result["transaction_date"],
            amount_transferred=None,
            transaction_id=result["transaction_id"],
            status="needs_review",
            source_file_name=file.filename,
            ocr_text=result["text"],
            ocr_confidence=Decimal(str(result["confidence"])),
            image_data=image_bytes,
            image_content_type=file.content_type,
            notes="Shared screenshot. Enter this chit's portion of the combined payment.",
        ))

    db.commit()
    db.refresh(transaction)
    return RedirectResponse(f"/transactions/{transaction.id}/edit", status_code=303)


@app.get("/transactions/{transaction_id}/edit", response_class=HTMLResponse)
def edit_transaction_page(request: Request, transaction_id: str, db: Session = Depends(get_db)):
    user = require_user(request, db)
    transaction = get_owned_transaction(db, transaction_id, user)
    chit = get_owned_chit(db, str(transaction.chit_id), user)
    total_transactions = db.query(Transaction).filter(Transaction.chit_id == chit.id).count()
    total_chit_amount = chit.chit_amount * total_transactions
    return templates.TemplateResponse("transaction_edit.html", {
        "request": request,
        "user": user,
        "chit": chit,
        "transaction": transaction,
        "total_chit_amount": total_chit_amount,
    })


@app.post("/transactions/{transaction_id}/edit")
def edit_transaction(
    request: Request,
    transaction_id: str,
    transaction_date: str = Form(""),
    amount_transferred: str = Form(""),
    transaction_id_value: str = Form("", alias="transaction_id"),
    status: str = Form("needs_review"),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    transaction = get_owned_transaction(db, transaction_id, user)
    transaction.transaction_date = parse_date(transaction_date)
    transaction.amount_transferred = parse_decimal(amount_transferred)
    transaction.transaction_id = transaction_id_value.strip() or None
    transaction.status = status if status in {"verified", "needs_review"} else "needs_review"
    transaction.notes = notes.strip() or None
    db.commit()
    return RedirectResponse(f"/chits/{transaction.chit_id}", status_code=303)


@app.get("/transactions/{transaction_id}/image")
def download_transaction_image(request: Request, transaction_id: str, db: Session = Depends(get_db)):
    user = require_user(request, db)
    transaction = get_owned_transaction(db, transaction_id, user)
    if not transaction.image_data:
        raise HTTPException(status_code=404, detail="No image stored")
    filename = transaction.source_file_name or f"transaction-{transaction.id}.jpg"
    return StreamingResponse(
        io.BytesIO(transaction.image_data),
        media_type=transaction.image_content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/transactions/{transaction_id}/delete")
def delete_transaction(request: Request, transaction_id: str, db: Session = Depends(get_db)):
    user = require_user(request, db)
    transaction = get_owned_transaction(db, transaction_id, user)
    chit_id = transaction.chit_id
    db.delete(transaction)
    db.commit()
    return RedirectResponse(f"/chits/{chit_id}", status_code=303)


@app.get("/chits/{chit_id}/export.csv")
def export_csv(request: Request, chit_id: str, db: Session = Depends(get_db)):
    user = require_user(request, db)
    chit = get_owned_chit(db, chit_id, user)
    transactions = db.query(Transaction).filter(Transaction.chit_id == chit.id).order_by(Transaction.transaction_date.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Transaction Date", "Amount Transferred", "Transaction ID", "Chit Amount", "Source File", "Status"])
    total_chit_amount = chit.chit_amount * len(transactions)
    total_amount_paid = sum((Decimal(str(transaction.amount_transferred)) for transaction in transactions if transaction.amount_transferred is not None), Decimal("0"))
    for transaction in transactions:
        writer.writerow([
            transaction.transaction_date.isoformat() if transaction.transaction_date else "",
            str(transaction.amount_transferred) if transaction.amount_transferred is not None else "",
            transaction.transaction_id or "",
            str(chit.chit_amount),
            transaction.source_file_name or "",
            transaction.status,
        ])
    writer.writerow([])
    writer.writerow(["TOTAL CHIT AMOUNT", "", "", str(total_chit_amount), "", ""])
    writer.writerow(["TOTAL AMOUNT PAID", str(total_amount_paid), "", "", "", ""])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="chit-{chit.name}-transactions.csv"'},
    )
