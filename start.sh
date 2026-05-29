#!/bin/bash
set -a
source .env
set +a
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2
