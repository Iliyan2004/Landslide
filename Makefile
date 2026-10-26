.PHONY: registries test demo api up frontend
registries:        ; python scripts/build_registries.py
test:              ; cd backend && PYTHONPATH=. python -m unittest discover -s tests -t . -v
demo:              ; cd backend && PYTHONPATH=. python ../scripts/run_pipeline.py
api:               ; cd backend && uvicorn landslide.api.main:app --reload --port 8000
up:                ; docker compose up --build
frontend:          ; cd frontend && npm install && npm run dev
