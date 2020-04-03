#! /usr/bin/env sh
exec gunicorn -b 0.0.0.0:8000 -w 4 -k uvicorn.workers.UvicornH11Worker app:app
