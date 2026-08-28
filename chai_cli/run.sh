#!/bin/bash

python3 -m venv .venv
source venv/bin/activate
pip install -U pip setuptools wheel
pip install -e ".[live]"
