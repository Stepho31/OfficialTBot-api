#!/usr/bin/env bash
export $(grep -v '^#' .env | xargs) && uvicorn app.main:app --reload --port 8000
