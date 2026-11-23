import argparse
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.database import SessionLocal, engine, Base
from app.models import Chit, Transaction, User

CHIT_AMOUNTS = {"chit1": 40000, "chit2": 40000, "chit3": 50000, "chit4": 70000, "chit5": 70000}


def decimal_or_none(value):
    try:
        cleaned = (value or "").replace("₹", "").replace(",", "").strip()
        return Decimal(cleaned) if cleaned else None
    except (InvalidOperation, AttributeError):
        return None


def parse_date(value):
    from datetime import datetime
    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime((value or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


def migrate(source_root: Path, email: str):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email.lower()).first()
        if not user:
            raise RuntimeError("Create the account through the web app before running migration")

        folders = sorted([p for p in source_root.iterdir() if p.is_dir() and p.name.startswith("chit")])
        for folder in folders:
            name = folder.name
            csv_path = folder / "transactions.csv"
            if not csv_path.exists():
                continue

            chit = db.query(Chit).filter(Chit.owner_id == user.id, Chit.name == name).first()
            if not chit:
                chit = Chit(
                    owner_id=user.id,
                    name=name,
                    chit_amount=Decimal(str(CHIT_AMOUNTS.get(name, 40000))),
                    status="completed" if name.startswith("completed") else "active",
                    notes="Imported from existing folder structure",
                )
                db.add(chit)
                db.flush()

            image_dir = folder / "transactions"
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    transaction_id = (row.get("Transaction ID") or "").strip()
                    amount = decimal_or_none(row.get("Amount Transferred"))
                    date_value = parse_date(row.get("Transaction Date"))
                    source_name = (row.get("Source File") or "").strip()
                    if not any((date_value, amount, transaction_id, source_name)):
                        continue

                    image_bytes = None
                    content_type = None
                    image_path = image_dir / source_name if source_name else None
                    if image_path and image_path.exists():
                        image_bytes = image_path.read_bytes()
                        suffix = image_path.suffix.lower()
                        content_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".bmp": "image/bmp"}.get(suffix)

                    existing = db.query(Transaction).filter(
                        Transaction.owner_id == user.id,
                        Transaction.chit_id == chit.id,
                        Transaction.source_file_name == source_name,
                    ).first() if source_name else None

                    if existing:
                        continue

                    db.add(Transaction(
                        owner_id=user.id,
                        chit_id=chit.id,
                        transaction_date=date_value,
                        amount_transferred=amount,
                        transaction_id=transaction_id or None,
                        status="verified",
                        source_file_name=source_name or None,
                        notes="Imported from existing CSV",
                        image_data=image_bytes,
                        image_content_type=content_type,
                    ))
        db.commit()
        print("Migration complete")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=r"C:\repos\legal_documents\investment\chitfunds")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    migrate(Path(args.source), args.email.strip().lower())
