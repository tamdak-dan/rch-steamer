#!/usr/bin/env bash
# Set the model-change PIN (25/50 SLM). Installed as /usr/local/bin/rch-set-pin.
# See deploy/set_model_pin.py for the options (--status, --default).
exec /opt/rch-steamer-venv/bin/python /opt/rch-steamer/deploy/set_model_pin.py "$@"
