# 固定验证流程

目标：把“结构正确”和“Fusion 里真的对”分开，二者都要过。

## 0. 生成（优先用库，不要从零拼字节）

```powershell
python scripts/ctf_events.py describe candidate.json    # 对象名、条件/动作、参数摘要
python scripts/ctf_events.py verify   candidate.json    # 结构、对象引用、立即条件层级
```

`describe` 输出里能看到已知条件/动作名称、对象 id 对应的名字，以及参数体的十六进制摘要
（每个参数最多显示前 30 字节）。长表达式的指纹可能不在摘要里，须用模板断言或 `find --contains` 核对。
**用数字核对语义**，不要只凭“看起来像”：

- 例：`101 = 0 - 跳跃初速度 - AltValN(103)` 的表达式里必须出现 `67 00 00 00`（103），
  出现 `69 00 00 00`（105）就是拿成了“跳出水”分支。
- `template("mario_jump_ground")` 已内置这条指纹断言；自己拼的时候也要断言。

## 1. 保留参考导出

改任何事件前，先让用户从 Fusion 复制相关事件，用
[ClipboardBridge](clipboard-workflow.md) 导出并确认身份（时间戳/哈希）。
记下目标对象名、限定符、变量/标志位编号、期望插入位置。

## 2. 本地校验生成包

```powershell
python scripts/verify_events.py candidate.json --dump
python scripts/verify_events.py candidate.json --template target-export.json   # 只改事件、元数据不变时
```

`--template` 要求元数据逐字节相同；新增对象或改对象表时不要加。

补充检查（`verify_events.py` 不覆盖的）：

- 每个条件/动作头及已知 t1 参数引用的对象 id 都在 SJBO 里（`ctf_events.py verify` 会查）；
  表达式、创建对象等其它参数中的对象引用尚未完整解析，仍须人工核对；
- 立即条件（`On loop`、`On each one`）只出现在顶层或组容器之下——
  普通子事件以事件头 `0x8000` 标志判断，不能只看层级字段是否非零。
  新旧校验器目前自动识别的立即条件均仅有上述两类，其它绿色立即条件须人工检查；
- 参数里的数字符合预期（变量下标、标志位编号、运算符）；
- 事件头：`id`/`previous id` 从 1 开始、第一个的 previous=0。

## 3. 粘贴并重新导出

用 ClipboardBridge Import（见 clipboard-workflow），请用户在测试副本里粘贴，
检查 Fusion 显示的：
条件顺序与取反、对象名、变量/标志编号、动作参数、插入层级。

然后只重新复制**刚插入的事件**，再导出成 readback JSON。

## 4. 回读比对

```powershell
python scripts/verify_events.py candidate.json --readback fusion-readback.json
```

逐字节相同只说明事件载荷没被 Fusion 改写；**运行效果仍要进游戏测**。

## 5. 回归自测（改脚本/模板后必跑）

```powershell
python scripts/ctf_events.py selftest     # 全部样本必须逐字节 round-trip，模板指纹必须通过
python -B -m unittest discover -s scripts -p test_ctf_events.py  # 错误输入、Windows 路径及模拟桥回归
```

`selftest` 目前覆盖 `references/original-code/*.json` 的解析→重建一致性，
只跳过明确的 `MMF2BEHAVIOR` 包；损坏的事件包会导致失败。
它不代表所有源事件已通过语义校验或 Fusion 运行测试。
新增模板时把它加进 `PROVENANCE`，指纹加进 `FINGERPRINTS`。
