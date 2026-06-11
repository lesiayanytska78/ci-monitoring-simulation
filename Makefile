# One-command entry points for the repository.
#   make install   install dependencies
#   make figures   regenerate all paper figures from the released CSVs in data/
#   make test      run the test suite
#   make all       install, regenerate figures, and test

.PHONY: install figures test all

install:
	python -m pip install -r requirements.txt pytest

figures:
	python plot_paper_figs.py

test:
	pytest -q

all: install figures test
