#!/bin/sh
# Launch maxYMiser (MYM_2MB.PRG) in a Hatari window with the host MIDI keyboard as the ST's MIDI in.
# STE (for the DMA sample track), 4 MB, TOS 1.62 from your Hatari config. The MYM_V167 folder is
# drive C:, so songs/SNDH exports saved to C:\ land in that folder.
# The MIDI port is the first ALSA raw MIDI device matching a name in $MIDI_NAME, tried in order
# (default "Keystation QUAD-CAPTURE": the keyboard on USB, else the interface's MIDI in);
# override the device with MIDI_DEV=/dev/snd/midiCxDy.
# MIDI out goes to /dev/null (no echo back to the keyboard; "none" would disable MIDI in too). Hatari output goes to mym.log.
cd "$(dirname "$0")/MYM_V167" || exit 1

if [ -z "$MIDI_DEV" ]; then
    for name in ${MIDI_NAME:-Keystation QUAD-CAPTURE}; do
        port=$(amidi -l 2>/dev/null | grep -i "$name" | head -n 1 | awk '{print $2}')
        [ -n "$port" ] && break
    done
    if [ -z "$port" ]; then
        port=$(amidi -l 2>/dev/null | awk 'NR > 1 { print $2; exit }')
    fi
    if [ -n "$port" ]; then
        # hw:C,D,S -> /dev/snd/midiCcDd
        MIDI_DEV=$(echo "$port" | awk -F'[:,]' '{ printf "/dev/snd/midiC%sD%s", $2, $3 }')
    fi
fi

if [ -z "$MIDI_DEV" ] || [ ! -e "$MIDI_DEV" ]; then
    echo "No MIDI input device found (amidi -l lists none). Is the keyboard/interface connected?" >&2
    echo "Starting without MIDI." >&2
    MIDI_DEV=none
    MIDI_OUT=none  # disables MIDI entirely
else
    echo "MIDI in: $MIDI_DEV"
fi

exec hatari --confirm-quit no --machine ste --memsize 4 --harddrive . \
    --auto 'C:\MYM_2MB.PRG' --window --sound 44100 \
    --midi-in "$MIDI_DEV" --midi-out "${MIDI_OUT:-/dev/null}" "$@" > ../mym.log 2>&1
