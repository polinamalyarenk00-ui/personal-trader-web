#!/bin/bash
set -e
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Установите Python 3.12 с https://www.python.org/downloads/'; exit 1
fi
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
exec .venv/bin/python -m streamlit run app.py
