"""
TGCN 全节点数据准备脚本（不执行训练）

用法:
    # 预览模式（不实际执行）
    python TGCN/prepare_all_sensors_data.py --dry-run

    # 实际执行数据准备
    python TGCN/prepare_all_sensors_data.py

    # 指定传感器数量
    python TGCN/prepare_all_sensors_data.py --top_n 500
"""
import os
import sys
import subprocess
import argparse


def main():
    parser = argparse.ArgumentParser(description="TGCN 全节点数据准备")
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划，不执行")
    parser.add_argument("--top_n", type=int, default=0, help="传感器数量 (0=全部)")
    parser.add_argument("--days", type=int, default=59, help="训练数据天数")
    parser.add_argument("--val_days", type=int, default=11, help="验证数据天数")
    parser.add_argument("--threshold", type=float, default=3.0, help="邻接矩阵距离阈值(km)")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    prepare_script = os.path.join(script_dir, "tgcn_pytorch", "data", "prepare_data.py")
    output_dir = os.path.join(script_dir, "tgcn_pytorch", "data", "all_sensors")

    all_stations_path = os.path.join(script_dir, "data", "d12_data", "all_stations.txt")
    if not os.path.exists(all_stations_path):
        print(f"[ERROR] 未找到全传感器列表: {all_stations_path}")
        print("请先运行: python -c \"from backend.graph.sensor_parser import parse_sensors; ...\"")
        return

    with open(all_stations_path) as f:
        station_count = sum(1 for line in f if line.strip())

    top_n = args.top_n if args.top_n > 0 else station_count

    print("=" * 60)
    print("TGCN 全节点数据准备")
    print("=" * 60)
    print(f"  传感器数量: {top_n} (共 {station_count} 个)")
    print(f"  训练数据: {args.days} 天")
    print(f"  验证数据: {args.val_days} 天")
    print(f"  距离阈值: {args.threshold} km")
    print(f"  输出目录: {output_dir}")
    print(f"  站点列表: {all_stations_path}")
    print()

    if args.dry_run:
        print("[DRY-RUN] 仅预览，不执行数据准备")
        print("\n将执行的命令:")
        cmd = [
            sys.executable, prepare_script,
            "--all_sensors",
            "--top_n", str(top_n),
            "--days", str(args.days),
            "--val_days", str(args.val_days),
            "--threshold", str(args.threshold),
            "--output_dir", output_dir,
        ]
        print(" ".join(cmd))
        print(f"\n预计生成文件:")
        print(f"  {output_dir}/d12_adj.csv       - {top_n}x{top_n} 邻接矩阵")
        print(f"  {output_dir}/d12_speed.csv     - 速度数据矩阵")
        print(f"  {output_dir}/sensor_ids.csv    - 传感器 ID 列表")
        print(f"  {output_dir}/data_config.json  - 数据配置")
        print(f"\n之后可用以下命令训练:")
        print(f"  cd TGCN/tgcn_pytorch && python train.py --config configs/all_sensors.yaml \\")
        print(f"    --speed_path data/all_sensors/d12_speed.csv \\")
        print(f"    --adj_path data/all_sensors/d12_adj.csv")
        return

    cmd = [
        sys.executable, prepare_script,
        "--all_sensors",
        "--top_n", str(top_n),
        "--days", str(args.days),
        "--val_days", str(args.val_days),
        "--threshold", str(args.threshold),
        "--output_dir", output_dir,
    ]

    print(f"执行数据准备...")
    print(f"{' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=os.path.join(script_dir, "tgcn_pytorch"))
    if result.returncode == 0:
        print(f"\n{'=' * 60}")
        print(f"数据准备完成！")
        print(f"输出目录: {output_dir}")
        print(f"\n下一步: 训练全节点模型")
        print(f"  cd TGCN/tgcn_pytorch")
        print(f"  python train.py --config configs/all_sensors.yaml \\")
        print(f"    --speed_path data/all_sensors/d12_speed.csv \\")
        print(f"    --adj_path data/all_sensors/d12_adj.csv")
    else:
        print(f"\n[ERROR] 数据准备失败，退出码: {result.returncode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
