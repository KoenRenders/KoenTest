# Eén bouwingang (#396) — zie BUILDING.md. Vereist Postgres + raaktest-DB.
TEST_DB ?= postgresql+psycopg2://postgres:postgres@localhost:5432/raaktest
CHECK_DB ?= postgresql://postgres:postgres@localhost:5432/raakcheck

.PHONY: ci test typecheck migrate-check

ci: migrate-check typecheck test

test:
	cd backend && TEST_DATABASE_URL=$(TEST_DB) python -m pytest -q

typecheck:
	cd backend && python -m mypy app

migrate-check:
	cd backend && DATABASE_URL=$(CHECK_DB) SECRET_KEY=make-check-secret-key-32-chars-min \
		APP_ENV=dev alembic heads | grep -c "head" | grep -qx 1 \
		&& echo "alembic: precies één head"
