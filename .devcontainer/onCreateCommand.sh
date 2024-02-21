#!/bin/bash

poetry config virtualenvs.create true
poetry install --no-interaction --no-ansi

docker compose pull
poetry run invoke start 
