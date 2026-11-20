# Fixed verification workflow

Run these commands from the skill root for the examples. For actual work, pass absolute paths or paths relative to your current directory. The verifier uses Python 3's standard library and no machine-specific configuration. It processes files locally and does not open the clipboard.

1. **Keep a reference export.** Copy the relevant target events from Fusion with ClipboardBridge. Identify the target object names, conditions, actions, values, and intended event position from that export.
2. **Check the generated payload.** Run `python scripts/verify_events.py candidate.json --dump`. For transformations intended to preserve all metadata byte-for-byte, add `--template target-export.json`. Skip that comparison when comments or object metadata intentionally change, and review those changes separately. Check IDs and parameter bytes against the source records. Review object selection, expressions, event order and every green Immediate Condition before import.
3. **Paste and re-export.** Use ClipboardBridge import. Paste into the intended event list in a test copy and inspect Fusion's displayed conditions and actions. Re-copy just the inserted events as a new JSON export.
4. **Compare the readback.** Run `python scripts/verify_events.py candidate.json --readback fusion-readback.json`. An exact match applies to the event payload, independently of the session-assigned clipboard ID. On mismatch, validate and dump the readback separately, compare both event lists in Fusion, and record any differences. A runtime behavior change still needs an in-engine test.

The verifier checks clipboard hashes and lengths, sample-format package and stream boundaries, event and parameter counts, and known nested Immediate Conditions. It recognizes the observed `On loop` and Active-object ForEach IDs. Add other confirmed pairs with `--immediate TYPE,OPCODE`, using the equals form for negative types (for example `--immediate=-1,-16`). A group container may use a nonzero hierarchy field for top-level events, so the checker uses the observed child-event flag for the nesting check. This is not a full Fusion decoder or object-table validator. It expects complete `CF_CNCV25_EVENTS` packages and does not parse bare streams or `MMF2BEHAVIOR` wrappers.

## Reference runs

```powershell
python scripts/verify_events.py references/original-code/mario-init.bin
python scripts/verify_events.py references/original-code/validated-mario-bw1.json --dump
python scripts/verify_events.py references/verification-samples/run-fullspeed.json --template references/original-code/mario-movement.json --readback references/verification-samples/run-fullspeed-readback.json --dump
```

The last two files come from the maintainer's `ue-ctf25_20261119_2245.zip`. The readback is its `ctf-clipboard-2026-11-19_22-43-47-574.json`. The example has one top-level event, three conditions (held Fire 2, Mario 1000 and 200 both unequal to -1), and one action (Mario AT=60). The numeric value is specific to the example. Its captured readback matches the payload byte-for-byte.
