#!/bin/sh
# Rebuild data/catalog.json from the sources. Needs a clone of github.com/pianoroll/SUPRA at $SUPRA (default ../SUPRA).
set -e
SUPRA=${SUPRA:-../SUPRA}
cp data/catalog.json /tmp/wh-prev-catalog.json
python3 tools/parse_supra.py "$SUPRA" /tmp/wh-supra.json
python3 tools/build_catalog.py /tmp/wh-supra.json "$SUPRA" .
python3 tools/select_loc.py
python3 tools/build_records.py
python3 tools/build_pieces.py
python3 tools/build_schedule.py /tmp/wh-prev-catalog.json
