.PHONY: setup config smoke dashboard list prep clean

# Pick a Python >= 3.10 (the repo requires it). Override: make setup PYTHON=/path/to/python
PYTHON ?= $(shell command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3)
# For run targets, prefer the project venv if it exists.
PY_RUN := $(if $(wildcard .venv/bin/python3),.venv/bin/python3,$(PYTHON))

setup:
	$(PYTHON) -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	.venv/bin/playwright install chromium
	@echo ""
	@echo "Setup complete (using $(PYTHON)). Run: make config"

config:
	@[ -f config/profile.yml ] \
		&& echo "config/profile.yml already exists — skipping" \
		|| (cp config/profile.example.yml config/profile.yml && echo "Created config/profile.yml")
	@[ -f config/standard_answers.yml ] \
		&& echo "config/standard_answers.yml already exists — skipping" \
		|| (cp config/standard_answers.example.yml config/standard_answers.yml && echo "Created config/standard_answers.yml")
	@[ -f config/targets.yml ] \
		&& echo "config/targets.yml already exists — skipping" \
		|| (cp config/targets.example.yml config/targets.yml && echo "Created config/targets.yml")
	@echo ""
	@echo "Edit config/profile.yml with your details, then run: make smoke"

smoke:
	bash scripts/smoke_test.sh

dashboard:
	$(PY_RUN) tools/generate_dashboard.py \
		--pipeline pipeline.md \
		--tasks tasks.md \
		--output dashboard/index.html

list:
	$(PY_RUN) run_applications.py --list

# Build a drill plan for a company from the shared question-bank repo.
# Usage: make prep COMPANY=databricks
prep:
	@[ -n "$(COMPANY)" ] || { echo "Usage: make prep COMPANY=<name>  (e.g. make prep COMPANY=databricks)"; exit 1; }
	$(PY_RUN) tools/prep_company.py --company "$(COMPANY)"

clean:
	rm -rf .venv __pycache__ agents/__pycache__ tools/__pycache__ prep-plans *.log
