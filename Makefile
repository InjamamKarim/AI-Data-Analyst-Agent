VENV := data-agent-env
PY := $(VENV)/bin/python

.PHONY: setup seed test api eval host smoke

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

seed:
	$(PY) -m backend.db.seed

test:
	$(PY) -m pytest -q

api:
	$(PY) -m uvicorn backend.main:app --reload

eval:
	$(PY) -m eval.ablation

host:
	$(PY) scripts/check_host.py

smoke:
	$(PY) -m eval.harness --demo --limit 5
