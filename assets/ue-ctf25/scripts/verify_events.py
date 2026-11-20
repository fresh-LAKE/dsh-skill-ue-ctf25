"""Validate UE CF_CNCV25_EVENTS exports and compare Fusion readbacks."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct


def require(test, message):
    if not test:
        raise ValueError(message)


def load(path):
    data = path.read_bytes()
    if data.startswith(b"KLBEDAEH"):
        return data
    doc = json.loads(data.decode("utf-8-sig"))
    formats = doc["Formats"]
    require(isinstance(formats, list), "Formats must be an array")
    for entry in formats:
        if entry.get("Storage") != "HGLOBAL":
            continue
        payload = base64.b64decode(entry["Base64"], validate=True)
        require(len(payload) == entry["Length"], "Clipboard payload length mismatch")
        require(hashlib.sha256(payload).hexdigest() == entry["SHA256"].lower(),
                "Clipboard payload SHA-256 mismatch")
    events = [entry for entry in formats if entry.get("Name") == "CF_CNCV25_EVENTS"
              and entry.get("Storage") == "HGLOBAL"]
    require(len(events) == 1, "Expected one HGLOBAL CF_CNCV25_EVENTS payload")
    return base64.b64decode(events[0]["Base64"], validate=True)


def parse(data, extra_immediates):
    require(len(data) >= 30 and data[:8] == b"KLBEDAEH" and data[16:20] == b"STVE",
            "Unsupported header (expected a CF_CNCV25_EVENTS package, not a behavior wrapper or bare stream)")
    end = 24 + struct.unpack_from("<I", data, 20)[0]
    require(26 <= end <= len(data)-4 and data.endswith(b"!DNE"), "Invalid stream length or package trailer")
    offset = 24
    events = []
    while offset + 2 <= end:
        size = -struct.unpack_from("<h", data, offset)[0]
        if not size:
            require(offset + 2 == end, "Unexpected bytes after event terminator")
            return events, data[end:]
        label = f"event {len(events) + 1} at 0x{offset:x}"
        limit = offset + size
        require(size >= 14 and limit <= end - 2, f"{label}: invalid event length")
        conditions, actions = data[offset+2:offset+4]
        require(conditions > 0, f"{label}: missing condition")
        flags, _, hierarchy = struct.unpack_from("<HHH", data, offset + 4)
        # The hierarchy field is nonzero in some source events inside groups.
        # The observed sub-event flag distinguishes those from child records.
        child = bool(flags & 0x8000)
        cursor = offset + 14
        records = []
        for index in range(conditions + actions):
            condition = index < conditions
            header_size = 16 if condition else 14
            require(cursor + header_size <= limit, f"{label}: truncated condition/action")
            length, obj_type, opcode, object_index = struct.unpack_from("<HhhH", data, cursor)
            record_end = cursor + length
            require(length >= header_size and record_end <= limit, f"{label}: invalid condition/action length")
            identity = (obj_type, opcode)
            immediate = identity in {(-1, -16), (2, -41)} | extra_immediates
            require(not (condition and child and immediate),
                    f"{label}: Immediate Condition {identity} is nested")
            position = cursor + header_size
            params = []
            for _ in range(data[cursor+12]):
                require(position + 4 <= record_end, f"{label}: truncated parameter header")
                param_size, param_type = struct.unpack_from("<HH", data, position)
                require(param_size >= 4 and position + param_size <= record_end,
                        f"{label}: invalid parameter length")
                params.append((param_type, data[position+4:position+param_size].hex()))
                position += param_size
            require(position == record_end, f"{label}: parameter counts do not fit record")
            records.append((obj_type, opcode, object_index, params))
            cursor = record_end
        require(cursor == limit, f"{label}: condition/action counts do not fit event")
        events.append((flags, hierarchy, records[:conditions], records[conditions:]))
        offset = limit
    raise ValueError("Missing event stream terminator")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, help="clipboard JSON or complete event package")
    parser.add_argument("--template", type=Path, help="require byte-identical metadata from this export")
    parser.add_argument("--readback", type=Path, help="require identical CF_CNCV25_EVENTS payload after re-copy")
    parser.add_argument("--immediate", action="append", default=[], metavar="TYPE,OPCODE",
                        help="additional confirmed Immediate Condition pair, repeat as needed")
    parser.add_argument("--dump", action="store_true", help="show event flags, record IDs and parameter bytes")
    args = parser.parse_args()
    try:
        extra = set()
        for value in args.immediate:
            pair = tuple(int(x, 0) for x in value.split(","))
            require(len(pair) == 2, "--immediate requires TYPE,OPCODE")
            extra.add(pair)
        data = load(args.candidate)
        events, metadata = parse(data, extra)
        if args.template:
            _, original_metadata = parse(load(args.template), extra)
            require(metadata == original_metadata, "Metadata differs from the template")
        if args.readback:
            readback = load(args.readback)
            parse(readback, extra)
            require(data == readback,
                    "Readback bytes differ. Check Fusion event semantics before classifying the change.")
        if args.dump:
            for index, (flags, hierarchy, conditions, actions) in enumerate(events, 1):
                print(f"#{index} flags=0x{flags:04x} hierarchy={hierarchy}")
                for label, records in (("condition", conditions), ("action", actions)):
                    for obj_type, opcode, obj, params in records:
                        print(f"  {label} type={obj_type} opcode={opcode} object={obj} params={params}")
        print(f"PASS: {len(events)} records, {len(data)} bytes, sha256={hashlib.sha256(data).hexdigest()}")
        if args.template:
            print("Template metadata: identical")
        if args.readback:
            print("Readback event payload: identical")
        print("Scope: binary structure and known Immediate Condition IDs. Review semantics in Fusion.")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, struct.error) as error:
        parser.exit(1, f"FAIL: {error}\n")


if __name__ == "__main__":
    main()
