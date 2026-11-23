# Deployment Guide: Windows and Linux

This application uses FastAPI, PostgreSQL/TiDB Cloud, Tesseract OCR, and server-rendered Jinja2 templates.

## 1. Environment Variables

Create a `.env` file in the project root.

```dotenv
DATABASE_URL=postgresql+psycopg2://USERNAME:PASSWORD@HOST:5432/chitfunds?sslmode=require
SESSION_SECRET=replace-with-a-long-random-secret
MAX_UPLOAD_MB=10

DEFAULT_ADMIN_NAME=Administrator
DEFAULT_ADMIN_EMAIL=admin@example.com
DEFAULT_ADMIN_PASSWORD=replace-with-a-strong-password

# Windows example:
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe

# Linux/PythonAnywhere example:
# TESSERACT_CMD=/usr/bin/tesseract
```

Generate a strong session secret with Python:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Do not commit `.env` to Git. Add it to `.gitignore`.

## 2. Windows Setup

### Install Tesseract

1. Download the 64-bit Tesseract installer for Windows.
2. Install it to the standard location:

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```

3. Set `TESSERACT_CMD` in `.env`.

### Install Python and the application

PowerShell:

```powershell
cd C:\repos\chitfunds-parser
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip==24.3.1
pip install -r requirements.txt
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

### Test the database connection

```powershell
python -c "from dotenv import load_dotenv; load_dotenv(); from app.database import engine; from sqlalchemy import text; c=engine.connect(); print(c.execute(text('select current_database(), current_user')).first()); c.close()"
```

### Run locally

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## 3. Linux Setup

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip tesseract-ocr
```

Optional language support:

```bash
sudo apt install -y tesseract-ocr-eng
```

If another language is OCR-ed, install the matching language package, for example:

```bash
sudo apt install -y tesseract-ocr-tel
```

Verify Tesseract:

```bash
which tesseract
tesseract --version
```

Set `TESSERACT_CMD=/usr/bin/tesseract` in `.env`.

### Create the virtual environment

```bash
cd /path/to/chitfunds-parser
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Run locally or on a Linux server

Development:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Production-style process:

```bash
pip install gunicorn
gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

Do not expose Uvicorn or Gunicorn directly to the internet without a reverse proxy and HTTPS.

## 4. PostgreSQL/TiDB Cloud

Use PostgreSQL TLS for production connections. The application passes the SSL mode in `DATABASE_URL` to the PostgreSQL driver; it does not enable TLS on the database server.

The `DATABASE_URL` format is:

```text
postgresql+psycopg2://USERNAME:PASSWORD@HOST:5432/DATABASE?sslmode=require
```

Example:

```dotenv
DATABASE_URL=postgresql+psycopg2://your-user:your-password@your-host.gateway.prod.aws.com:5432/chitfunds?sslmode=require
```

URL-encode passwords containing reserved characters such as `@`, `/`, `#`, `?`, or `%`. The database does not need to run on PythonAnywhere or the Windows host.

If startup fails with `server does not support SSL, but SSL was required`, enable TLS on PostgreSQL where possible. For a trusted development network with a server that does not support TLS, explicitly use `sslmode=disable` instead:

```dotenv
DATABASE_URL=postgresql+psycopg2://USERNAME:PASSWORD@HOST:5432/chitfunds?sslmode=disable
```

This sends database traffic, including credentials, without encryption. Do not use it over untrusted networks. The PostgreSQL service in `docker-compose.yml` does not enable TLS by default; when connecting to it from the `web` service, use `postgres` as the host rather than `localhost`.

On startup, the application:

- Creates missing tables.
- Adds approval, role, and active columns to existing `users` tables.
- Creates or updates the default administrator from `.env`.

A PostgreSQL user with schema DDL permissions is required for the first deployment and for automatic startup migrations.

## 5. PythonAnywhere Deployment

### 5.1 Upload the project

Upload the repository or clone it in a PythonAnywhere console:

```bash
cd ~
git clone YOUR_REPOSITORY_URL chitfunds-parser
cd chitfunds-parser
```

The application does not require Docker on PythonAnywhere.

### 5.2 Use a supported Python version

PythonAnywhere should use Python 3.10 or newer for a modern deployment. If only Python 3.9 is available, the pinned `requirements.txt` can support it.

Create the virtual environment:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5.3 Install Tesseract

Most PythonAnywhere user accounts cannot use `apt-get` or install system packages. Tesseract availability depends on the selected PythonAnywhere account tier and infrastructure.

Before configuring OCR:

```bash
which tesseract
ls -l /usr/bin/tesseract
```

If Tesseract is unavailable:

1. Ask PythonAnywhere support whether Tesseract is available on your account.
2. Consider OCR provider alternatives or a VPS.
3. The app can still store and manually edit images, but OCR extraction will not work until Tesseract is available.

If it is available, set:

```dotenv
TESSERACT_CMD=/usr/bin/tesseract
```

Do not configure `C:\Program Files\Tesseract-OCR\tesseract.exe` on PythonAnywhere.

### 5.4 Configure `.env`

Create `.env` in the project directory:

```bash
nano .env
```

Use the production database URL and a strong session secret. Never use the local development password or expose the file publicly.

### 5.5 Configure the PythonAnywhere web app

1. Open the PythonAnywhere **Web** tab.
2. Add a new web app.
3. Choose **Manual configuration**.
4. Select the same Python version used by `.venv`.
5. Set the virtual environment path:

```text
/home/YOUR_USERNAME/chitfunds-parser/.venv
```

6. Set the WSGI configuration file to load:

```python
from wsgi import application
```

The project provides `wsgi.py`, which uses `a2wsgi` to run the FastAPI ASGI application through PythonAnywhere's WSGI interface.

For both WSGI and ASGI processes, the working directory is:

```text
/home/YOUR_USERNAME/chitfunds-parser
```

The FastAPI entry point remains:

```python
from app.main import app
```

### 5.6 Database security

Allow PythonAnywhere to reach TiDB Cloud:

1. Confirm TiDB Cloud network access allows the PythonAnywhere outbound IP or account network.
2. Keep `sslmode=require` in `DATABASE_URL`.
3. Rotate the database password if it was previously committed or shared.

### 5.7 Static files

On PythonAnywhere or another reverse-proxy host, configure static files:

```text
URL: /static/
Directory: /home/YOUR_USERNAME/chitfunds-parser/app/static/
```

### 5.8 HTTPS and cookies

Set in the production environment:

```dotenv
COOKIE_HTTPS=true
```

This is automatically important for secure session cookies behind HTTPS.

Note: this project currently enables HTTPS-only cookies only when `COOKIE_HTTPS=true`.

### 5.9 Default admin

Set a strong admin account in `.env`:

```dotenv
DEFAULT_ADMIN_NAME=Administrator
DEFAULT_ADMIN_EMAIL=admin@yourdomain.com
DEFAULT_ADMIN_PASSWORD=strong-random-password
```

The account is created or promoted on startup. Existing admin passwords are not reset automatically.

### 5.10 File size and uploaded images

`MAX_UPLOAD_MB=10` limits each uploaded image. Uploaded image bytes are stored in the PostgreSQL `transactions.image_data` column.

Database backup size will grow with screenshots. TiDB Cloud storage capacity and plan limits should be monitored.

## 6. PostgreSQL Migration for Existing Database

For existing rows in a deployed database, the app startup migration adds:

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user';
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_approved INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active INTEGER NOT NULL DEFAULT 1;
```

For existing chits and transactions, `Base.metadata.create_all()` creates missing tables but does not alter other custom schemas. Add a formal Alembic migration before changing more database columns in production.

## GitHub Actions to Docker Hub

In the GitHub repository, open **Settings > Secrets and variables > Actions** and add:

- `DOCKERHUB_USERNAME`: Docker Hub username
- `DOCKERHUB_TOKEN`: Docker Hub access token, not an account password

Each branch push publishes one tag in the form `<lowercase-branch>-<7-character-commit>`. Characters that are invalid in Docker tags, including `/`, become `-`. For example, `feature/Payments` at commit `abcdef1` produces `feature-payments-abcdef1`.

Example image name:

```text
DOCKERHUB_USERNAME/chitfunds-parser:main-abcdef1
```

Pull request builds validate Docker build output but do not push or require Docker Hub credentials.

## Run the Docker Hub Image

Install and start Docker Desktop on Windows or Docker Engine on Linux. Add `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` to the GitHub repository's Actions secrets before pushing a branch. After the workflow succeeds, find the actual image tag in the Actions run or Docker Hub. Replace `DOCKERHUB_USERNAME` and `main-abcdef1` in the commands below with your username and published tag. For a private image, run `docker login` first.

For Ubuntu 24.04 Docker and PostgreSQL container setup, see [Installing Docker & PostgreSQL on Ubuntu 24.04 with pgAdmin Web Interface](https://vbscriptsite.wordpress.com/2026/03/12/installing-docker-postgresql-on-ubuntu-24-04-with-pgadmin-web-interface/).

Create a separate `.env.docker` file on the machine running Docker:

```dotenv
DATABASE_URL=postgresql+psycopg2://USERNAME:PASSWORD@HOST:5432/chitfunds?sslmode=require
SESSION_SECRET=replace-with-a-long-random-secret
DEFAULT_ADMIN_NAME=Administrator
DEFAULT_ADMIN_EMAIL=admin@example.com
DEFAULT_ADMIN_PASSWORD=replace-with-a-strong-password
MAX_UPLOAD_MB=10
COOKIE_HTTPS=false
TESSERACT_CMD=/usr/bin/tesseract
```

Replace the placeholders with your own database and admin settings. Generate the session secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. URL-encode reserved characters in the database password. Docker's `--env-file` passes values literally, so do not add shell-style quotes around values. Keep this file private and never commit or publish it. The image already includes Tesseract at `/usr/bin/tesseract`; do not pass the Windows Tesseract path from your local `.env`.

The database must be reachable from the container. `localhost` inside a container refers to that container, not your host machine. Use your cloud database hostname or an appropriately configured Docker network hostname.

The following command publishes port 8000 on all host interfaces. Restrict access to trusted networks using host and network firewalls; use HTTPS for public access. For host-only access, replace `-p 8000:8000` with `-p 127.0.0.1:8000:8000`.

From the directory containing `.env.docker`, run the following in PowerShell or a Linux shell:

```bash
docker pull DOCKERHUB_USERNAME/chitfunds-parser:main-abcdef1
docker run -d --name chitfunds-parser --env-file .env.docker -p 8000:8000 DOCKERHUB_USERNAME/chitfunds-parser:main-abcdef1
docker logs -f chitfunds-parser
```

After startup completes, open `http://127.0.0.1:8000` on the Docker host or `http://DOCKER_HOST_IP:8000` from another machine. Allow TCP port 8000 through the host and network firewalls for the clients that need access. Press Ctrl+C to stop following logs; the container continues running. `COOKIE_HTTPS=false` is for HTTP testing only. For deployment behind HTTPS, use `COOKIE_HTTPS=true`, configure an HTTPS reverse proxy, and change the port binding as needed. Do not expose this application publicly without reviewing its authentication and production security controls.

Use `docker port chitfunds-parser` to check the published address. A mapping to `127.0.0.1:8000` is accessible only from the Docker host. To change the port mapping, recreate the container with the desired `docker run` options; restarting it is not sufficient.

Useful container commands:

```bash
docker stop chitfunds-parser
docker start chitfunds-parser
docker logs chitfunds-parser
```

To apply a changed `.env.docker` or deploy a different tag, stop and remove the container, then repeat the `docker run` command:

```bash
docker stop chitfunds-parser
docker rm chitfunds-parser
```

Restarting an existing container does not reload its environment file. For Docker Compose, update the `.env` used by the `web` service and run `docker compose up -d --force-recreate web`.

Removing the container does not delete records or screenshots stored in the external database. Back up the database separately. Changing `DEFAULT_ADMIN_PASSWORD` does not reset an existing admin account's password.

## 7. Operations Checklist

Before production:

- [ ] Replace the default session secret.
- [ ] Replace the default admin password.
- [ ] Confirm signup accounts remain pending until approval.
- [ ] Confirm only approved/active users can access data.
- [ ] Confirm TiDB Cloud TLS is enabled.
- [ ] Confirm image uploads are stored and downloadable.
- [ ] Confirm Tesseract is available in the deployed environment.
- [ ] Configure database backups.
- [ ] Add HTTPS and a custom domain.
- [ ] Monitor uploaded image database size.

## 8. Restart and Logs

Windows:

```powershell
Ctrl+C
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Linux/Gunicorn:

```bash
sudo systemctl restart chitfunds-parser
sudo journalctl -u chitfunds-parser -n 100 --no-pager
```

PythonAnywhere:

- Reload the web app from the **Web** tab after code or dependency changes.
- Check the server, access, and error logs from the **Web** tab.
