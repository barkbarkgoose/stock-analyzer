# Boilerplate

Ready-to-use Django + Vue 3 project boilerplate with JWT auth.

## First-Time Setup

The backend supports an encrypted keychain for secrets and other deployment-specific
configuration. It stores encrypted values in `backend/keychain.json` and its Fernet
key in `backend/keychain.key`; neither file is committed.

```bash
cd backend

# Install the cryptography dependency with the rest of the backend requirements.
uv pip install -r requirements.txt

# Create the encrypted store and its owner-only key file.
uv run python -m keychain init --from-example

# Move Django settings into the keychain. Quote values to preserve special characters.
uv run python -m keychain set "SECRET_KEY=replace-with-a-unique-production-secret"
uv run python -m keychain set "CORS_ALLOWED_ORIGINS=https://app.example.com"
uv run python -m keychain set "DATABASE_URL=postgres://user:password@db.example.com:5432/app"

# Verify encryption, decryption, and key-file permissions.
uv run python -m keychain doctor
```

`SECRET_KEY` and `CORS_ALLOWED_ORIGINS` use their `.env` values until a keychain value
is set, which keeps first-run management commands working. Once migrated, remove those
secret values from `.env`. Back up `backend/keychain.key` securely: without it,
`keychain.json` cannot be recovered. Rotate it with `uv run python -m keychain rotate-key`.

## Quick Start

Run both development servers together from the project root:

```bash
./dev.sh
```

The runner applies migrations, selects available ports beginning at `8800` and `5177`,
updates the Vite proxy and local CORS origins for those ports, and stops both processes
when you press Ctrl+C. Set `DEV_BACKEND_PORT_DEFAULT` or `DEV_FRONTEND_PORT_DEFAULT` in
the keychain to change the starting ports.

If `SECRET_KEY` is missing (or still the `.env.example` placeholder), the runner prompts
you to generate one and saves it to `backend/.env`. For unattended setups, set
`DEV_GENERATE_SECRET_KEY=1` to generate it without prompting.

### Backend

```bash
cd boilerplate/backend

# Create virtual environment
uv venv
source venv/bin/activate  # or .\.venv\Scripts\activate on Windows

# Install dependencies
uv pip install -r requirements.txt

# Copy and edit environment
cp .env.example .env

# Run migrations
uv run python manage.py migrate

# Create superuser
uv run python manage.py createsuperuser

# Run dev server
uv run python manage.py runserver 8800
```

### Frontend

This project uses [pnpm](https://pnpm.io). Enable it via Corepack if needed
(`corepack enable`) and install dependencies:

```bash
cd boilerplate/frontend

# Install dependencies
pnpm install

# Copy and edit environment
cp .env.example .env

# Run dev server
pnpm dev
```

## Structure

```
boilerplate/
├── backend/
│   ├── config/           # Django settings
│   │   └── settings/     # base.py, local.py, production.py
│   ├── apps/
│   │   ├── users/       # Custom User model + JWT auth
│   │   └── organizations/
│   └── manage.py
└── frontend/
    ├── src/
    │   ├── components/  # Navbar, etc.
    │   ├── views/       # Login, Register, Dashboard
    │   ├── stores/       # Pinia auth store
    │   ├── services/    # Axios with interceptors
    │   └── router/      # Vue Router with auth guards
    └── package.json
```

## Key Features

- **Tailwind CSS 4.x** via `@tailwindcss/vite` plugin
- **JWT Auth** with simplejwt (register/login/refresh endpoints)
- **Expired-token handling**: the auth store drops expired JWTs and the Axios
  interceptor redirects to `/login`, so the UI never gets stuck on a dead session
- **Custom User Model** with Organization FK
- **Per-user settings** (`/api/v1/auth/settings/`) with key whitelisting,
  input validation, and API keys encrypted at rest via `apps/users/crypto.py`
- **CORS configured** for frontend at localhost:5177
- **APPEND_SLASH=False** for clean API URLs

## Tests

```bash
cd backend
uv run --with-requirements requirements.txt python -m pytest
```


## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/v1/auth/register/` | POST | No | Register user + org |
| `/api/v1/auth/login/` | POST | No | Get JWT tokens + user |
| `/api/v1/auth/refresh/` | POST | No | Refresh access token |
| `/api/v1/auth/settings/` | GET | Yes | Read current user's settings |
| `/api/v1/auth/settings/` | PATCH | Yes | Update current user's settings |

## Add New Apps

```bash
cd backend
source venv/bin/activate
uv run python manage.py startapp myapp
```

Then add to `INSTALLED_APPS` in `config/settings/base.py`.
