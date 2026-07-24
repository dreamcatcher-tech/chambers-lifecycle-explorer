.PHONY: sync build test validate serve

sync:
	python3 scripts/sync_source.py ../fundamentals

build:
	python3 scripts/build_data.py --print-summary

test:
	python3 -m unittest discover -s tests -v

validate: test
	python3 scripts/build_data.py --check --print-summary
	python3 scripts/validate_site.py

serve:
	python3 -m http.server 8008 --directory site
