#!/bin/sh
# Headless test run (no window): ./run.sh [vbls] [autoplay-script] [extra hatari args...]
# Log goes to run.log, screenshots to hd/SHOTnn.ST (taken only when a script is given).
cd "$(dirname "$0")"
VBLS=${1:-3000}; [ $# -gt 0 ] && shift
rm -f hd/AUTO.TXT
if [ -n "$1" ] && [ -f "$1" ]; then cp "$1" hd/AUTO.TXT; shift; fi
cd hd
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy timeout 900 hatari --confirm-quit no --natfeats yes \
    --machine ste --harddrive . --auto 'C:\KQ5ST.PRG' --fast-forward yes --sound off \
    --run-vbls "$VBLS" --log-level error "$@" > ../run.log 2>&1
echo "exit $?" >> ../run.log
rm -f AUTO.TXT
cat ../run.log
