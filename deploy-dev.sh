#!/bin/bash
git pull && sudo docker compose -f docker-compose.dev.yml --env-file .env.dev up --build -d
