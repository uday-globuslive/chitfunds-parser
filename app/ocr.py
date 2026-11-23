import io
import os
import re
from datetime import datetime

import pytesseract
from PIL import Image


tesseract_cmd = os.getenv("TESSERACT_CMD")
if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def normalize_date(value):
    if not value:
        return None
    value = value.strip().replace("Sept", "Sep")
    formats = (
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y",
        "%d %B %Y", "%d-%b-%Y", "%d-%b-%y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def extract(image_bytes):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    text = pytesseract.image_to_string(image)

    confidences = [float(v) for v in data.get("conf", []) if str(v).isdigit() and float(v) >= 0]
    confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0

    transaction_date = None
    date_patterns = (
        r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
        r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b",
        r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Sept(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{2,4}\b",
    )
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            transaction_date = normalize_date(match.group(0))
            if transaction_date:
                break

    amount = None
    amount_patterns = (
        r"(?:₹|Rs\.?|INR|[%])\s*[=:\s]*([\d][\d,]{2,})",
        r"(?:amount|paid|debited|total)\s*[:=]?\s*(?:₹|Rs\.?|INR)?\s*([\d][\d,]{2,})",
    )
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = re.sub(r"[^0-9.]", "", match.group(1))
            try:
                candidate = float(value)
                if 100 <= candidate <= 10000000:
                    amount = candidate
                    break
            except ValueError:
                pass

    if amount is None:
        comma_values = re.findall(r"\b\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?\b", text)
        for value in comma_values:
            candidate = float(value.replace(",", ""))
            if 100 <= candidate <= 10000000:
                amount = candidate
                break

    transaction_id = None
    id_patterns = (
        r"(?:Transaction\s*(?:ID|No)|Txn(?:\s*ID)?|UTR|Reference(?:\s*(?:No|ID))?)\s*[:#=-]?\s*([A-Z0-9][A-Z0-9-]{7,})",
        r"\b(?:UPI|IMPS|NEFT)\s*[:#=-]?\s*([A-Z0-9][A-Z0-9-]{7,})",
        r"\b([A-Z]?\d{12,})\b",
    )
    for pattern in id_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            transaction_id = match.group(1).strip()
            break

    return {
        "text": text,
        "confidence": confidence,
        "transaction_date": transaction_date,
        "amount_transferred": amount,
        "transaction_id": transaction_id,
    }
