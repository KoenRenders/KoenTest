#!/bin/sh
set -e

echo "==> Running database migrations..."
alembic upgrade head

echo "==> Seeding postal codes (if empty)..."
python -c "
from app.database import SessionLocal
from app.models.postal_codes import PostalCode
db = SessionLocal()
count = db.query(PostalCode).count()
db.close()
if count == 0:
    import subprocess, sys
    result = subprocess.run([sys.executable, 'seed_postal_codes.py'], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
else:
    print(f'  {count} postal codes already present, skipping.')
"

echo "==> Seeding activities (if empty)..."
python -c "
from app.database import SessionLocal
from app.models.activity import Activity
db = SessionLocal()
count = db.query(Activity).count()
db.close()
if count == 0:
    import subprocess, sys
    result = subprocess.run([sys.executable, 'seed_activities.py'], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
else:
    print(f'  {count} activities already present, skipping.')
"

echo "==> Seeding CMS pages (if empty)..."
python -c "
from app.database import SessionLocal
from app.models.cms import CmsPage
db = SessionLocal()
count = db.query(CmsPage).count()
db.close()
if count == 0:
    import subprocess, sys
    result = subprocess.run([sys.executable, 'seed_pages.py'], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
else:
    print(f'  {count} CMS pages already present, skipping.')
"

echo "==> Seeding sponsors from assets/seed (if present)..."
python seed_sponsors.py || echo "  sponsor seeding skipped/failed (non-fatal)"

echo "==> Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
