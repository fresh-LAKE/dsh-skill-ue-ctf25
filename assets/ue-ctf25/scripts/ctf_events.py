"""CF_CNCV25_EVENTS 读写 / 反汇编 / 组装库（仅标准库）。

设计目标：不再从零逆向二进制。常见条件/动作都有已验证的“模板”，
模板带来源（文件+事件号+序号）和指纹断言，改完即可校验。

用法：
    python ctf_events.py describe  some.json
    python ctf_events.py verify    some.json
    python ctf_events.py templates

库：
    from ctf_events import Package, template, Obj
    pkg = Package.load(path); pkg.describe()
    rec = template("mario_jump_ground")          # 已做指纹校验
    # 修改现有包，或参考 example_infinite_jump.py 构造 Package / new_event。
    out = pkg.to_bytes()
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF = HERE.parent / "references" / "original-code"

# 所有样本里逐字节相同的 62 字节 TYAL 负载
TYAL = bytes.fromhex(
    "000000000a0000000000000000000000000000000000000000000a000000000000000000"
    "0000000000000000080000000000000000000000ffff00000000"
)
assert len(TYAL) == 62

GROUP_IDS = {
    0: "Instance", 1: "Gravity", 2: "Movable", 3: "Solid", 4: "Platform",
    5: "Water", 6: "MarioAni", 7: "Enemy", 8: "Shell", 9: "HardShell",
    10: "EnemyTurn", 11: "Lava", 12: "PowerUp", 13: "MovingBlock",
    16: "Block", 17: "AutoPlace",
}

COND_NAMES = {
    (-1, -1): "Always", (-1, -25): "NOT", (-1, -16): "On loop", (-1, -6): "Run this event once",
    (-1, -10): "Group header", (-1, -9): "Comment", (-1, -42): "Blank/unknown (-1,-42)",
    (2, -41): "ForEach", (2, -27): "Compare alterable value",
    (2, -25): "Flag is on", (2, -24): "Flag is off", (2, -4): "Is overlapping",
    (-7, -6): "Repeat while Player 1 pressed", (-7, -4): "Player 1 pressed (trigger)",
}
ACT_NAMES = {
    (2, 31): "Set alterable value", (2, 32): "Add to alterable value",
    (-2, 0): "Play sample", (-5, 0): "Create object", (2, 35): "Set flag on",
    (-1, 0): "No action",
}

# 模板来源：名称 -> (样本文件, 事件序号, "C"/"A", 该方向第几条)
PROVENANCE = {
    "flag_on": ("process-start.json", 2, "C", 0),
    "flag_off": ("lavaball-track-init.json", 0, "C", 0),
    "set_flag_on": ("lavaball-track-init.json", 0, "A", 12),
    "cmp_value_50": ("mario-movement.json", 161, "C", 2),
    "cmp_value_53": ("mario-movement.json", 161, "C", 0),
    "key_repeat": ("mario-movement.json", 161, "C", 3),
    "key_press": ("mario-animation.json", 23, "C", 0),
    "set_value_50": ("mario-movement.json", 160, "A", 0),
    "mario_jump_ground": ("mario-movement.json", 167, "A", 0),
    "mario_an_set": ("mario-movement.json", 166, "A", 1),
    "play_mario_jump": ("mario-movement.json", 167, "A", 1),
    "overlap_group": ("mario-movement.json", 169, "C", 0),
}

# 指纹：模板必须/禁止包含的字节串
FINGERPRINTS = {
    "mario_jump_ground": (b"\x67\x00\x00\x00", b"\x69\x00\x00\x00"),
}


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


class UnsupportedBehaviorWrapper(ValueError):
    """A whole-behavior clipboard capture without an event package."""


# ---------------------------------------------------------------- model
@dataclass
class Param:
    type: int
    body: bytes

    def to_bytes(self):
        return struct.pack("<HH", 4 + len(self.body), self.type) + self.body

    @property
    def u32s(self):
        return [struct.unpack_from("<I", self.body, i)[0]
                for i in range(0, len(self.body) - 3, 4)]


@dataclass
class Rec:
    is_cond: bool
    header: bytearray
    params: list

    @property
    def hsize(self):
        return 16 if self.is_cond else 14

    @property
    def type(self):
        return struct.unpack_from("<h", self.header, 2)[0]

    @property
    def op(self):
        return struct.unpack_from("<h", self.header, 4)[0]

    @property
    def obj(self):
        return struct.unpack_from("<H", self.header, 6)[0]

    @obj.setter
    def obj(self, value):
        struct.pack_into("<H", self.header, 6, value)

    @property
    def inverted(self):
        # 条件头偏移 10 的 u16：普通 0x0020，取反 0x0120（bit 0x0100）。
        return self.is_cond and bool(struct.unpack_from("<H", self.header, 10)[0] & 0x0100)

    def to_bytes(self):
        body = b"".join(p.to_bytes() for p in self.params)
        struct.pack_into("<H", self.header, 0, self.hsize + len(body))
        struct.pack_into("<B", self.header, 12, len(self.params))
        return bytes(self.header) + body

    def text(self, objects):
        names = COND_NAMES if self.is_cond else ACT_NAMES
        name = names.get((self.type, self.op), "?")
        target = objects.get(self.obj, f"#{self.obj}")
        ps = ", ".join(f"t{p.type}[{len(p.body)}B]{p.body.hex()[:60]}" for p in self.params)
        inv = "NOT " if self.inverted else ""
        return f"{inv}{name} <{target}> ({self.type},{self.op}) {ps}"


@dataclass
class Event:
    header: bytearray
    conds: list
    acts: list

    @property
    def flags(self):
        return struct.unpack_from("<H", self.header, 4)[0]

    @property
    def depth(self):
        return struct.unpack_from("<H", self.header, 8)[0]

    def to_bytes(self):
        body = b"".join(r.to_bytes() for r in self.conds + self.acts)
        struct.pack_into("<h", self.header, 0, -(14 + len(body)))
        self.header[2] = len(self.conds)
        self.header[3] = len(self.acts)
        return bytes(self.header) + body


@dataclass
class Obj:
    id: int
    type: int
    name: str
    cls: str = "Sprite"
    flags: int = 0
    group_id: int = None
    icon_tag: bytes = b"OIC0"
    icon_payload: bytes = b""
    subtype: int = 2          # 对象类编号：Sprite=2，Layer object=0x21，按样本原样保留

    def to_bytes(self):
        out = bytearray()
        out += struct.pack("<IHH", self.id, self.type, self.subtype)
        raw = self.name.encode("utf-16-le")
        out += struct.pack("<I", 0x80000000 | (len(raw) // 2)) + raw
        raw2 = self.cls.encode("utf-16-le")
        out += struct.pack("<I", 0x80000000 | (len(raw2) // 2)) + raw2
        out += struct.pack("<H", self.flags)
        if self.type == 3:
            out += struct.pack("<H", 0 if self.group_id is None else self.group_id)
        else:
            out += self.icon_tag
            if self.icon_tag in (b"OIC2", b"OIC3"):
                out += struct.pack("<I", len(self.icon_payload)) + self.icon_payload
        return bytes(out)


class Package:
    def __init__(self, version, field12, events, objects, tail,
                 prefix=None, gap=b""):
        self.version = version      # bytes 8..12
        self.field12 = field12
        self.events = events
        self.objects = objects
        self.tail = tail            # 从 TYAL 到 !DNE 的原始字节
        self.prefix = prefix if prefix is not None else b"SMER" + struct.pack("<I", 0)
        self.gap = gap              # SJBO 之后、TYAL 之前的附加块（如 SPRG）

    # ---- load
    @classmethod
    def from_bytes(cls, data):
        require(len(data) >= 30, "truncated event package")
        require(data[:8] == b"KLBEDAEH", "not a CF_CNCV25_EVENTS package")
        require(data[16:20] == b"STVE", "missing STVE")
        stream_len = struct.unpack_from("<I", data, 20)[0]
        end = 24 + stream_len
        require(26 <= end <= len(data) - 4 and data.endswith(b"!DNE"), "bad stream length or trailer")
        events = []
        off = 24
        while off + 2 <= end:
            size = -struct.unpack_from("<h", data, off)[0]
            if not size:
                require(off + 2 == end, "unexpected bytes after event terminator")
                break
            require(size >= 14 and off + size <= end - 2, "invalid event length")
            cond, act = data[off + 2], data[off + 3]
            require(cond > 0, "event has no condition")
            header = bytearray(data[off:off + 14])
            cur = off + 14
            conds, acts = [], []
            for i in range(cond + act):
                is_cond = i < cond
                hs = 16 if is_cond else 14
                require(cur + hs <= off + size, "truncated condition/action header")
                ln = struct.unpack_from("<H", data, cur)[0]
                require(ln >= hs and cur + ln <= off + size, "invalid condition/action length")
                h = bytearray(data[cur:cur + hs])
                cnt = data[cur + 12]
                params = []
                p = cur + hs
                for _ in range(cnt):
                    require(p + 4 <= cur + ln, "truncated parameter header")
                    ps, pt = struct.unpack_from("<HH", data, p)
                    require(ps >= 4 and p + ps <= cur + ln, "invalid parameter length")
                    params.append(Param(pt, data[p + 4:p + ps]))
                    p += ps
                require(p == cur + ln, "parameter counts do not fit record")
                (conds if is_cond else acts).append(Rec(is_cond, h, params))
                cur += ln
            require(cur == off + size, "condition/action counts do not fit event")
            events.append(Event(header, conds, acts))
            off += size
        else:
            raise ValueError("missing event stream terminator")
        objects, prefix, gap, tail = cls._parse_meta(data, end)
        return cls(data[8:12], struct.unpack_from("<I", data, 12)[0], events, objects, tail, prefix, gap)

    @classmethod
    def load(cls, path):
        return cls.from_bytes(read_payload(Path(path)))

    @staticmethod
    def _parse_meta(data, start):
        pos = data.find(b"SJBO", start)
        require(pos >= start and pos + 8 <= len(data) - 4, "SJBO not found or truncated")
        count = struct.unpack_from("<I", data, pos + 4)[0]
        p = pos + 8
        objs = []
        for _ in range(count):
            require(p + 8 <= len(data) - 4, "truncated object header")
            oid, typ, subtype = struct.unpack_from("<IHH", data, p)
            p += 8
            name, p = _ustr(data, p)
            cls, p = _ustr(data, p)
            require(p + 2 <= len(data) - 4, "truncated object flags")
            flags = struct.unpack_from("<H", data, p)[0]
            p += 2
            group_id = None
            icon_tag, icon_payload = b"OIC0", b""
            if typ == 3:
                require(p + 2 <= len(data) - 4, "truncated qualifier id")
                group_id = struct.unpack_from("<H", data, p)[0]
                p += 2
            else:
                icon_tag = data[p:p + 4]
                p += 4
                require(icon_tag in (b"OIC0", b"OIC2", b"OIC3"), f"unknown icon tag {icon_tag!r}")
                if icon_tag in (b"OIC2", b"OIC3"):
                    require(p + 4 <= len(data) - 4, "truncated icon length")
                    sz = struct.unpack_from("<I", data, p)[0]
                    require(p + 4 + sz <= len(data) - 4, "truncated icon payload")
                    icon_payload = data[p + 4:p + 4 + sz]
                    p += 4 + sz
            objs.append(Obj(oid, typ, name, cls, flags, group_id, icon_tag, icon_payload, subtype))
        t = data.find(b"TYAL", p)
        require(t >= p and t + 8 <= len(data) - 4,
                f"TYAL not found or truncated (objects end {p:#x})")
        tail_len = struct.unpack_from("<I", data, t + 4)[0]
        require(t + 8 + tail_len == len(data) - 4, "invalid TYAL length")
        # 对象表之后、TYAL 之前可能有 SPRG（注释文本）等附加块；原样保留。
        return objs, data[start:pos], data[p:t], data[t:]

    # ---- save
    def to_bytes(self):
        stream = b"".join(ev.to_bytes() for ev in self.events) + b"\x00\x00"
        out = bytearray(b"KLBEDAEH" + self.version + struct.pack("<I", self.field12))
        out += b"STVE" + struct.pack("<I", len(stream)) + stream
        out += self.prefix
        out += b"SJBO" + struct.pack("<I", len(self.objects))
        out += b"".join(o.to_bytes() for o in self.objects)
        out += self.gap
        out += self.tail
        return bytes(out)

    def save(self, path):
        payload = self.to_bytes()
        doc = {
            "Version": 1,
            "CapturedAt": "1970-01-01T00:00:00+00:00",
            "Formats": [{
                "Id": 50247, "Name": "CF_CNCV25_EVENTS", "Storage": "HGLOBAL",
                "Length": len(payload),
                "SHA256": hashlib.sha256(payload).hexdigest(),
                "Base64": base64.b64encode(payload).decode(),
            }],
        }
        Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    # ---- helpers
    @property
    def objects_by_name(self):
        return {o.name: o for o in self.objects}

    def describe(self):
        names = {o.id: o.name for o in self.objects}
        lines = [f"objects: " + ", ".join(f"{o.id}:{o.name}(type {o.type})" for o in self.objects)]
        for i, ev in enumerate(self.events):
            lines.append(f"#{i} depth={ev.depth} flags=0x{ev.flags:04x}")
            for r in ev.conds:
                lines.append("  " + r.text(names))
            for r in ev.acts:
                lines.append("  " + r.text(names))
        return "\n".join(lines)

    def verify(self):
        errors = []
        ids = {o.id for o in self.objects}
        if len(ids) != len(self.objects):
            errors.append("duplicate object ids in SJBO")
        for i, ev in enumerate(self.events):
            for r in ev.conds + ev.acts:
                if r.obj not in ids:
                    errors.append(f"event #{i}: object id {r.obj} not in SJBO")
                for p in r.params:
                    # Only the observed t1 object-pointer layout is decoded here.
                    if p.type == 1:
                        if len(p.body) != 8:
                            errors.append(f"event #{i}: unsupported t1 object-pointer length")
                        elif struct.unpack_from("<H", p.body, 2)[0] not in ids:
                            errors.append(f"event #{i}: t1 object id not in SJBO")
            # A nonzero hierarchy field can describe group membership; the child
            # flag distinguishes nested events, as in verify_events.py.
            if ev.flags & 0x8000:
                for r in ev.conds:
                    if (r.type, r.op) in ((-1, -16), (2, -41)):
                        errors.append(
                            f"event #{i}: immediate condition {r.type},{r.op} is nested")
        return errors


# ---------------------------------------------------------------- utils
def read_payload(path):
    data = Path(path).read_bytes()
    if data.startswith(b"KLBEDAEH"):
        return data
    doc = json.loads(data.decode("utf-8-sig"))
    formats = doc["Formats"]
    require(isinstance(formats, list), "Formats must be an array")
    events = []
    for e in formats:
        require(isinstance(e, dict), "invalid clipboard format entry")
        if e.get("Storage") != "HGLOBAL":
            continue
        payload = base64.b64decode(e["Base64"], validate=True)
        require(len(payload) == e["Length"], "clipboard payload length mismatch")
        require(hashlib.sha256(payload).hexdigest() == e["SHA256"].lower(),
                "clipboard payload SHA-256 mismatch")
        if e.get("Name") == "CF_CNCV25_EVENTS":
            events.append(payload)
    if not events and any(e.get("Name") == "MMF2BEHAVIOR" and e.get("Storage") == "HGLOBAL"
                          for e in formats):
        raise UnsupportedBehaviorWrapper("MMF2BEHAVIOR wrapper is not supported")
    require(len(events) == 1, "expected one HGLOBAL CF_CNCV25_EVENTS payload")
    return events[0]


def _ustr(data, p):
    require(p + 4 <= len(data) - 4, "truncated string length")
    ln = struct.unpack_from("<I", data, p)[0]
    require(ln & 0x80000000, "unsupported non-Unicode object string")
    p += 4
    n = (ln & 0x7FFFFFFF) * 2
    require(p + n <= len(data) - 4, "truncated object string")
    return data[p:p + n].decode("utf-16-le"), p + n


def iter_records(pkg):
    for ei, ev in enumerate(pkg.events):
        for ci, r in enumerate(ev.conds):
            yield ei, "C", ci, ev, r
        for ai, r in enumerate(ev.acts):
            yield ei, "A", ai, ev, r


def ancestor_chain(pkg, event_index):
    """返回从根到该事件父级的 [(事件序号, 事件)]。"""
    ev = pkg.events[event_index]
    depth, j, chain = ev.depth, event_index - 1, []
    while depth > 0 and j >= 0:
        parent = pkg.events[j]
        if parent.depth == depth - 1:
            chain.append((j, parent))
            depth = parent.depth
        j -= 1
    return list(reversed(chain))


def _rec_line(pkg, ei, kind, ri, rec):
    names = {o.id: o.name for o in pkg.objects}
    return (f"#{ei} {kind}{ri} ({rec.type},{rec.op}) obj={names.get(rec.obj, rec.obj)} "
            f"params=" + ";".join(p.body.hex() for p in rec.params))


def find_records(pkg, *, op=None, obj=None, is_cond=None, u32=None,
                 contains=None, event=None):
    """按结构特征列出候选记录（用于“同形多分支”时定位）。"""
    out = []
    for ei, kind, ri, ev, rec in iter_records(pkg):
        if event is not None and ei != event:
            continue
        if is_cond is not None and rec.is_cond != is_cond:
            continue
        if op is not None and (rec.type, rec.op) != op:
            continue
        if obj is not None and rec.obj != obj:
            continue
        if u32 is not None and not any(struct.pack("<I", u32) in p.body for p in rec.params):
            continue
        if contains is not None and not any(contains in p.body for p in rec.params):
            continue
        out.append((ei, kind, ri, ev, rec))
    return out


def describe_event(pkg, ei, context=2):
    names = {o.id: o.name for o in pkg.objects}
    ev = pkg.events[ei]
    lines = []
    for pei, pev in ancestor_chain(pkg, ei):
        conds = "; ".join(f"{r.text(names)}" for r in pev.conds)
        lines.append(f"parent #{pei} depth={pev.depth}: {conds}")
    lines.append(f"#{ei} depth={ev.depth} flags=0x{ev.flags:04x}")
    for r in ev.conds:
        lines.append("  " + r.text(names))
    for r in ev.acts:
        lines.append("  " + r.text(names))
    # 同一父级下、同深度的兄弟事件
    siblings = []
    for j in range(ei + 1, min(len(pkg.events), ei + 1 + context * 8)):
        sib = pkg.events[j]
        if sib.depth < ev.depth:
            break
        if sib.depth == ev.depth:
            siblings.append(j)
            if len(siblings) >= context:
                break
    for j in siblings:
        s = pkg.events[j]
        conds = "; ".join(r.text(names) for r in s.conds[:3])
        lines.append(f"sibling #{j}: {conds}")
    return "\n".join(lines)


def diff_events(pkg_a, ei_a, pkg_b, ei_b):
    a, b = pkg_a.events[ei_a], pkg_b.events[ei_b]
    lines = [f"A=#{ei_a} conds={len(a.conds)} acts={len(a.acts)} | B=#{ei_b} conds={len(b.conds)} acts={len(b.acts)}"]
    for label, ra, rb in (("cond", a.conds, b.conds), ("act", a.acts, b.acts)):
        for i in range(max(len(ra), len(rb))):
            if i >= len(ra):
                lines.append(f"{label}{i}: only B ({rb[i].type},{rb[i].op})")
                continue
            if i >= len(rb):
                lines.append(f"{label}{i}: only A ({ra[i].type},{ra[i].op})")
                continue
            x, y = ra[i].to_bytes(), rb[i].to_bytes()
            same = x == y
            head = f"{label}{i}: {'same' if same else 'DIFF'} ({ra[i].type},{ra[i].op})"
            if not same:
                diffs = [k for k in range(min(len(x), len(y))) if x[k] != y[k]]
                head += f" len {len(x)}/{len(y)} bytes {[hex(k) for k in diffs[:12]]}"
                if ra[i].params and rb[i].params:
                    head += f" | A={ra[i].params[-1].body.hex()[:40]} B={rb[i].params[-1].body.hex()[:40]}"
            lines.append(head)
    return "\n".join(lines)


def template(name):
    """返回 PROVENANCE 中记录的记录副本（已做指纹检查）。"""
    require(name in PROVENANCE, f"unknown template {name}")
    fname, ev_index, kind, index = PROVENANCE[name]
    pkg = Package.load(REF / fname)
    ev = pkg.events[ev_index]
    rec = (ev.conds if kind == "C" else ev.acts)[index]
    data = rec.to_bytes()
    if name in FINGERPRINTS:
        must, must_not = FINGERPRINTS[name]
        require(must in data, f"{name}: missing fingerprint {must.hex()}")
        require(must_not not in data, f"{name}: contains forbidden bytes {must_not.hex()}")
    return Rec(rec.is_cond, bytearray(rec.header), [Param(p.type, p.body) for p in rec.params])


def new_event(conds, acts, depth=0, flags=0, event_id=1, prev=0):
    h = bytearray(14)
    struct.pack_into("<H", h, 4, flags)
    struct.pack_into("<H", h, 8, depth)
    struct.pack_into("<H", h, 10, event_id)
    struct.pack_into("<H", h, 12, prev)
    return Event(h, conds, acts)


def numeric_rec(base_name, param_index, value, kind="u32"):
    """复制模板并把第 param_index 个参数里第一个 u32 改成 value。"""
    rec = template(base_name)
    p = rec.params[param_index]
    body = bytearray(p.body)
    struct.pack_into("<I", body, 0, value)
    rec.params[param_index] = Param(p.type, bytes(body))
    return rec


def set_param_u32(rec, param_index, offset, value):
    p = rec.params[param_index]
    body = bytearray(p.body)
    struct.pack_into("<I", body, offset, value)
    rec.params[param_index] = Param(p.type, bytes(body))
    return rec


def set_param_u16(rec, param_index, offset, value):
    p = rec.params[param_index]
    body = bytearray(p.body)
    struct.pack_into("<H", body, offset, value)
    rec.params[param_index] = Param(p.type, bytes(body))
    return rec


# ---------------------------------------------------------------- CLI
def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "describe":
        pkg = Package.load(argv[2])
        print(pkg.describe())
        errs = pkg.verify()
        print("verify:", "OK" if not errs else "; ".join(errs))
    elif cmd == "verify":
        pkg = Package.load(argv[2])
        errs = pkg.verify()
        print("PASS" if not errs else "\n".join(errs))
        return 0 if not errs else 1
    elif cmd == "selftest":
        bad = 0
        for path in sorted(REF.glob("*.json")):
            try:
                pkg = Package.load(path)
                same = pkg.to_bytes() == read_payload(path)
            except UnsupportedBehaviorWrapper as exc:
                print(f"skip {path.name}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {path.name}: {exc}")
                bad += 1
                continue
            print(f"{'ok  ' if same else 'DIFF'} {path.name}")
            bad += 0 if same else 1
        for name in sorted(PROVENANCE):
            try:
                rec = template(name)
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL template {name}: {exc}")
                bad += 1
        print("PASS" if not bad else f"{bad} failure(s)")
        return 0 if not bad else 1
    elif cmd == "templates":
        for name, (f, ev, k, i) in sorted(PROVENANCE.items()):
            rec = template(name)
            print(f"{name:20s} <- {f} #{ev} {k}{i}  ({rec.type},{rec.op}) {rec.to_bytes().hex()[:48]}")
    elif cmd == "find":
        args = argv[2:]
        opts = {"op": None, "obj": None, "u32": None, "contains": None,
                "event": None, "side": None}
        files = []
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("--op", "--obj", "--u32", "--contains", "--event"):
                opts[a[2:]] = args[i + 1]
                i += 2
            elif a in ("--cond", "--act"):
                opts["side"] = "C" if a == "--cond" else "A"
                i += 1
            else:
                files.append(a)
                i += 1
        pkg = Package.load(files[0])
        op = tuple(int(x, 0) for x in opts["op"].split(",")) if opts["op"] else None
        hits = find_records(
            pkg, op=op,
            obj=int(opts["obj"], 0) if opts["obj"] else None,
            is_cond=None if opts["side"] is None else opts["side"] == "C",
            u32=int(opts["u32"], 0) if opts["u32"] else None,
            contains=bytes.fromhex(opts["contains"]) if opts["contains"] else None,
            event=int(opts["event"], 0) if opts["event"] else None,
        )
        for ei, kind, ri, ev, rec in hits:
            chain = " -> ".join(f"#{p}({','.join(f'{c.type},{c.op}' for c in pev.conds)})"
                                for p, pev in ancestor_chain(pkg, ei))
            inv = " [invert]" if rec.inverted else ""
            print(f"{_rec_line(pkg, ei, kind, ri, rec)}{inv} depth={ev.depth} parents={chain or '-'}")
        print(f"{len(hits)} candidate(s)")
    elif cmd == "variants":
        # 把一个 opcode 的所有记录按参数分组，快速看出“同形家族”有几种变体、各被谁使用。
        pkg = Package.load(argv[2])
        op = tuple(int(x, 0) for x in argv[argv.index("--op") + 1].split(","))
        groups = {}
        for ei, kind, ri, ev, rec in find_records(pkg, op=op):
            key = tuple(p.body for p in rec.params)
            groups.setdefault(key, []).append((ei, kind))
        for key, uses in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            where = ", ".join(f"#{e}{k}" for e, k in uses[:10])
            print(f"{len(uses):3d}x [{where}]{' ...' if len(uses) > 10 else ''}")
            print(f"      {b''.join(key).hex()}")
        print(f"{len(groups)} variant(s), {sum(len(v) for v in groups.values())} record(s)")
    elif cmd == "show":
        pkg = Package.load(argv[2])
        ei = int(argv[argv.index("--event") + 1], 0)
        print(describe_event(pkg, ei))
    elif cmd == "diff":
        left, right = argv[2], argv[3]
        fa, ea = left.rsplit(":", 1)
        fb, eb = right.rsplit(":", 1)
        print(diff_events(Package.load(fa), int(ea, 0), Package.load(fb), int(eb, 0)))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
