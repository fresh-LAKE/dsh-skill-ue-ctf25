# Clipboard workflow and binary limits

Use the [fixed verification workflow](event-verification.md) before delivering generated events and when comparing a Fusion readback.

## Read and export

The user's Windows session can access Fusion's custom clipboard formats. The agent's shell in the original session returned Windows error 5 for OpenClipboard. Do not keep retrying unchanged access failures or assume every environment has the same limitation. Use direct authorized access if available; otherwise the user runs the supplied bridge in their desktop PowerShell and the agent reads the resulting file.

Copy `scripts/ClipboardBridge.ps1` to the task's writable exchange/output folder. Running it without arguments exports all supported memory-backed formats to a filename based on **local system time**, down to milliseconds, beside the script. Export always chooses the timestamped name, even if -Path is supplied. -Path is for import only. Do not restore the old fixed-name export behavior.

```powershell
powershell.exe -NoProfile -STA -File "C:\path\to\exchange\ClipboardBridge.ps1"
```

Exports contain format ID/name, raw bytes as Base64, length and SHA-256. Validate every payload's length/hash before transforming it. Use CF_UNICODETEXT (ID 13) for exact readable event content when available. `CF_CNCV25_EVENTS` contains event binary data. `MMF2BEHAVIOR` is a whole-behavior wrapper and may have no text format; it still contains the events. Readable text alone has not been established as importable Fusion events.

When several files arrive, use names/timestamps and decoded contents to match the user's order. Deduplicate by payload hashes for analysis without deleting source files. Never silently treat an empty Formats array or an older capture as the newly requested behavior.

The helper reads HGLOBAL data; unsupported handle formats are marked skipped. It does not promise a complete serialization of every possible OLE object. The original helper caps a single payload at 128 MiB.

## Import

```powershell
powershell.exe -NoProfile -STA -File "C:\path\to\exchange\ClipboardBridge.ps1" -Mode Import -Path "C:\path\to\event.json" -FormatName CF_CNCV25_EVENTS
```

Import validates selected custom-format hashes, registers format names in the current session and replaces the clipboard with the selected formats. Numeric registered format IDs can vary by session. A successful import call does not establish that Fusion accepts a modified event. Have the user verify the pasted conditions, selected objects, variables and runtime behavior relevant to the change.

## Observed binary layout, not a complete format specification

The supplied event samples begin with `KLBEDAEH`, contain `STVE` followed by a little-endian uint32 event-stream length, and end the stream with a zero int16. In these samples the stream begins at byte 24. Subsequent metadata includes comment records (`SMER`), object descriptions (`SJBO`), icons/layout and `!DNE`.

Observed event records have a negative int16 record length, one-byte condition/action counts, and a 14-byte header. Conditions have 16-byte headers and actions 14-byte headers; each record and parameter is length-prefixed. These observations apply to the supplied samples. Unknown headers, event flags, group pointers, expressions or object maps require a matching reference or further decoding.

Preserve/rebuild record lengths, counts, stream lengths, group structure, object mappings and expressions together. **Green immediate conditions may never be nested under another event.** Validate semantics and hierarchy, not only byte lengths. Object indexes in a source clipboard package are local to its object metadata; they are not universal object IDs. Keep metadata from the relevant target and inspect pasted object assignments.

The verified simple mutation reused Mario's `AS=1` action, changed its zero-based variable index from 44 to BW=74, and combined it with a top-level Always. `original-code/validated-mario-bw1.json` is the actual user-verified payload. It retained the original object's metadata. `original-code/mario-init.bin` is the source raw capture. Do not apply fixed offsets from these samples to unrelated exports.

When generating other event forms, prefer reusing verified records and editing understood fields. Recompute Base64, Length and SHA256 for the final package. Inspect immediate-condition placement, object selection, parameter types, expressions, top-level grouping and callbacks before proposing import. Structural validation is distinct from successful Fusion paste and runtime verification.
