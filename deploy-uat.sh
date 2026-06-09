#!/bin/bash
git pull && docker compose -f docker-compose.uat.yml --env-file .env.uat up --build -d
