# 剪贴板工作流（读 / 写 / 回读校验）

## 结论先行（2026-11-20 实测）

在本工作区里，**agent 的 shell 可以直接读写剪贴板**：`ClipboardBridge.ps1`
的 Import/Export 在普通（非交互）PowerShell 进程里就能成功，
不要再默认“agent 打不开剪贴板、必须让用户手动跑”。

正确姿势是“**导入 → 立刻回读 → 比对哈希**”一条龙，三步都在 agent 侧完成。
已封装成 `scripts/ImportAndVerify.ps1`，通常只需要：

```powershell
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "<skill>\scripts\ImportAndVerify.ps1" -Path "<work>\candidate.json"
```

通过会打印 `PASS: clipboard matches ...`。手动版本如下：

```powershell
# 1) 生成/确认候选 JSON 后导入
powershell.exe -NoProfile -STA -File "<work>\ClipboardBridge.ps1" `
  -Mode Import -Path "<work>\candidate.json" -FormatName CF_CNCV25_EVENTS

# 2) 立刻导出（脚本会生成带毫秒时间戳的新文件）
powershell.exe -NoProfile -STA -File "<work>\ClipboardBridge.ps1"

# 3) 比对：导出的 CF_CNCV25_EVENTS 的 Base64/SHA256 应与 candidate.json 完全一致
```

第 3 步通过，只说明“剪贴板里确实是这份字节”，**不代表 Fusion 接受它**；
Fusion 内的粘贴结果仍需用户确认（见 [event-verification](event-verification.md)）。

只有在 Import 抛 `OpenClipboard failed: 5`（或导出拿不到自定义格式）时，才退回
“让用户在自己的桌面 PowerShell 里运行同一条命令”。首次失败后不要原地重试十几次，
直接换会话/请用户执行。

## 读剪贴板

`ClipboardBridge.ps1` 无参数运行时导出所有受支持的内存格式，文件名按**本机时间到毫秒**
生成在脚本旁边（即使给了 `-Path` 也只影响 Import）。导出包含 Id/Name/Storage/Length/
SHA256/Base64；先校验长度与哈希，再转换。

- `CF_UNICODETEXT`（Id 13）给可读文本，但**不能**当可导入事件用。
- `CF_CNCV25_EVENTS` 才是事件二进制。
- `MMF2BEHAVIOR` 是整段行为包装，通常没有文本格式；`verify_events.py` 与
  `ctf_events.py` 都不解析它。

多个文件到达时按时间戳和内容排序、按哈希去重，不要拿旧导出当新结果。

## 写剪贴板

- Import 会先清空剪贴板，再只放回 `-FormatName` 指定的格式；需要保留别的格式就一次传多个名字。
- 数值格式 Id 每次会话可能不同，桥会现场 `RegisterClipboardFormat`，不要硬编码 Id。
- 导入前确保 JSON 的 `Length`/`SHA256`/`Base64` 三者自洽（`ctf_events.py` 的 `save()`
  会自动重算）。
- **告诉用户去粘贴之前再导入一次**：中间任何一次复制都会覆盖它。

## 粘贴到 Fusion 的提示（减少来回）

- 事件包里的对象按**名字**匹配。包里出现的新对象（例如控制器 Active）要在工程里先建好、
  名字完全一致；没有的话 Fusion 会弹“对象不存在”，在对话框里映射到已有对象。
- 粘贴插入在**当前选中的事件之后**。需要固定位置时，先选中目标位置的前一条事件（或组）。
- 粘贴后立刻看 Fusion 显示的条件/动作/对象名是否与预期一致；截图或重新复制导出都能作为回读。
- 事件包只带事件，不带对象定义、图片、行为；粘贴不会替你创建对象。

## 生成事件时

用 `scripts/ctf_events.py`（见 [opcode-cookbook](opcode-cookbook.md)）：

```powershell
python scripts/ctf_events.py describe candidate.json   # 反汇编成人话，核对对象/条件/动作
python scripts/ctf_events.py verify   candidate.json   # 结构 + 对象引用 + 立即条件层级
python scripts/verify_events.py       candidate.json   # 独立实现的结构校验
```

拿不准某个动作/条件时，从 `references/original-code/` 里找语义相同的记录整段复制，
用 `template()` + 指纹断言（例如跳跃必须含 `67 00 00 00`、不得含 `69 00 00 00`）。
不要手写表达式内部字节。

## 已知边界

- 桥只读 HGLOBAL 数据，位图/调色板/元文件等句柄格式标记为跳过；单载荷上限 128 MiB。
- 剪贴板包里的对象 id 是**包内局部编号**，粘贴时 Fusion 按对象名匹配；对象名必须与目标工程一致。
- 生成包只带 `OIC0`（无图标）即可粘贴；原样保留图标只影响编辑器显示。
