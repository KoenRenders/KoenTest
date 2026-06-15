# E2e-tests (Playwright) — #128

Headless end-to-end tests tegen een **draaiende** frontend + backend. De eerste
flow (`registration.spec.ts`) registreert een gezin via "Word lid" met betaaltype
**overschrijving** — die raakt Mollie niet, dus stabiel zonder gateway-stub.

## Lokaal draaien

1. **Backend** (met geseede postcodes), bv.:
   ```
   cd backend
   export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/raake2e
   export SECRET_KEY=dev-secret-key-long-enough-for-hs256
   export APP_ENV=dev
   alembic upgrade head
   python seed_postal_codes.py
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
2. **Frontend** (in een tweede terminal), met de API-URL naar de backend:
   ```
   cd frontend
   npm install
   npx playwright install --with-deps chromium   # eenmalig
   NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
   ```
3. **Tests** (derde terminal):
   ```
   cd frontend
   npm run e2e
   ```

## CI

Een **non-blocking** `e2e`-job in `.github/workflows/backend-tests.yml` start de
stack (Postgres + backend + `next dev`) en draait deze spec. `continue-on-error`
staat aan zodat de e2e (terwijl die wordt uitgebreid) de pijplijn niet breekt.
