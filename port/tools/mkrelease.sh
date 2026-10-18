#!/bin/sh
# Package the playable game folder for a GitHub release: tools/mkrelease.sh VERSION
# -> dist/KQ5ST-VERSION.zip with KQ5ST/ (the game folder, from st/hd) and READ_ME.TXT.
# Leaves out saved games, screenshots, debug files and flag files from testing.
set -e
cd "$(dirname "$0")/.."
VER=${1:?usage: tools/mkrelease.sh VERSION}
OUT=dist/KQ5ST-$VER
rm -rf "$OUT" "$OUT.zip"; mkdir -p "$OUT/KQ5ST"
for f in st/hd/*; do
    case "$(basename "$f")" in
        KQ5sg.*|SHOT*|AUTO.TXT|HELLO.PRG|KQ5ST.sym|NOSND|NOBLIT|KTRACE|YM_TRACE|*.avi|*.log) ;;
        *) cp "$f" "$OUT/KQ5ST/" ;;
    esac
done
sed "s/@VERSION@/$VER/" tools/READ_ME.TXT | sed 's/$/\r/' > "$OUT/READ_ME.TXT"
(cd "$OUT" && zip -qr -X "../KQ5ST-$VER.zip" READ_ME.TXT KQ5ST)
ls -l "$OUT.zip"
