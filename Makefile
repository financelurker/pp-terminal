.DEFAULT_GOAL := build
CHECK_DIRS = pp_terminal tests

clean:
	rm -rf dist __pycache__ *.pyc *.pyo

install:
	poetry install $(ARGS)
	patch -p1 < ./patch_ppxml2db.diff

check:
	poetry run pylint $(CHECK_DIRS)
	poetry run bandit -c bandit.yaml -r $(CHECK_DIRS)
	poetry run mypy $(CHECK_DIRS)

test:
	poetry run pytest

build:
	poetry build
