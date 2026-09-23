PY ?= .venv/bin/python

.PHONY: setup data validate test research strategy all

setup:            ## create .venv with all dependencies
	uv venv .venv
	uv pip install --python .venv/bin/python -e ".[dev,research]"

data:             ## download HistData 1-minute + Yahoo daily/hourly data (cached in data/raw)
	$(PY) scripts/download_data.py

validate:         ## proxy-vs-futures timestamp/return validation -> reports/data_validation.txt
	$(PY) scripts/validate_data.py

test:
	$(PY) -m pytest -q

research:         ## re-run the whole strategy search -> reports/research/
	mkdir -p reports/research
	set -e; for s in scripts/research/[0-9]*.py; do n=$$(basename $$s .py); \
		echo "== $$n"; $(PY) $$s > reports/research/$$n.txt; cat reports/research/$$n.txt; done

strategy:         ## final strategy numbers -> reports/strategy_results.md, trades_nq.csv, equity_nq.png
	$(PY) scripts/run_strategy.py

all: data validate test research strategy
