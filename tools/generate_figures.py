#!/usr/bin/env python3
"""
论文图表生成脚本 — 基于项目已有数据文件生成发布级图表。
输出到 docs/generated_figures/ 目录。
"""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import Patch
from pathlib import Path
import os

# ---------- config ----------
OUT = Path("docs/generated_figures")
OUT.mkdir(parents=True, exist_ok=True)

RESULT_DIR = Path("TGCN/result")
DATA_DIR = Path("TGCN/data")

# 中文字体设置 (Windows)
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.dpi"] = 300
plt.rcParams["savefig.bbox"] = "tight"
plt.rcParams["font.size"] = 10

# ---------- load data ----------
with open(RESULT_DIR / "TGCN_history.json") as f:
    history = json.load(f)

with open(RESULT_DIR / "TGCN_results.json") as f:
    results = json.load(f)

with open(RESULT_DIR / "online_prediction_step1.json") as f:
    online = json.load(f)

epochs = list(range(1, 101))
train_loss = history["train_loss"]
val_loss = history["val_loss"]
rmse_hist = history.get("RMSE", [])
mae_hist = history.get("MAE", [])
mape_hist = history.get("MAPE", [])
r2_hist = history.get("R2", [])

# Extract online prediction data
preds = online["sensor_predictions"]
speeds = np.array([p["pred_speed_kmh"] for p in preds])
lats = np.array([p["latitude"] for p in preds])
lons = np.array([p["longitude"] for p in preds])
is_interp = np.array([p["is_interpolated"] for p in preds])
fwy_list = [p.get("fwy", "?") for p in preds]

core_mask = ~is_interp
interp_mask = is_interp

# Paper-reported values (for algorithm comparison charts)
paper_data = {
    "dijkstra": {"distance": 18.22, "time_min": 11.3, "compute_ms": 2504.2},
    "astar":    {"distance": 19.07, "time_min": 16.4, "compute_ms": 2341.7},
    "alt":      {"distance": 21.73, "time_min": 14.2, "compute_ms": 1803.0},
    "predictive": {"distance": 19.07, "time_min": 19.0},
    "timedep":  {"distance": 18.43, "time_min": 37.8, "avg_speed": 29.29,
                 "intersection_delay_s": 1080.2, "compute_ms": 910.6},
}


# ============================================================
# Fig 1: Training & Validation Loss Curve
# ============================================================
def fig_training_loss():
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(epochs, train_loss, "steelblue", linewidth=1.2, label="训练损失")
    ax.plot(epochs, val_loss, "darkorange", linewidth=1.2, label="验证损失")
    ax.axvline(x=np.argmin(val_loss) + 1, color="gray", linestyle="--", linewidth=0.7,
               label=f"最佳轮次={np.argmin(val_loss)+1}")
    ax.set_xlabel("训练轮次")
    ax.set_ylabel("均方误差损失")
    ax.set_title("T-GCN训练与验证损失曲线")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    # Inset: zoom last 30 epochs
    axin = ax.inset_axes([0.55, 0.45, 0.42, 0.42])
    axin.plot(epochs[-30:], train_loss[-30:], "steelblue", linewidth=1.0)
    axin.plot(epochs[-30:], val_loss[-30:], "darkorange", linewidth=1.0)
    axin.set_xlabel("训练轮次（局部）", fontsize=7)
    axin.set_title("最后30轮", fontsize=7)
    axin.tick_params(labelsize=6)
    axin.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "fig_loss_curves.png")
    plt.close(fig)
    print("  [OK] fig_loss_curves.png")


# ============================================================
# Fig 2: RMSE, MAE, MAPE Convergence
# ============================================================
def fig_metrics_convergence():
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
    colors = ["#2c7bb6", "#d7191c", "#fdae61"]
    labels = ["均方根误差（km/h）", "平均绝对误差（km/h）", "平均绝对百分比误差（%）"]
    data = [rmse_hist, mae_hist, mape_hist]
    best_rmse_ep = np.argmin(rmse_hist) + 1
    for ax, d, c, lab in zip(axes, data, colors, labels):
        ax.plot(epochs, d, color=c, linewidth=1.0)
        ax.axvline(x=best_rmse_ep, color="gray", linestyle="--", linewidth=0.6)
        ax.set_xlabel("训练轮次")
        ax.set_ylabel(lab)
        ax.set_title(lab)
        ax.grid(True, alpha=0.3)
        # annotate final value
        ax.annotate(f"{d[-1]:.2f}", xy=(100, d[-1]), fontsize=8, color=c,
                    xytext=(85, d[-1] + (max(d) - min(d)) * 0.12),
                    arrowprops=dict(arrowstyle="->", color="gray", lw=0.6))
    fig.suptitle("T-GCN验证集指标收敛趋势", fontweight="bold", y=1.01)
    fig.tight_layout()
    fig.savefig(OUT / "fig_metrics_convergence.png")
    plt.close(fig)
    print("  [OK] fig_metrics_convergence.png")


# ============================================================
# Fig 3: Online Prediction Speed Distribution Histogram
# ============================================================
def fig_speed_distribution():
    fig, ax = plt.subplots(figsize=(7, 4.2))
    counts, bins, patches = ax.hist(speeds, bins=50, color="steelblue", edgecolor="white",
                                     alpha=0.85, linewidth=0.3)
    # Color bars below 50 km/h red
    for count, patch, left, right in zip(counts, patches, bins[:-1], bins[1:]):
        if right <= 50:
            patch.set_facecolor("#d7191c")
        elif left < 50:
            patch.set_facecolor("#fdae61")
    ax.axvline(x=50, color="#d7191c", linestyle="--", linewidth=1.2, label="低速阈值（50 km/h）")
    ax.axvline(x=np.mean(speeds), color="darkgreen", linestyle="-", linewidth=1.0,
               label=f"平均速度 = {np.mean(speeds):.1f} km/h")
    ax.set_xlabel("预测速度（km/h）")
    ax.set_ylabel("检测器数量")
    ax.set_title("在线预测速度分布（第1步，2587个检测器）")
    ax.legend(fontsize=8)

    # Text box with stats
    stats_text = (
        f"平均值：{np.mean(speeds):.2f} km/h\n"
        f"最小值：{np.min(speeds):.2f} km/h\n"
        f"最大值：{np.max(speeds):.2f} km/h\n"
        f"低于50 km/h：{np.sum(speeds < 50)}个检测器\n"
        f"P10: {np.percentile(speeds, 10):.1f}  P90: {np.percentile(speeds, 90):.1f}"
    )
    ax.text(0.97, 0.95, stats_text, transform=ax.transAxes, fontsize=7.5,
            verticalalignment="top", horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))
    fig.tight_layout()
    fig.savefig(OUT / "fig_speed_distribution.png")
    plt.close(fig)
    print("  [OK] fig_speed_distribution.png")


# ============================================================
# Fig 4: Sensor Spatial Distribution Map
# ============================================================
def fig_sensor_spatial():
    fig, ax = plt.subplots(figsize=(8, 6.5))
    # Core sensors
    ax.scatter(lons[core_mask], lats[core_mask], c="#2c7bb6", s=8, alpha=0.8,
               label=f"核心节点（n={core_mask.sum()}）", edgecolors="none")
    # Interpolated detectors
    ax.scatter(lons[interp_mask], lats[interp_mask], c="#fdae61", s=3, alpha=0.5,
               label=f"插值节点（n={interp_mask.sum()}）", edgecolors="none")
    # Highlight low-speed detectors
    low_mask = speeds < 50
    ax.scatter(lons[low_mask], lats[low_mask], c="#d7191c", s=10, alpha=0.9,
               marker="x", linewidths=0.6,
               label=f"低于50 km/h（n={low_mask.sum()}）")
    ax.set_xlabel("经度")
    ax.set_ylabel("纬度")
    ax.set_title("传感器空间分布与低速检测器（PeMS D12）")
    ax.legend(fontsize=7, loc="lower left", markerscale=1.2)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "fig_sensor_spatial_map.png")
    plt.close(fig)
    print("  [OK] fig_sensor_spatial_map.png")


# ============================================================
# Fig 5: Speed by Freeway Boxplot
# ============================================================
def fig_speed_by_freeway():
    from collections import Counter
    fwy_counts = Counter(fwy_list)
    # Pick top 10 freeways by detector count
    top_fwys = [f for f, _ in fwy_counts.most_common(10)]
    data_by_fwy = {}
    for fwy in top_fwys:
        mask = np.array([f == fwy for f in fwy_list])
        data_by_fwy[fwy] = speeds[mask]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    positions = list(range(1, len(top_fwys) + 1))
    bp = ax.boxplot([data_by_fwy[f] for f in top_fwys], positions=positions,
                     widths=0.55, patch_artist=True,
                     medianprops={"color": "black", "linewidth": 0.8},
                     flierprops={"marker": ".", "markersize": 2, "alpha": 0.4})
    for patch, pos in zip(bp["boxes"], positions):
        patch.set_facecolor(plt.cm.Set2(pos / len(positions)))
    ax.set_xticks(positions)
    ax.set_xticklabels([f"FWY-{f}" for f in top_fwys], rotation=30, fontsize=8)
    ax.set_ylabel("预测速度（km/h）")
    ax.set_title("按高速公路划分的速度分布（检测器数量前10）")
    ax.axhline(y=50, color="#d7191c", linestyle="--", linewidth=0.8, alpha=0.6)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "fig_speed_by_freeway.png")
    plt.close(fig)
    print("  [OK] fig_speed_by_freeway.png")


# ============================================================
# Fig 6: Algorithm Performance Comparison (Bar Chart)
# ============================================================
def fig_algorithm_comparison():
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.8))

    # (a) Distance
    algos = ["Dijkstra", "A*", "ALT", "预测驱动", "时变A*"]
    distances = [18.22, 19.07, 21.73, 19.07, 18.43]
    times = [11.3, 16.4, 14.2, 19.0, 37.8]
    compute = [2504.2, 2341.7, 1803.0, None, 910.6]

    colors_bar = ["#2c7bb6", "#abd9e9", "#74add1", "#fdae61", "#d7191c"]

    # Distance
    ax = axes[0]
    bars = ax.bar(algos, distances, color=colors_bar, edgecolor="white", linewidth=0.3)
    ax.set_ylabel("路径长度（km）")
    ax.set_title("路径距离对比")
    ax.tick_params(axis="x", rotation=25)
    for bar, val in zip(bars, distances):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2,
                f"{val:.1f}", ha="center", fontsize=8)

    # Time
    ax = axes[1]
    bars = ax.bar(algos, times, color=colors_bar, edgecolor="white", linewidth=0.3)
    ax.set_ylabel("预计时间（min）")
    ax.set_title("路径时间对比")
    ax.tick_params(axis="x", rotation=25)
    for bar, val in zip(bars, times):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                f"{val:.1f}", ha="center", fontsize=8)

    # Compute time
    ax = axes[2]
    compute_display = [2504.2, 2341.7, 1803.0, 0, 910.6]  # placeholder for pred-drive
    bars = ax.bar(algos, compute_display, color=colors_bar, edgecolor="white", linewidth=0.3)
    ax.set_ylabel("计算耗时（ms）")
    ax.set_title("搜索计算耗时")
    ax.tick_params(axis="x", rotation=25)
    for bar, val in zip(bars, compute_display):
        label = f"{val:.0f}" if val > 0 else "N/A"
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 30,
                label, ha="center", fontsize=8)

    fig.suptitle("路径规划算法性能对比（相同OD对）", fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig_algorithm_comparison.png")
    plt.close(fig)
    print("  [OK] fig_algorithm_comparison.png")


# ============================================================
# Fig 7: Static vs Predictive vs Time-dependent comparison
# ============================================================
def fig_time_comparison():
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    categories = ["静态规划\n（A*基线）", "预测驱动\n（重规划）", "时变A*"]
    path_km = [19.07, 19.07, 18.43]
    time_min = [16.4, 19.0, 37.8]

    x = np.arange(len(categories))
    width = 0.3
    bars1 = ax.bar(x - width / 2, path_km, width, color="#2c7bb6", edgecolor="white",
                   label="路径长度（km）")
    ax2 = ax.twinx()
    bars2 = ax2.bar(x + width / 2, time_min, width, color="#d7191c", edgecolor="white",
                    label="预计时间（min）")

    # Labels on bars
    for bar, val in zip(bars1, path_km):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                f"{val:.1f}", ha="center", fontsize=9, fontweight="bold")
    for bar, val in zip(bars2, time_min):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 f"{val:.1f}", ha="center", fontsize=9, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.set_ylabel("路径长度（km）", color="#2c7bb6")
    ax2.set_ylabel("预计时间（min）", color="#d7191c")
    ax.set_title("路径规划方法演进：静态、预测、时变")
    # Combined legend
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_static_vs_dynamic.png")
    plt.close(fig)
    print("  [OK] fig_static_vs_dynamic.png")


# ============================================================
# Fig 8: Time-dep A* Path Time Decomposition
# ============================================================
def fig_time_decomposition():
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    labels = ["行驶时间", "路口延迟"]
    values = [37.8 * 60 - 1080.2, 1080.2]  # seconds
    colors_wedge = ["#2c7bb6", "#d7191c"]
    explode = (0, 0.07)
    wedges, texts, autotexts = ax.pie(values, explode=explode, labels=labels,
                                       colors=colors_wedge, autopct="%1.1f%%",
                                       startangle=90, textprops={"fontsize": 9})
    for at in autotexts:
        at.set_fontweight("bold")
    ax.set_title("时变A*路径时间构成\n（总计：37.8分钟）")
    # Add annotation
    ax.annotate(f"行驶：{values[0]:.0f}s（{values[0]/60:.1f} min）\n"
                f"延迟：{values[1]:.0f}s（{values[1]/60:.1f} min）",
                xy=(0, -1.2), fontsize=8, ha="center",
                bbox=dict(boxstyle="round", facecolor="whitesmoke", alpha=0.8))
    fig.tight_layout()
    fig.savefig(OUT / "fig_time_decomposition.png")
    plt.close(fig)
    print("  [OK] fig_time_decomposition.png")


# ============================================================
# Fig 9: R² Trend Analysis
# ============================================================
def fig_r2_analysis():
    fig, ax = plt.subplots(figsize=(7, 4.0))
    ax.plot(epochs, r2_hist, color="#2c7bb6", linewidth=1.2)
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.6)
    ax.axhline(y=r2_hist[-1], color="#d7191c", linestyle="--", linewidth=0.8,
               label=f"最终R方 = {r2_hist[-1]:.4f}")
    ax.fill_between(epochs, 0, r2_hist, alpha=0.15, color="#2c7bb6")
    ax.set_xlabel("训练轮次")
    ax.set_ylabel("R方分数")
    ax.set_title("训练过程中的R方分数变化趋势")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    # Annotation explaining low R²
    ax.annotate(
        "R方偏低说明模型对极端速度波动\n"
        "和复杂空间差异的拟合仍有限，\n"
        "但MAE约5 km/h，已可支撑\n"
        "路径规划原型验证。",
        xy=(60, 0.02), fontsize=7.5,
        bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))
    fig.tight_layout()
    fig.savefig(OUT / "fig_r2_analysis.png")
    plt.close(fig)
    print("  [OK] fig_r2_analysis.png")


# ============================================================
# Fig 10: Speed CDF (Cumulative Distribution)
# ============================================================
def fig_speed_cdf():
    fig, ax = plt.subplots(figsize=(6.5, 4))
    sorted_speeds = np.sort(speeds)
    cdf = np.arange(1, len(sorted_speeds) + 1) / len(sorted_speeds)
    ax.plot(sorted_speeds, cdf, "steelblue", linewidth=1.5)
    ax.axvline(x=50, color="#d7191c", linestyle="--", linewidth=1.0,
               label="50 km/h阈值")
    ax.axhline(y=0.0661, color="#d7191c", linestyle=":", linewidth=0.8,
               label=f"P(速度 < 50) = 6.61%")
    ax.set_xlabel("预测速度（km/h）")
    ax.set_ylabel("累计概率")
    ax.set_title("预测速度累计分布")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    # Annotate key percentiles
    for p in [10, 25, 50, 75, 90]:
        val = np.percentile(speeds, p)
        ax.annotate(f"P{p}={val:.1f}", xy=(val, p / 100), fontsize=7,
                    xytext=(val + 2, p / 100 + 0.05),
                    arrowprops=dict(arrowstyle="->", color="gray", lw=0.5))
    fig.tight_layout()
    fig.savefig(OUT / "fig_speed_cdf.png")
    plt.close(fig)
    print("  [OK] fig_speed_cdf.png")


# ============================================================
# Fig 11: Core vs Interpolated Speed Comparison
# ============================================================
def fig_core_vs_interpolated():
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    # Core
    ax = axes[0]
    ax.hist(speeds[core_mask], bins=25, color="#2c7bb6", edgecolor="white", alpha=0.8)
    ax.axvline(x=np.mean(speeds[core_mask]), color="darkblue", linestyle="-", linewidth=1.0)
    ax.set_xlabel("速度（km/h）")
    ax.set_ylabel("数量")
    ax.set_title(f"核心节点（n={core_mask.sum()}，μ={np.mean(speeds[core_mask]):.1f}）")
    ax.grid(True, alpha=0.3)

    # Interpolated
    ax = axes[1]
    ax.hist(speeds[interp_mask], bins=40, color="#fdae61", edgecolor="white", alpha=0.8)
    ax.axvline(x=np.mean(speeds[interp_mask]), color="darkorange", linestyle="-", linewidth=1.0)
    ax.set_xlabel("速度（km/h）")
    ax.set_ylabel("数量")
    ax.set_title(f"插值节点（n={interp_mask.sum()}，μ={np.mean(speeds[interp_mask]):.1f}）")
    ax.grid(True, alpha=0.3)

    fig.suptitle("核心节点与IDW插值节点速度分布对比", fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig_core_vs_interpolated.png")
    plt.close(fig)
    print("  [OK] fig_core_vs_interpolated.png")


# ============================================================
# Fig 12: Multi-step prediction error (if data available)
# ============================================================
def fig_error_by_speed_bin():
    """Error analysis by speed bin — using available distribution data."""
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    bins = np.arange(20, 85, 5)
    bin_centers = (bins[:-1] + bins[1:]) / 2
    counts, _ = np.histogram(speeds, bins=bins)
    ax.bar(bin_centers, counts, width=4, color="steelblue", edgecolor="white",
           alpha=0.85, align="center")
    ax.set_xlabel("速度区间（km/h）")
    ax.set_ylabel("检测器数量")
    ax.set_title("不同速度区间的检测器数量（预测第1步）")
    # Highlight low-speed bins
    for i, (center, count) in enumerate(zip(bin_centers, counts)):
        if center < 50:
            ax.bar(center, count, width=4, color="#d7191c", edgecolor="white", alpha=0.85)
    ax.grid(True, axis="y", alpha=0.3)
    # Legend
    legend_elements = [
        Patch(facecolor="steelblue", label="≥ 50 km/h"),
        Patch(facecolor="#d7191c", label="< 50 km/h（低速）"),
    ]
    ax.legend(handles=legend_elements, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_speed_bin_counts.png")
    plt.close(fig)
    print("  [OK] fig_speed_bin_counts.png")


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    print("Generating figures...")
    fig_training_loss()
    fig_metrics_convergence()
    fig_speed_distribution()
    fig_sensor_spatial()
    fig_speed_by_freeway()
    fig_algorithm_comparison()
    fig_time_comparison()
    fig_time_decomposition()
    fig_r2_analysis()
    fig_speed_cdf()
    fig_core_vs_interpolated()
    fig_error_by_speed_bin()
    print(f"\nDone! {len(list(OUT.glob('*.png')))} figures saved to {OUT.resolve()}")
