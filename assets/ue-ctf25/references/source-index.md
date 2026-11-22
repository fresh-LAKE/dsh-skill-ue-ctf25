# Source index

The package covers the UE preparation material supplied in this chat. Original captures are preserved byte-for-byte and each captured payload was checked against its embedded length and SHA-256. Read the text first for event/API tasks, and use JSON/binary files when constructing or inspecting clipboard data.

## Format and tooling (read before generating events)

- [Binary event format](event-binary-format.md) — decoded `CF_CNCV25_EVENTS`: package header, event/record headers, parameters, `SJBO` object table (Active/Group, icons, qualifier ids), `TYAL`, trailer.
- [Opcode cookbook](opcode-cookbook.md) — verified condition/action templates with byte offsets, parameter layouts, Mario variable indices, expression fingerprints and the four look-alike jump branches.
- [Clipboard workflow](clipboard-workflow.md) — direct import/export from the agent shell, verification loop, fallback.
- [Verification workflow](event-verification.md) — local structure checks, readback comparison, regression self-test.
- `scripts/ctf_events.py` — parse / describe / verify / build library with provenance-checked templates (`selftest` round-trips supported event exports and explicitly skips whole-behavior wrappers).
- `scripts/ImportAndVerify.ps1` — import a package to the clipboard and compare the readback hash in one command.
- `scripts/example_infinite_jump.py` — worked example: flag-gated mid-air jump.

## Manual

- [UE Manual.pdf](UE%20Manual.pdf) — original 22-page manual for Super Mario Ultra Edition 231211.1.
- [Searchable extraction](UE%20Manual-extracted.txt) — contains extraction artifacts; screenshots require the PDF.
- [Source manifest](source-manifest.json) — original filenames, hashes and provenance.

## Engine and Mario

| Subject | Readable source | Original binary/capture |
|---|---|---|
| Main-event comments | [Comments](original-code/frame-events-comment-conversation.txt) | User message, transcription |
| Mario init | [Events](original-code/mario-init.txt) | [Raw event bytes](original-code/mario-init.bin) |
| Mario animation | [Events](original-code/mario-animation.txt) | [Event capture](original-code/mario-animation.json), [whole Behavior capture](original-code/mario-animation-whole-behavior.json) |
| Mario movement | [Events](original-code/mario-movement.txt) | [Capture](original-code/mario-movement.json) |
| Mario injury/invincibility/death | [Recovered events](original-code/mario-hurt-conversation.txt) | Original binary no longer available |
| Process Start Event | [Events](original-code/process-start.txt) | [Capture](original-code/process-start.json) |
| Process End Event | [Recovered events](original-code/process-end-conversation.txt) | Original binary no longer available |
| Verified generated test, Always → Mario.BW=1 | See clipboard workflow | [User-verified capture](original-code/validated-mario-bw1.json) |

The old fixed-name export file was overwritten before Mario injury and Process End were separately archived. Their complete visible event text was recovered from this chat, with whitespace normalized. No original binary was invented for them. The main-event comment is also transcribed from the user's message. These sources support reading and implementation reference; they cannot be imported as their original binary captures.

## Object examples

| Subject | Readable source | Original capture |
|---|---|---|
| Goomba init | [Events](original-code/goomba-init.txt) | [Capture](original-code/goomba-init.json) |
| Goomba attacked | [Events](original-code/goomba-attacked.txt) | [Capture](original-code/goomba-attacked.json) |
| Goomba hurt mario | [Events](original-code/goomba-hurt-mario.txt) | [Capture](original-code/goomba-hurt-mario.json) |
| Blue flying Koopa init | [Events](original-code/fly-troopa-blue-init.txt) | [Capture](original-code/fly-troopa-blue-init.json) |
| Blue flying Koopa attacked | [Events](original-code/fly-troopa-blue-attacked.txt) | [Capture](original-code/fly-troopa-blue-attacked.json) |
| New stomp API | [Events](original-code/fly-troopa-blue-stomp.txt) | [Capture](original-code/fly-troopa-blue-stomp.json) |
| Track fireball init | [Events](original-code/lavaball-track-init.txt) | [Capture](original-code/lavaball-track-init.json) |
| Track fireball hurt mario | [Events](original-code/lavaball-track-hurt-mario.txt) | [Capture](original-code/lavaball-track-hurt-mario.json) |
| Track fireball animation / binding | [Events](original-code/lavaball-track-animation.txt) | [Capture](original-code/lavaball-track-animation.json) |

Repeated identical Blue Koopa attacked exports were consolidated into one reference capture. Their repeated copies remain in the originating workspace. The captured code is preserved as supplied, including commented-out blocks and potential edge cases. The newer Immediate Condition rule governs generated/modified events.

## Later user clarifications

- All green Immediate Conditions belong at event top level. Nested loop callbacks can crash Fusion. Starting a loop is an action and may be nested.
- Focus on API usage and comments; core implementation details are secondary unless a concrete change depends on them.
- The newer stomp implementation substantially reduces false classifications in fast vertical movement.
- Goomba belongs to Instance, Gravity, Movable, Enemy and EnemyTurn, with walking speed as its only custom setting.
- The invisible track-fireball body belongs only to MovingBlock; its visible child has no Behaviors/qualifiers and plays its animation normally. Runtime binding uses child F and Flag 21.
