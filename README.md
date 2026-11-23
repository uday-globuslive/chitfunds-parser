# Chitfunds Parser

A multi-user FastAPI application for OCR-assisted chit-fund transaction records.

## Features

- User signup and login
- Complete data isolation per account
- Chit management
- Image upload and database storage
- Tesseract OCR review workflow
- Manual create and edit forms
- Image downloads
- CSV export
- PostgreSQL database

## Start with Docker

1. Copy `.env.example` to `.env`.
2. Set a strong `SESSION_SECRET`.
3. Run `docker compose up --build`.
4. Open `http://localhost:8000`.

## Local start without Docker

1. Create a virtual environment.
2. Install requirements.
3. Start PostgreSQL and set `DATABASE_URL` in `.env`.
4. Run `uvicorn app.main:app --reload`.

Install Tesseract locally and set `TESSERACT_CMD` if it is not found automatically.
