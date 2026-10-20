# Input: mouse, keyboard, keypad, events

Index: [`README.md`](README.md). Code: `st/src/input.c`, `st/src/glue.S` (`ikbd_handler`,
mouse packet handler). Game-side logic that the keys trigger is partly patched: SCRIPTS.md.

## Overview

The Amiga interpreter read the mouse/joystick hardware in a poll (hunk 16 `+$160`, patched to
`c_input_poll`) and got keys through an input task ("FerretTask", hunk 15, not run on the ST).
The shim replaces all of it: mouse globals and the button flag are updated at interrupt time,
keys and mouse packets are decoded from the raw IKBD bytes, events are queued in a ring and
posted into Prog's event queue from the poll hook inside GetEvent. The autoplay script
(WORKFLOW.md "Test automation") feeds the same paths.

## Mouse

- SCI's button tracking reads the mouse globals (`-$6e60` button, `-$6e62/-$6e64` position,
  window `+$c/+$e`) in a loop without calling GetEvent: they must change at interrupt time (as
  FerretTask did). The mouse packet handler does that.
- kSetCursor with a position moved the pointer via input.device on the Amiga; hooked (hunk 17
  `+$aa`) so the pointer moves on the ST too.
- No double-click: an earlier "double-click skips the walk" feature (modifier bit `$80` on the
  second click, plus a patched `Ego::handleEvent`) was removed on 2026-10-20 at the user's request
  (it caused bugs here and there, and the game is about the journey).
- Both mouse buttons held together post an Esc key event (`mouse_buttons_changed`), so the mouse
  alone can skip the title sequence (SCRIPTS.md "Title skips"); in the game Esc opens the icon bar.
- The video driver's pointer show/hide counter is ignored (pointer always drawn, HANDOFF gap 6).

## Keyboard and keypad

TOS only reports key presses (the keyboard IOREC / `Bconin`), never releases, and its key tables
turn the keypad into digits, so the shim replaces the `ikbdsys` entry of the XBIOS `Kbdvbase`
table (TOS's ACIA interrupt handler calls it once per pending byte, in supervisor mode with
d0-d3/a0-a3/a5 saved): `ikbd_handler` reads the ACIA status, takes the byte from the data register
and passes it to `ikbd_byte`, which re-implements TOS's packet state machine (headers `$f6..$ff`
start packets of 7,5,2,2,2,2,6,2,1,1 bytes; everything else is a key make/break code, bit 7 =
release). Mouse packets go to the existing `mouse_handler`. Keys become SCI key events (type 4)
with TOS's key tables (`Keytbl`: unshifted / shifted / caps lock, ctrl-letter = `& $1f`) plus the
`special_key` table: arrows, Clr/Home, Insert, Delete, function keys (PC scancode `<< 8`), Undo =
Esc, Help = F1, and the numeric keypad as the Amiga and DOS interpreters report it - 7 8 9 / 4 5 6 /
1 2 3 = `$4700 $4800 $4900 / $4b00 $4c00 $4d00 / $4f00 $5000 $5100`, keypad 0 = Insert `$5200`,
keypad . = Delete `$5300`, keypad Enter = 13 (the Amiga keymap in Prog's data hunk, a4 `-$7516`,
gives the same codes for its keypad digits; it has no Insert, keypad 0 is `'0'` there).
Modifiers (shift/ctrl/alt) are tracked from their make/break codes; software key repeat (0.5 s,
then every 6 VBLs) runs from the VBL. TOS keyboard state (`Kbshift`, `Bconin`) is not used by the
shim and not updated while it runs (restored on exit). No joystick support: IKBD joystick event
reporting (command `$14`) switches the IKBD mouse off (tried, the mouse died), and interrogation
mode would need polling. The keypad cannot type digits in the game (use the number row).

Why a full replacement: TOS 1.62's ACIA handler (`$e03ca0`) loops over `midisys`/`ikbdsys` until
MFP GPIP bit 4 is high; its `ikbdsys` (`$e03cd4`) checks status bits 7 and 0 before reading the
data register, so a wrapper that reads the byte first cannot hand it on to TOS.

## What the game does with those codes

All original logic except the `kQPMouse` patch (SCRIPTS.md): `User::handleEvent` (script 996)
calls the kernel's `MapKeyToDir` on every key event; Prog's implementation (hunk 16 `+0`, table
at a4 `-$760e`) maps `$4800`→1 N, `$4900`→2, `$4d00`→3, `$5100`→4, `$5000`→5 S, `$4f00`→6,
`$4b00`→7, `$4700`→8 NW and `$4c00` (keypad 5)→0, setting type `$44` (direction + keyboard) and
clearing the modifiers. Direction events go first to global 77, KQ5's `kQPMouse` (script 0, a
`PseudoMouse` from script 933, patched to the plain class behaviour): with the walk cursor it
returns 0 and `User::handleEvent` passes the event to `Ego::handleEvent` (script 996):
`setDirection` (walk until something else happens), the same direction again while the mover
exists = stop, direction 0 (keypad 5) ignored; with any other cursor it moves the pointer by
`maxInc` = 20 pixels (`setCursor`) and claims the event; key repeat makes it glide. Then
`IconBar::handleEvent` (script 937): direction 0 (keypad 5) = `advanceCurIcon` (cycles the
cursors), key `$5200` Insert = `swapCurIcon` (walk ↔ last cursor), `$5300` Delete or Esc = show
the icon bar, Enter (13) = perform the current icon's action at the pointer (with the walk
cursor: walk there). This is the behaviour the KQ5 manual describes. User-tested: 5, 0, ., Enter
and pointer movement; the walk-cursor case awaits the user's test (HANDOFF.md).

History: the 2026-10-17 night version instead posted hold-to-walk direction events from the shim
and made `kQPMouse::handleEvent` return 0 always; reverted the same day after the user tested it.

## GetEvent and the event ring

`c_input_poll` is called at the start of Prog's `GetEvent(mask, event)` (hunk 14 `+$58`, a C
function, so the mask is at `8(a5)` when the hook at hunk 16 `+$160` runs) and posts only the
pending events whose type matches the mask; the others stay in the shim's ring for a later call.
Reason: Prog's GetEvent walks its queue for the first event matching the mask, clears that entry
and then advances the queue head by one - so a non-matching event at the head (an Esc) is silently
dropped whenever a later mouse event matches. `Game::newRoom` ends with a mouse-event flush
(`(Event new: 3)` loop) that runs after the new room's init, which for the title is ~3 s (pic
106's transition, font loading): an Esc with a click queued behind it was lost there.

Prog's event queue: head/tail pointers at `-$71cc`/`-$71c8(a4)`, 14-byte entries (type.w,
message.w, modifiers.w, time.l, y.w, x.w), post function at hunk 14 `+$1a4`.

## Hatari notes

- Keyboard joystick emulation (`[Joystick1] nJoystickMode = 2` with keypad keys in `hatari.cfg`)
  swallows those keys before they reach the ST; it must be off for the keypad to work (the user
  has turned it off).
- Headless key-level tests: the `ikbd byte` autoplay command feeds the decoder directly
  (`tests/numpad.txt`); Hatari's `--cmd-fifo` key injection was not completed.
