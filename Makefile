.PHONY: setup config smoke dashboard list clean

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	.venv/bin/playwright install chromium
	@echo ""
	@echo "Setup complete. Run: make config"

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
	python3 tools/generate_dashboard.py \
		--pipeline pipeline.md \
		--tasks tasks.md \
		--output dashboard/index.html

list:
	python3 run_applications.py --list

clean:
	rm -rf .venv __pycache__ agents/__pycache__ tools/__pycache__ *.log
