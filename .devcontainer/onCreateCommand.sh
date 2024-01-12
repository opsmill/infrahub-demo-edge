#!/bin/bash

poetry config virtualenvs.create true
poetry install --no-interaction --no-ansi

docker compose pull
docker compose -f docker-compose.yml up -d
