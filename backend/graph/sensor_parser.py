"""
PeMS D12 传感器元数据解析
从 d12_text_meta_2023_12_05.txt 解析传感器站点信息
"""

import os
import csv
from collections import defaultdict

META_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "osm", "d12_text_meta_2023_12_05.txt"
)

# Type 字段含义映射
TYPE_MAP = {
    "OR": "On-Ramp (入口匝道)",
    "FR": "Off-Ramp (出口匝道)",
    "ML": "Mainline (主线)",
    "HV": "HOV (高乘载车道)",
    "SR": "Single Ramp",
}


def parse_sensors(meta_path=META_PATH):
    """
    解析传感器元数据文件，返回传感器列表。

    每条记录包含:
      id, fwy, dir, latitude, longitude, length, type, lanes, name

    跳过无经纬度的行。
    按站点去重（相同 Fwy + Dir + Name 视为同一站点，取第一条）。
    """
    sensors = []
    seen_stations = set()

    with open(meta_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            lat_str = row.get("Latitude", "").strip()
            lon_str = row.get("Longitude", "").strip()

            if not lat_str or not lon_str:
                continue

            try:
                lat = float(lat_str)
                lon = float(lon_str)
            except ValueError:
                continue

            # 去重：同一 Fwy + Dir + Name 只保留一条
            station_key = (row["Fwy"], row["Dir"], row["Name"])
            if station_key in seen_stations:
                continue
            seen_stations.add(station_key)

            sensors.append(
                {
                    "id": int(row["ID"]),
                    "fwy": row["Fwy"].strip(),
                    "dir": row["Dir"].strip(),
                    "latitude": lat,
                    "longitude": lon,
                    "length": float(row["Length"]) if row["Length"].strip() else 0,
                    "type": row["Type"].strip(),
                    "type_desc": TYPE_MAP.get(row["Type"].strip(), row["Type"].strip()),
                    "lanes": int(row["Lanes"]) if row["Lanes"].strip() else 0,
                    "name": row["Name"].strip(),
                    "city": row.get("City", "").strip(),
                }
            )

    return sensors


def get_sensors_by_fwy(meta_path=META_PATH):
    """按高速公路分组返回传感器"""
    sensors = parse_sensors(meta_path)
    groups = defaultdict(list)
    for s in sensors:
        groups[s["fwy"]].append(s)
    return dict(groups)


if __name__ == "__main__":
    sensors = parse_sensors()
    print(f"共解析到 {len(sensors)} 个传感器站点")

    by_fwy = get_sensors_by_fwy()
    for fwy, items in sorted(by_fwy.items()):
        print(f"  I-{fwy}: {len(items)} 个站点")
