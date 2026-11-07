#!/bin/sh
# Play KQ5ST in a Hatari window (STE, TOS 1.62 from your Hatari config, normal speed). Sound is
# forced on here because a saved Hatari config may have bEnableSound = FALSE (happened 2026-10-17).
# Debug output from the shim goes to play.log.
#   ./play.sh [hatari args]                         YM2149 sound
#   ./play.sh --mt32 MIDI-OUT-DEVICE [hatari args]  MT-32 driver, ST MIDI OUT -> that device
#     e.g. /dev/snd/midiC2D0 (list with "amidi -l": hw:2,0 = midiC2D0), or a file to capture.
#   ./play.sh --munt ROMDIR [hatari args]           MT-32 driver played through Munt
#     (tools/mt32bridge, built with its build.sh; ROMDIR holds MT32_CONTROL.ROM + MT32_PCM.ROM).
#   Both MT-32 modes create hd/MT32 for the run and remove it afterwards (docs/WORKFLOW.md
#   "MT-32 in Hatari").
ST=$(cd "$(dirname "$0")" && pwd)
MIDI_OUT= MUNT_ROMS=
case "$1" in
--mt32) MIDI_OUT=${2:?usage: play.sh --mt32 MIDI-OUT-DEVICE [hatari args]}; shift 2 ;;
--munt) MUNT_ROMS=${2:?usage: play.sh --munt ROMDIR [hatari args]}; shift 2 ;;
esac
cd "$ST/hd"
rm -f AUTO.TXT
cleanup() { :; }
if [ -n "$MUNT_ROMS" ]; then
    BRIDGE="$ST/../tools/mt32bridge/mt32bridge"
    [ -x "$BRIDGE" ] || { echo "build $BRIDGE first (tools/mt32bridge/build.sh)" >&2; exit 1; }
    MIDI_OUT="$ST/munt.fifo"
    rm -f "$MIDI_OUT"; mkfifo "$MIDI_OUT"
    "$BRIDGE" "$MUNT_ROMS" "$MIDI_OUT" 2> "$ST/munt.log" \
        | pw-cat --playback --raw --rate 32000 --channels 2 --format s16 - &
    PLAYER=$!
    cleanup() { kill $PLAYER 2>/dev/null; pkill -f "mt32bridge .*munt.fifo" 2>/dev/null; rm -f "$MIDI_OUT"; }
fi
MADE_FLAG=
if [ -n "$MIDI_OUT" ]; then
    if [ ! -e MT32 ]; then touch MT32; MADE_FLAG=1; fi
    set -- --midi-in /dev/null --midi-out "$MIDI_OUT" "$@"
elif [ -e MT32 ]; then
    echo "note: hd/MT32 exists, so the game uses the MT-32 driver (YM silent)" >&2
fi
trap 'cleanup; [ -n "$MADE_FLAG" ] && rm -f MT32' EXIT INT TERM
hatari --confirm-quit no --natfeats yes --machine ste --harddrive . \
    --auto 'C:\KQ5ST.PRG' --window --sound 44100 "$@" > ../play.log 2>&1
