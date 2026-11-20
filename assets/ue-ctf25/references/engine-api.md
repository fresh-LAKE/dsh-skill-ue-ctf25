# Engine APIs and conventions

## Sources and timing

Use the [original source index](source-index.md) to inspect exact event predicates and action order. The supplied project uses object Behaviors for most logic. Frame Events contain compatibility choices, initialization and the object library. Event order is `Frame events, Behaviors, Global events`.

`Process Start Event` first handles pause/resume, then invokes `frame_start` while Pause is off. Mario's movement behavior responds there. It then prepares collision masks/layers and processes MovingBlock correction. `movingblock_fix_end` is invoked after that correction; Mario's collision-box escape logic responds there. The later Instance, Gravity and Movable groups perform their respective processing. A declaration's position does not alone establish when a triggered callback runs: follow its call site.

`Process End Event` contains handlers for `frame_end`. The supplied excerpt does not itself start `frame_end`; preserve the caller in global/core events. These handlers initialize newly created instances, compensate riders on moving blocks, advance custom Bouncing-based animation, call `camera`, restore background layers, and synchronize Mario's visual position/angle/direction. A visual override applied earlier can be overwritten by that final synchronization.

The built-in pause is described as disabled by default in the manual. When pause support is used, Instance behavior checks `1000 <> -1`; other objects check the Pause object's Pause flag. Some core functions have different guards. Follow the relevant actual source rather than blindly adding conditions to every callback.

## Qualifiers and state

| Qualifier / state | Interface |
|---|---|
| Group.Instance | Foundation for Gravity and Movable; floating-point coordinates stored in Alterable Value X/Y |
| Instance 1000 | -1 disabled; 0 initialize; 1 normal; 2 restore |
| Instance 1002 | -1 no collision; 0 normal; 1 Mario collision type; 2 enemy collision type |
| Instance 1003 | 0 normal; 1 disable out of screen; 2 disabled until entering screen |
| Instance 1004 | 1 indicates crushed by a moving solid |
| Instance 1005 | 1 requests final display on level_back |
| Group.Gravity | 100–199; 100 is -1 disabled, 0 grounded, 1 airborne; 101 velocity, 102 gravity angle |
| Gravity 103–108 | Air acceleration/deceleration, water acceleration/deceleration, air/water maximum velocity |
| Gravity 109 | 0 applies acceleration |
| Group.Movable | 200–299; 200=-1 disabled; 201 speed; 202 angle |
| Movable 203 | -1 no collision response; 0 stop; 1 reverse; 2 set 204=1 for object-specific response |
| Movable 205 | Slope tolerance |
| Group.Enemy | 400 normal/death state (0/1), plus shared shell/star interaction and other enemy checks |
| Group.Solid / Platform | 900 selects collision type; -1 disabled, 0 general, 1 Mario, 2 enemy; Platform is one-way |
| Group.MovingBlock | Adds moving-solid correction; built-in movement requires ForEach `init_movement` |

Internal processing can also use temporary sentinel states such as -2. Do not assume documented public values exhaust every internal value, or that arbitrary high variable indexes are free.

`init` is a per-instance ForEach. Instance initialization synchronizes X/Y and sets 1000=1. If creating objects that must be usable immediately, follow the examples that explicitly set X/Y, 1000 and invoke `init`; frame-end initialization is a fallback. Objects with only MovingBlock can use their own initialization flag and `init_movement`, as the track-fireball example does.

Motion events for moving solids must not be put inside `frame_start` or `frame_end` loops per the manual. Position/angle snapshots at these stages are used for correction.

## Public collision helper

Invoke `instance_place_fix` as a ForEach on the selected Instance after setting these variables.

| Variable | Meaning |
|---|---|
| 1098 | Solid collision type to test |
| 1097=1 | Ignore Backdrop and Group.Solid |
| 1096=1 | Ignore Group.Platform |
| 1095 | Escape direction in degrees |
| 1094 | Maximum escape depth |
| 1093=1 | Disable depth limit |
| 1099 | Return 1 success, 0 not performed because maximum depth was exceeded |

Set all relevant arguments deliberately, since these variables persist on the object. Check the return before assuming relocation succeeded. Group.AutoPlace is a last-resort escape mechanism described in the manual.

Callbacks used in the examples include `gravity_down_finished`, `gravity_up_finished`, `movable_place_finished`, `gravity_hit_block_up`, and `gravity_hit_block_up_failed`. A callback handler must be top-level. ForEach functions are immediate and convenient but should not be multiplied unnecessarily in hot paths.

## Mario

| Variables | Role in supplied behaviors |
|---|---|
| AS / AT | Facing -1 or +1, and movement-control speed |
| AW | Gravity direction normalized to [0,360) |
| AX / AY | Relative left/right input |
| AU / AV / AZ | Last physical direction keys and delayed control after gravity-direction changes |
| AL | Previous collision animation for size-change detection |
| AQ | 0 normal, 1 crouched, >=2 stuck/correction state |
| AM / AN | Valid jump request and repeat-jump lock |
| AO / AC | Water-entry state and bubble timer |
| AP | Pipe-related state; gates differ between <=0 and =0 in different examples |
| AH / AI | Invincibility mode and timer; 1 injury, 2 star, 3 goal invincibility per comments |
| AE / AG | Deferred stomp response and head-hit sound suppression |

Movement applies `201 = Max(0, (AT-1)/8.0)` and `202 = 102 + 90*AS`. AT is not identical to the final physical speed. Reverse input slows AT before changing AS. Animation walking speed also uses AT.

Jumping writes 101; hold-to-jump-height adds further upward velocity during ascent. Swimming temporarily probes 24 pixels against gravity to choose swimming versus exiting water, then restores position. `mario_stomp` sets AE; the frame-end response writes 101=-9 or -13 depending on Fire 1. Injury opens the `受伤` flag; the injury behavior handles power-down/invincibility/death.

## Layers, audio and global state

Keep `sys_setting`, `level_back`, `level_main`, `level_info`, `level_circle`, `sys_pause`, `sys_overlap` intact. Physics temporarily uses `sys_overlap`; avoid unrelated editing there. Keep level_back scrolling consistent with level_main and avoid obscuring it with other backgrounds.

Use the Audio object's channel-indexed variables to control volume. UE's audio manager overwrites direct channel volume changes. Global game state is stored in Globalvar. Frame restart needs the engine's save/restore hooks because `Restart current frame` does not produce a normal Frame End and resets global-object variables in the documented version. Read the manual before porting between projects.
