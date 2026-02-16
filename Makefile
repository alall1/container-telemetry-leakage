.PHONY: build run analyze clean
VENV=.venv
PY=$(VENV)/bin/python
PIP=$(VENV)/bin/pip

$(VENV)/bin/activate:
	python3 -m venv $(VENV)

build:
	docker build -t twc:mvp -f docker/Dockerfile .

run:
	python3 runner/run_experiment.py

analyze: $(VENV)/bin/activate
	$(PIP) install -q --upgrade pip
	$(PIP) install -q pandas scikit-learn matplotlib
	$(PY) analysis/analyze.py

clean:
	rm -f data/dataset.csv
	rm -rf results/*

