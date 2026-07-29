#!/usr/bin/env bash
set -e
pip install -r requirements.txt
python -c "from db import init_db; init_db(); print('[build] db initialized')"
python -c "from app import bootstrap_admin; bootstrap_admin()"
