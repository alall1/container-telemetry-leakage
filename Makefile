.PHONY: build run analyze clean

build:
	docker build -t twc:mvp -f docker/Dockerfile .

run:
	python3 runner/run_experiment.py

analyze:
	python3 -m pip install -q pandas scikit-learn matplotlib
	python3 analysis/analyze.py

clean:
	rm -f data/dataset.csv
	rm -rf results/*

