PYTHON ?= python

.PHONY: setup run seed test

setup:
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) manage.py migrate

run:
	$(PYTHON) manage.py migrate
	$(PYTHON) manage.py runserver

seed:
	$(PYTHON) manage.py migrate
	$(PYTHON) manage.py seed

test:
	$(PYTHON) -m pytest

