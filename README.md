# UE for Clickteam Fusion 2.5

DeepSeek Harness bundle that ships the `ue-ctf25` skill: Super Mario Ultra Edition
(UE) event development and verification in Clickteam Fusion 2.5.

The skill is registered through `ctx.skills` and loads on demand, either by the
model or through the skill row in the Web UI. Its instructions document UE
Behavior APIs, object qualifiers, the binary event clipboard, and the fixed
verification workflow. `assets/ue-ctf25` is the original plugin's skill tree,
extended with local binary-event tooling while retaining its relative links and
original reference captures.

## Contents

| Path | Purpose |
|---|---|
| `assets/ue-ctf25/SKILL.md` | Skill body and constraints |
| `assets/ue-ctf25/references/` | UE manual, API notes, event captures, samples |
| `assets/ue-ctf25/scripts/` | `ClipboardBridge.ps1`, `verify_events.py` |

## Limits

The plugin does not modify Fusion. Generated event data must still be pasted
into Fusion and verified there; the bundled verifier only checks structure and
references locally. UE here means Super Mario Ultra Edition, not Unreal Engine.

## Development

This project was developed with the assistance of ChatGPT and DeepSeek models.
