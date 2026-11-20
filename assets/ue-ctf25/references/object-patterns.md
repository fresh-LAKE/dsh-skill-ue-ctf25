# Enemy and animation patterns

Read the named files in [original-code](source-index.md) for the complete predicates, qualifiers, flags and actions.

## Goomba

The user specifies Instance, Gravity, Movable, Enemy, EnemyTurn, with walking speed as the only custom parameter. This does not mean the object has no engine-reserved variable storage.

`goomba-init.txt` sets collision type 1002=2 and entry-screen activation 1003=2, copies enemy gravity defaults, writes walking speed to 201, converts the editor direction to degrees with `Dir*11.25`, and sets 203=1 (reverse) and 205=4.

`goomba-attacked.txt` shows death state 400=1, legacy screen-Y stomp testing, `mario_stomp`, `enemy_death`, immediate initialization of Goomba Death 2, and fireball/beet damage. `goomba-hurt-mario.txt` checks overlap, both instance enable states and Mario invincibility before setting injury. Legacy stomp uses Goomba.Y >= Mario.Y+16; the contact-damage test uses Mario.Y > Goomba.Y-16.

## Blue flying Koopa and the newer stomp API

`fly-troopa-blue-init.txt` sets 100=1 initially. Whenever 100=0, it writes 101 to the negative jump-height parameter, producing repeated bounces. 202 also drives the object's displayed direction.

`fly-troopa-blue-attacked.txt` first checks overlap and enemy enable state, then invokes the enemy's `stomp_start`. That handler sets 411=16, calls `stomp_detect`, and reads 410. On success it invokes `mario_stomp`, awards 200 points and transforms the flyer into an oriented Troopa Blue, explicitly initializing the new instance. On failure it checks Mario's enable and invincibility before setting injury.

The complete `fly-troopa-blue-stomp.txt` implements:

- Argument 411: stomp height.
- Return 410: 1 stomped, 0 not stomped.
- frame_start records the enemy's current position in 490/491.
- 492 is scratch storage for enemy displacement projected onto Mario's gravity axis, then for the temporary test displacement.
- Compare Mario's gravity-axis velocity 101 with that enemy displacement. When appropriate, temporarily move Mario along the gravity axis, test overlap and restore both variable and displayed coordinates.

The user specifically confirms that this approach significantly reduces misclassification during **high-speed vertical motion**. Prefer it for fast jumping/moving enemies and arbitrary gravity when relevant. It is a predicate used after an overlap gate, not a complete swept collision detector. Its original comments still warn that jumping Koopas/Bowser may need delayed post-stomp operations, and direct coordinate changes from bridges/vortices/wind can interfere.

Do not copy these object-local handler names/variables into a generic qualifier without handling instance selection. Keep `frame_start`, `stomp_start`, and `stomp_detect` immediate-condition handlers top-level.

## Parent and child animation binding

The user's track fireball has an invisible `Lavaball on track` body belonging **only to Group.MovingBlock**. Its `Lavaball Animation` child has no behaviors or qualifiers and animates normally. The parent writes the child's F and Flag 21 at runtime, even though it has no separately configured custom behavior/variables.

`lavaball-track-init.txt` uses Flag 20 for one-time setup, sets the built-in movement parameters, then calls `init_movement`. `lavaball-track-hurt-mario.txt` opens Mario's injury flag on qualifying overlap.

In `lavaball-track-animation.txt`:

1. At frame_end, run `turning` ForEach for every body.
2. For a body with O=0, create its child, write the parent's Fixed value to child F, and set O=1.
3. In **each** independent handler, match child F to Fixed(current parent) before reading/updating that child. ForEach selects the current parent; the comparison selects its child.
4. Synchronize the child at body position +(16,16). Derive the target facing from movement components 311/312. Child Flag 21 gates initial facing, parent U/V store current/target angles, and subsequent events rotate in 15-degree steps.

The raw rotation code is an example supplied by the user, not a generalized rotation helper. If modifying it, account for zero angle difference in its division-based sign expressions and any desired final-step clamping. The example has no parent/child destruction cleanup; add it when the requested object's lifecycle requires it. A child object's own normal animation playback does not require an Instance qualifier or a Behavior.
