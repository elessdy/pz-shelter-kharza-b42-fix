"""Independent binary-header audit; does not use POT or its coordinate helpers.

Usage: python ValidateShelterMetadata.py original-b41 vanilla merged [--report report.json]
The selected legacy 300-tile source cell owns its footprint; vanilla owns the rest.
Use --source-cell X Y to override the established 22 38 default.
"""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import struct


def read_header(path):
    data = path.read_bytes()
    offset = 4 if data[:4] == b"LOTH" else 0
    modern_magic = offset == 4

    def integer():
        nonlocal offset
        value = struct.unpack_from("<i", data, offset)[0]
        offset += 4
        return value

    def count():
        value = integer()
        if not 0 <= value <= len(data):
            raise ValueError(f"Invalid count {value}: {path}:{offset}")
        return value

    def string():
        nonlocal offset
        end = data.index(b"\n", offset)
        value = data[offset:end].decode("latin1")
        offset = end + 1
        return value

    version = integer()
    if version not in (0, 1) or modern_magic != (version == 1):
        raise ValueError(f"Unexpected header magic/version: {path}")
    tile_names = [string() for _ in range(count())]
    if version == 0:
        offset += 1  # legacy byte between tile names and dimensions
    width, height = integer(), integer()
    min_z = integer() if version == 1 else 0
    max_z = integer()
    cell_x, cell_y = map(int, path.stem.split("_"))
    cell_size = 256 if version == 1 else 300
    cell_origin = (cell_x * cell_size, cell_y * cell_size)
    rooms = []
    for _ in range(count()):
        name, level = string(), integer()
        rectangles = []
        for _ in range(count()):
            x, y, w, h = integer(), integer(), integer(), integer()
            if w <= 0 or h <= 0:
                raise ValueError(f"Nonpositive room rectangle: {path}")
            rectangles.append((cell_origin[0] + x, cell_origin[1] + y, w, h))
        objects = []
        for _ in range(count()):
            kind, x, y = integer(), integer(), integer()
            # File coordinates are cell-relative, independent of room origin.
            objects.append((kind, cell_origin[0] + x, cell_origin[1] + y))
        rooms.append((name, level, tuple(sorted(rectangles)), tuple(sorted(objects))))
    buildings = []
    assigned = []
    for _ in range(count()):
        indices = [integer() for _ in range(count())]
        if any(i < 0 or i >= len(rooms) for i in indices):
            raise ValueError(f"Invalid building room index: {path}")
        assigned.extend(indices)
        buildings.append(tuple(sorted(rooms[i] for i in indices)))
    if sorted(assigned) != list(range(len(rooms))):
        raise ValueError(f"Orphan or multiply assigned rooms: {path}")
    density = data[offset:]
    if len(density) != (32 if version == 1 else 30) ** 2:
        raise ValueError(f"Density length or unparsed bytes: {path}")
    expected_width = 8 if version == 1 else 10
    if (width, height) != (expected_width, expected_width):
        raise ValueError(f"Wrong chunk dimensions: {path}")
    if not -32 <= min_z <= max_z <= 31:
        raise ValueError(f"Invalid level range: {path}")
    upper = max_z if version == 1 else max_z - 1
    if any(not min_z <= room[1] <= upper for room in rooms):
        raise ValueError(f"Room outside header level range: {path}")
    return dict(version=version, rooms=rooms, buildings=buildings,
                density=density, min_z=min_z, max_z=max_z,
                tile_names=tile_names, sha256=hashlib.sha256(data).hexdigest())


def bounds(building):
    rects = [r for room in building for r in room[2]]
    if not rects:
        raise ValueError("Building has no room rectangles")
    return (min(r[0] for r in rects), min(r[1] for r in rects),
            max(r[0] + r[2] for r in rects), max(r[1] + r[3] for r in rects))


def source_bounds(source_cell):
    if len(source_cell) != 2 or any(type(v) is not int or v < 0 for v in source_cell):
        raise ValueError("Source cell must contain two nonnegative integers")
    min_x, min_y = (v * 300 for v in source_cell)
    return min_x, min_y, min_x + 300, min_y + 300


def inside(x, y, footprint):
    min_x, min_y, max_x, max_y = footprint
    return min_x <= x < max_x and min_y <= y < max_y


def overlaps(b, footprint):
    x, y, x2, y2 = bounds(b)
    min_x, min_y, max_x, max_y = footprint
    return x < max_x and x2 > min_x and y < max_y and y2 > min_y


def contained(b, footprint):
    x, y, x2, y2 = bounds(b)
    min_x, min_y, max_x, max_y = footprint
    return x >= min_x and x2 <= max_x and y >= min_y and y2 <= max_y


def validate(original_dir, vanilla_dir, merged_dir, source_cell=(22, 38)):
    footprint = source_bounds(source_cell)
    min_x, min_y, max_x, max_y = footprint
    source_x, source_y = source_cell
    original = read_header(original_dir / f"{source_x}_{source_y}.lotheader")
    if original["version"] != 0:
        raise ValueError("Expected original B41 header")
    if any(not contained(b, footprint) for b in original["buildings"]):
        raise ValueError("Original building crosses the source footprint")
    report = dict(status="pass", comparison="Independent direct binary header decoding",
                  original_header_sha256=original["sha256"], cells=[],
                  density_chunks_checked=0, rooms_checked=0, metaobjects_checked=0)
    failures = []
    for cx in range(min_x // 256, (max_x - 1) // 256 + 1):
        for cy in range(min_y // 256, (max_y - 1) // 256 + 1):
            name = f"{cx}_{cy}.lotheader"
            vanilla = read_header(vanilla_dir / name)
            merged = read_header(merged_dir / name)
            if vanilla["version"] != 1 or merged["version"] != 1:
                raise ValueError("Expected B42 headers")
            expected = [b for b in original["buildings"]
                        if bounds(b)[0] // 256 == cx and bounds(b)[1] // 256 == cy]
            for building in vanilla["buildings"]:
                if overlaps(building, footprint):
                    if not contained(building, footprint):
                        raise ValueError(f"Vanilla building crosses source footprint: {bounds(building)}")
                else:
                    expected.append(building)
            if Counter(merged["buildings"]) != Counter(expected):
                failures.append(dict(cell=[cx, cy], type="building_room_or_metaobject_mismatch",
                    missing=list((Counter(expected)-Counter(merged["buildings"])).elements()),
                    unexpected=list((Counter(merged["buildings"])-Counter(expected)).elements())))
            # On disk density is x-major: header writer loops chunk x, then chunk y.
            for chx in range(32):
                for chy in range(32):
                    total = 0
                    for dx in range(8):
                        for dy in range(8):
                            x, y = cx*256+chx*8+dx, cy*256+chy*8+dy
                            if inside(x, y, footprint):
                                total += original["density"][((x-min_x)//10)*30+(y-min_y)//10]
                            else:
                                total += vanilla["density"][chx*32+chy]
                    value = merged["density"][chx*32+chy]
                    if value != total // 64:
                        failures.append(dict(cell=[cx, cy], type="density_mismatch",
                            square_origin=[cx*256+chx*8, cy*256+chy*8], expected=total//64, actual=value))
                    report["density_chunks_checked"] += 1
            room_count = len(merged["rooms"])
            object_count = sum(len(r[3]) for r in merged["rooms"])
            report["rooms_checked"] += room_count
            report["metaobjects_checked"] += object_count
            report["cells"].append(dict(cell=[cx, cy], rooms=room_count,
                buildings=len(merged["buildings"]), metaobjects=object_count,
                z_range=[merged["min_z"], merged["max_z"]],
                merged_header_sha256=merged["sha256"], vanilla_header_sha256=vanilla["sha256"]))
    report["failures"] = failures
    if failures:
        report["status"] = "fail"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("vanilla", type=Path)
    parser.add_argument("merged", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--source-cell", type=int, nargs=2, default=(22, 38), metavar=("X", "Y"))
    args = parser.parse_args()
    report = validate(args.original, args.vanilla, args.merged, args.source_cell)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
