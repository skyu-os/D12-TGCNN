"""
从 OSM XZ 文件中提取 PeMS D12 区域的机动车道路数据
优化版：只保留被机动车道引用的节点，输出更小更可靠的 OSM 文件
"""

import lzma
import re
import os
import sys

# PeMS D12 (Orange County) bbox
BBOX = {
    "north": 33.95,
    "south": 33.38,
    "east": -117.41,
    "west": -118.10,
}

# 机动车道类型
DRIVE_HIGHWAY_TYPES = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
    "service",
    "living_street",
}

XZ_PATH = os.path.join(
    os.path.dirname(__file__), "data", "osm", "planet_-118.579_33.669_3838a635.osm.xz"
)
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "data", "osm", "d12_drive.osm")


def is_in_bbox(lat, lon):
    return BBOX["south"] <= lat <= BBOX["north"] and BBOX["west"] <= lon <= BBOX["east"]


def parse_tag(line):
    """从 <tag k="..." v="..."/> 提取 key-value"""
    k_m = re.search(r'k="([^"]*)"', line)
    v_m = re.search(r'v="([^"]*)"', line)
    if k_m and v_m:
        return k_m.group(1), v_m.group(1)
    return None, None


def extract_d12_osm():
    print("=" * 60)
    print("  从 OSM XZ 提取 D12 区域机动车道路 (优化版)")
    print("=" * 60)

    # ===== Pass 1: 收集 bbox 内的节点坐标 =====
    print("\n[Pass 1/3] 收集 D12 bbox 内节点坐标...")
    node_coords = {}  # node_id -> (lat, lon)
    count = 0

    with lzma.open(XZ_PATH, "rt", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("<node") and not stripped.startswith("<nd"):
                id_m = re.search(r'id="(\d+)"', stripped)
                lat_m = re.search(r'lat="([-\d.]+)"', stripped)
                lon_m = re.search(r'lon="([-\d.]+)"', stripped)
                if id_m and lat_m and lon_m:
                    nid = int(id_m.group(1))
                    lat = float(lat_m.group(1))
                    lon = float(lon_m.group(1))
                    if is_in_bbox(lat, lon):
                        node_coords[nid] = (lat, lon)
                        count += 1
                        if count % 1000000 == 0:
                            print(f"  {count} 节点...")

    print(f"  D12 bbox 内节点: {len(node_coords)}")

    # ===== Pass 2: 收集机动车道的 way 数据和所需节点 ID =====
    print("\n[Pass 2/3] 收集机动车道 way 数据...")
    ways = []  # list of {node_refs: [], tags: {}}
    needed_node_ids = set()
    way_count = 0
    drive_way_count = 0

    with lzma.open(XZ_PATH, "rt", encoding="utf-8") as f:
        in_way = False
        way_tags = {}
        way_node_refs = []
        way_id = 0

        for line in f:
            stripped = line.strip()

            if stripped.startswith("<way"):
                in_way = True
                way_tags = {}
                way_node_refs = []
                # 提取 way id
                way_id_m = re.search(r'id="(\d+)"', stripped)
                way_id = int(way_id_m.group(1)) if way_id_m else way_count + 1
                continue

            if in_way:
                if stripped.startswith("<nd"):
                    ref_m = re.search(r'ref="(\d+)"', stripped)
                    if ref_m:
                        way_node_refs.append(int(ref_m.group(1)))
                elif stripped.startswith("<tag"):
                    k, v = parse_tag(stripped)
                    if k and v:
                        way_tags[k] = v
                elif stripped.startswith("</way>"):
                    in_way = False
                    way_count += 1

                    highway = way_tags.get("highway", "")
                    if highway in DRIVE_HIGHWAY_TYPES:
                        # 只保留所有节点都在 bbox 内的道路（避免缺失节点）
                        if all(ref in node_coords for ref in way_node_refs):
                            ways.append(
                                {
                                    "id": way_id,
                                    "node_refs": way_node_refs,
                                    "tags": way_tags,
                                }
                            )
                            for ref in way_node_refs:
                                needed_node_ids.add(ref)
                            drive_way_count += 1

                    if way_count % 500000 == 0:
                        print(
                            f"  扫描 {way_count} ways, 提取 {drive_way_count} 条机动车道..."
                        )

    print(f"  道路总数: {way_count}")
    print(f"  D12 机动车道: {drive_way_count}")
    print(f"  需要的节点数: {len(needed_node_ids)}")

    # ===== 写入过滤后的 OSM 文件 =====
    print(f"\n[Pass 3/3] 写入过滤后 OSM 文件: {OUTPUT_PATH}")
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
        # 写入头部
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        out.write('<osm version="0.6" generator="d12_extractor_v2">\n')
        out.write(
            f'  <bounds minlat="{BBOX["south"]}" minlon="{BBOX["west"]}" '
            f'maxlat="{BBOX["north"]}" maxlon="{BBOX["east"]}"/>\n'
        )

        # 写入节点
        written_nodes = 0
        for nid in sorted(needed_node_ids):
            if nid in node_coords:
                lat, lon = node_coords[nid]
                out.write(f'  <node id="{nid}" lat="{lat}" lon="{lon}" version="1"/>\n')
                written_nodes += 1
                if written_nodes % 500000 == 0:
                    print(f"  写入 {written_nodes} 节点...")

        print(f"  写入节点总数: {written_nodes}")

        # 写入道路
        for i, way in enumerate(ways):
            out.write(f'  <way id="{way["id"]}">\n')
            for ref in way["node_refs"]:
                out.write(f'    <nd ref="{ref}"/>\n')
            for k, v in way["tags"].items():
                # 转义 XML 特殊字符
                v = (
                    v.replace("&", "&amp;")
                    .replace('"', "&quot;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                out.write(f'    <tag k="{k}" v="{v}"/>\n')
            out.write("  </way>\n")

            if (i + 1) % 50000 == 0:
                print(f"  写入 {i + 1} 道路...")

        out.write("</osm>\n")

    file_size = os.path.getsize(OUTPUT_PATH) / 1024 / 1024
    print(f"\n  文件大小: {file_size:.1f} MB")
    print("\n[SUCCESS] 提取完成!")


if __name__ == "__main__":
    extract_d12_osm()
