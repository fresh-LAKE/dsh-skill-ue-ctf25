"""示例：用模板拼一个“被 Flag 0 门控的空中再跳”事件包。

这是 skill 的快速路径样板：所有记录都来自已验证导出，只改对象 id / 数值 / 运算符，
并用指纹确认拿到的是“地面跳跃（跳跃初速度 + 103）”而不是“跳出水（105）”分支。

运行：
    python example_infinite_jump.py [输出.json]
"""
import sys
from pathlib import Path

from ctf_events import (Package, Obj, new_event, template, set_param_u16,
                        set_param_u32, TYAL)

OBJ_FLAG = 1          # 新 Active 的 id（0 是 Mario）
OBJ_NAME = "无限跳"

# --- 条件 ---------------------------------------------------------------
flag_on = template("flag_on")
flag_on.obj = OBJ_FLAG

key = template("key_repeat")                       # Repeat while fire 1

v1000 = template("cmp_value_53")                   # Mario 1000 <> -1

v100 = template("cmp_value_53")                    # -> Mario 100 = 1
set_param_u32(v100, 0, 8, 100)                     # P0 目标下标
set_param_u16(v100, 1, 0, 0)                       # P1 运算符: 0 = "="
set_param_u32(v100, 1, 8, 1)                       # P1 值

aq0 = template("cmp_value_50")                     # Mario AQ = 0
an0 = template("cmp_value_50")                     # Mario AN = 0
set_param_u32(an0, 0, 0, 0x27)
ao0 = template("cmp_value_50")                     # Mario AO = 0（不在水中）
set_param_u32(ao0, 0, 0, 0x28)

# --- 动作 ---------------------------------------------------------------
jump = template("mario_jump_ground")               # 101 = 0 - 跳跃初速度 - 103
an_set = template("mario_an_set")                  # AN = 1
sound = template("play_mario_jump")                # Sound: mario_jump

event = new_event([flag_on, key, v1000, v100, aq0, an0, ao0],
                  [jump, an_set, sound])

pkg = Package(bytes([6, 4, 1, 0]), 0x30,
              [event],
              [Obj(0, 2, "Mario"), Obj(OBJ_FLAG, 2, OBJ_NAME)],
              b"TYAL" + (62).to_bytes(4, "little") + TYAL + b"!DNE")

errs = pkg.verify()
if errs:
    raise SystemExit("\n".join(errs))

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("infinite-jump.json")
data = pkg.save(out)
print(pkg.describe())
print(f"wrote {out} ({len(data)} bytes)")
