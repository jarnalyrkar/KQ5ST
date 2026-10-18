#!/bin/sh
# Play KQ5ST in a Hatari window (STE, TOS 1.62 from your Hatari config, normal speed). Sound is
# forced on here because a saved Hatari config may have bEnableSound = FALSE (happened 2026-10-17).
# Debug output from the shim goes to play.log.
cd "$(dirname "$0")/hd"
rm -f AUTO.TXT
exec hatari --confirm-quit no --natfeats yes --machine ste --harddrive . \
    --auto 'C:\KQ5ST.PRG' --window --sound 44100 "$@" > ../play.log 2>&1
