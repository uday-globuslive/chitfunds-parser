# Chitfunds Parser - Project Context

## Purpose

A multi-user FastAPI application for chit-fund payments. It provides server-rendered Jinja2 pages, PostgreSQL storage, Tesseract OCR, account approval, image storage/download, transaction editing, runtime totals, combined-payment splitting, and CSV export.

## Repository

Development folder:

```text
C:\repos\chitfunds-parser
```

Legacy source:

```text
C:\repos\legal_documents\investment\chitfunds
```

## Stack

- Python 3.9 locally; Python 3.12 container base
- FastAPI and Uvicorn
- Jinja2
- SQLAlchemy and psycopg2
- PostgreSQL/TiDB Cloud
- Tesseract OCR and Pillow
- Passlib/bcrypt signed-cookie authentication
- a2wsgi for PythonAnywhere WSGI deployment
- Docker and GitHub Actions

## Core Data

### User

- email
- password_hash
- display_name
- role: `user` or `admin`
- is_approved
- is_active
- created_at

### Chit

- owner_id
- name
- chit_amount
- start_date
- status: `active`, `completed`, or `archived`
- notes

### Transaction

- owner_id
- chit_id
- transaction_date
- amount_transferred
- transaction_id
- status: `needs_review` or `verified`
- source_file_name
- ocr_text
- ocr_confidence
- notes
- image_data bytea
- image_content_type

Every route must filter by the authenticated user's `owner_id` or call the existing ownership helpers.

## Authentication

Signup creates pending, active users. They cannot access data until admin approval.

Admin controls:

- approve pending users
- enable/disable users
- promote/demote users
- protect the current admin from disabling or changing their own role

Default admin values come from:

- `DEFAULT_ADMIN_NAME`
- `DEFAULT_ADMIN_EMAIL`
- `DEFAULT_ADMIN_PASSWORD`

Startup creates/promotes the configured admin but does not reset an existing admin password.

## Runtime Totals

Derived totals are not stored in transaction or chit tables.

```text
Total chit amount = chit amount * number of recorded transactions
Total amount paid = sum(amount_transferred)
```

Dashboard, chit detail, and transaction review show runtime totals.

CSV exports:

- one transaction per row
- original transaction fields only in transaction rows
- `TOTAL CHIT AMOUNT` summary row at the bottom
- `TOTAL AMOUNT PAID` summary row at the bottom

## Combined Payments

Upload from one chit and select additional owned chits in `Also record for`.

The app creates independent transaction records linked to each chit. Each copy stores the same screenshot and OCR text, but starts with no amount for a combined upload because the total must be manually split.

A future version should add a shared-payment parent and split validation.

## OCR

Tesseract extracts date, amount, transaction ID, raw text, and average confidence.

The amount parser supports currency symbols and comma-formatted values such as `53,270`.

OCR extraction is always editable.

## Database

PostgreSQL/TiDB Cloud through SQLAlchemy and psycopg2.

Expected URL:

```text
postgresql+psycopg2://USERNAME:PASSWORD@HOST:5432/chitfunds?sslmode=require
```

Startup creates missing tables and adds the existing `users.role`, `users.is_approved`, and `users.is_active` columns with PostgreSQL `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

Add formal Alembic migrations before changing schemas in production.

## Environment Variables

Required:

- `DATABASE_URL`
- `SESSION_SECRET`

Optional:

- `TESSERACT_CMD`
- `MAX_UPLOAD_MB`
- `COOKIE_HTTPS`
- `DEFAULT_ADMIN_NAME`
- `DEFAULT_ADMIN_EMAIL`
- `DEFAULT_ADMIN_PASSWORD`

Never commit `.env`, database passwords, session secrets, or admin passwords.

## Docker

The Dockerfile installs Tesseract and Python dependencies.

GitHub Actions builds and publishes to Docker Hub.

Required GitHub Actions secrets:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

Use a Docker Hub access token for `DOCKERHUB_TOKEN`, not an account password.

Default image name:

```text
<DOCKERHUB_USERNAME>/chitfunds-parser
```

Each branch push publishes one tag: `<lowercase-branch>-<7-character-commit>`. Unsupported Docker tag characters, including `/`, become `-`. Pull requests build locally without publishing.

Pull and run:

```bash
docker pull DOCKERHUB_USERNAME/chitfunds-parser:main-abcdef1
docker run --env-file .env -p 8000:8000 DOCKERHUB_USERNAME/chitfunds-parser:main-abcdef1
```

## Deployment

See `DEPLOYMENT.md` for Windows, Linux, PythonAnywhere, PostgreSQL, Docker, HTTPS, and Tesseract instructions.

PythonAnywhere may require `wsgi.py` and `a2wsgi` for WSGI hosting:

```python
from wsgi import application
```

## Main Files

- `app/main.py`: application routes and user workflows
- `app/models.py`: SQLAlchemy models
- `app/database.py`: database engine and sessions
- `app/security.py`: password helpers
- `app/ocr.py`: OCR extraction
- `app/templates/`: Jinja2 pages
- `app/static/app.css`: CSS
- `migrate_existing_data.py`: legacy CSV migration
- `wsgi.py`: PythonAnywhere ASGI-to-WSGI adapter
- `Dockerfile`
- `.dockerignore`
- `.github/workflows/docker-image.yml`
- `DEPLOYMENT.md`

## Completed Features

- Multi-user signup/login
- Approval workflow
- Admin controls
- Default admin from environment
- Chit CRUD editing
- Transaction create/edit/delete
- Screenshot upload and download
- PostgreSQL image storage
- Tesseract OCR review
- Combined screenshot splitting
- Runtime dashboard totals
- Runtime CSV totals
- Docker build
- GitHub Actions Docker Hub publishing
- PythonAnywhere WSGI bridge

## Future Improvements

- Formal Alembic migrations
- Shared-payment and split model
- Duplicate detection
- OCR preprocessing and confidence thresholds
- Edit audit history
- Password reset and email verification
- CSRF protection
- Security headers and rate limiting
- Pagination and filtering
- PDF reports
- Automated ownership-isolation tests
- Database backup and restore testing
