.PHONY: sync sync-tla build test validate serve

TEMPORAL_MODEL ?= ../chambers-temporal-model
JAVA ?= java
TLA_JAR ?= $(TEMPORAL_MODEL)/.tools/tla2tools.jar

sync:
	python3 scripts/sync_source.py ../fundamentals

sync-tla:
	python3 scripts/sync_tla_visualization.py $(TEMPORAL_MODEL) --java $(JAVA) --tla-jar $(TLA_JAR)
	python3 scripts/build_tla_data.py --print-summary

build:
	python3 scripts/build_data.py --print-summary
	python3 scripts/build_tla_data.py --print-summary

test:
	python3 -m unittest discover -s tests -v

validate: test
	python3 scripts/build_data.py --check --print-summary
	python3 scripts/build_tla_data.py --check --print-summary
	python3 scripts/validate_site.py
	python3 scripts/validate_tla_site.py

serve:
	python3 -m http.server 8008 --directory site
