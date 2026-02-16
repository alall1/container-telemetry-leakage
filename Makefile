.PHONY: build run analyze clean venv

VENV=.venv
PY=$(VENV)/bin/python
PIP=$(VENV)/bin/pip

build:
	docker build -t twc:mvp -f docker/Dockerfile .

run:
	$(PY) runner/run_experiment.py

venv:
	python3 -m venv $(VENV)

analyze: venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q pandas scikit-learn matplotlib
	$(PY) analysis/analyze.py

clean:
	rm -f data/dataset.csv
	rm -rf results/*

