.PHONY: run test migrate stripe seed

run:
	uvicorn app.main:app --reload --port 8000

test:
	pytest -q

migrate:
	alembic revision --autogenerate -m "update" && alembic upgrade head

stripe:
	stripe listen --forward-to localhost:8000/webhooks/stripe

seed:
	python -m tests.seed
