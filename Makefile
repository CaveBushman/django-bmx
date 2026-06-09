.PHONY: deps deps-upgrade install migrate test lint run

# Závislosti
deps:
	pip-compile requirements.in --output-file requirements.txt

deps-upgrade:
	pip-compile --upgrade requirements.in --output-file requirements.txt

install:
	pip install pip-tools
	pip-sync requirements.txt

# Django
migrate:
	python manage.py migrate

test:
	python manage.py test

lint:
	python manage.py check --deploy

run:
	python manage.py runserver

# Tailwind
css:
	npm run build --prefix theme/static_src

css-watch:
	npm run dev --prefix theme/static_src

# Statické soubory
static:
	python manage.py collectstatic --noinput
