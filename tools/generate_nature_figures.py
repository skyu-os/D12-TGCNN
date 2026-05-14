#!/usr/bin/env python3
"""
Generate Nature-style figures for the thesis draft.

The script reads existing project outputs and writes editable SVG, PDF, and
high-resolution PNG files into docs/nature_figures/.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from textwrap import wrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib import gridspec
from matplotlib import font_manager as fm
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Patch
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "nature_figures"
RESULT_DIR = ROOT / "TGCN" / "result"
DRAFT_MD = ROOT / "初稿" / "论文初稿完整版_Markdown_word_input.md"
NATURE_DRAFT_MD = ROOT / "初稿" / "论文初稿完整版_Markdown_Nature图版.md"

OUT.mkdir(parents=True, exist_ok=True)


PALETTE = {
    "blue": "#0F4D92",
    "blue_2": "#3775BA",
    "blue_3": "#B4C0E4",
    "teal": "#42949E",
    "teal_2": "#77D7D1",
    "red": "#B64342",
    "red_2": "#E9A6A1",
    "gold": "#D89C2B",
    "violet": "#7C6CCF",
    "lilac": "#D8D8F0",
    "grey_0": "#F6F6F6",
    "grey_1": "#D8D8D8",
    "grey_2": "#8F8F8F",
    "grey_3": "#4D4D4D",
    "black": "#272727",
    "green": "#2E9E44",
}

METHOD_COLORS = {
    "Dijkstra": PALETTE["grey_3"],
    "A*": PALETTE["blue_2"],
    "ALT": PALETTE["teal"],
    "预测驱动": PALETTE["gold"],
    "时变A*": PALETTE["red"],
}


def apply_publication_style() -> None:
    for font_path in [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]:
        if font_path.exists():
            fm.fontManager.addfont(str(font_path))
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "Arial",
        "DejaVu Sans",
    ]
    plt.rcParams["svg.fonttype"] = "none"
    plt.rcParams["font.size"] = 8
    plt.rcParams["axes.spines.right"] = False
    plt.rcParams["axes.spines.top"] = False
    plt.rcParams["axes.linewidth"] = 0.8
    plt.rcParams["legend.frameon"] = False
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["savefig.dpi"] = 600


def cm(width_cm: float, height_cm: float) -> tuple[float, float]:
    return width_cm / 2.54, height_cm / 2.54


def save_all(fig: plt.Figure, stem: str) -> None:
    for suffix in ("svg", "pdf", "png"):
        fig.savefig(
            OUT / f"{stem}.{suffix}",
            bbox_inches="tight",
            facecolor="white",
            dpi=600,
        )
    plt.close(fig)
    print(f"[OK] {stem}.svg/.pdf/.png")


def add_panel_label(ax: plt.Axes, label: str, x: float = -0.08, y: float = 1.03) -> None:
    ax.text(
        x,
        y,
        label,
        transform=ax.transAxes,
        fontsize=10,
        fontweight="bold",
        ha="left",
        va="bottom",
        color=PALETTE["black"],
    )


def clean_axis(ax: plt.Axes) -> None:
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)


def box(
    ax: plt.Axes,
    xy: tuple[float, float],
    w: float,
    h: float,
    text: str,
    fc: str,
    ec: str = "white",
    fs: int = 7,
    lw: float = 0.8,
) -> FancyBboxPatch:
    patch = FancyBboxPatch(
        xy,
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        facecolor=fc,
        edgecolor=ec,
        linewidth=lw,
    )
    ax.add_patch(patch)
    ax.text(
        xy[0] + w / 2,
        xy[1] + h / 2,
        text,
        ha="center",
        va="center",
        fontsize=fs,
        color=PALETTE["black"],
        linespacing=1.25,
    )
    return patch


def arrow(
    ax: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    color: str = PALETTE["grey_3"],
    lw: float = 1.0,
    rad: float = 0.0,
) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=8,
            linewidth=lw,
            color=color,
            connectionstyle=f"arc3,rad={rad}",
        )
    )


def flow_figure(stem: str, title: str, stages: list[str], subtitle: str | None = None) -> None:
    fig, ax = plt.subplots(figsize=cm(18, 6.2))
    clean_axis(ax)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.02, 0.95, title, fontsize=11, fontweight="bold", ha="left", va="top")
    if subtitle:
        ax.text(0.02, 0.89, subtitle, fontsize=7.5, color=PALETTE["grey_3"], ha="left", va="top")

    n = len(stages)
    xs = np.linspace(0.06, 0.86, n)
    w = min(0.16, 0.78 / n)
    colors = [PALETTE["blue_3"], PALETTE["lilac"], PALETTE["teal_2"], "#F0E0D0", PALETTE["red_2"]]
    for i, (x, text) in enumerate(zip(xs, stages)):
        wrapped = "\n".join(wrap(text, 10))
        box(ax, (x, 0.42), w, 0.24, wrapped, colors[i % len(colors)], fs=7)
        if i < n - 1:
            arrow(ax, (x + w + 0.005, 0.54), (xs[i + 1] - 0.012, 0.54))

    ax.plot([0.06, 0.86 + w], [0.34, 0.34], color=PALETTE["grey_1"], lw=0.8)
    ax.text(0.06, 0.26, "data", color=PALETTE["blue"], fontsize=7)
    ax.text(0.31, 0.26, "model", color=PALETTE["violet"], fontsize=7)
    ax.text(0.55, 0.26, "cost", color=PALETTE["teal"], fontsize=7)
    ax.text(0.78, 0.26, "validation", color=PALETTE["red"], fontsize=7)
    save_all(fig, stem)


def fig1_research_route() -> None:
    flow_figure(
        "fig1-1_research_route_nature",
        "研究总体技术路线",
        ["原始交通与路网数据", "数据清洗与图建模", "T-GCN短时速度预测", "动态边权计算", "路径规划与系统验证"],
        "From detector observations to prediction-aware routing decisions",
    )


def fig3_data_modeling() -> None:
    fig, ax = plt.subplots(figsize=cm(18, 7.2))
    clean_axis(ax)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.02, 0.95, "数据处理与路网建模流程", fontsize=11, fontweight="bold", va="top")

    left = [
        ("PeMS detector\n速度序列", PALETTE["blue_3"]),
        ("OSM道路网络\n几何与拓扑", PALETTE["teal_2"]),
    ]
    mid = [
        ("缺失与异常处理", "#F0E0D0"),
        ("核心节点筛选", PALETTE["lilac"]),
        ("邻接矩阵构建", PALETTE["blue_3"]),
        ("道路图生成", PALETTE["teal_2"]),
    ]
    right = [
        ("T-GCN输入张量", PALETTE["blue_3"]),
        ("传感器-路段映射", PALETTE["teal_2"]),
        ("动态路径规划输入", PALETTE["red_2"]),
    ]

    for y, (txt, c) in zip([0.64, 0.34], left):
        box(ax, (0.04, y), 0.18, 0.16, txt, c)
    for i, (txt, c) in enumerate(mid):
        box(ax, (0.35, 0.70 - i * 0.17), 0.20, 0.12, txt, c)
    for y, (txt, c) in zip([0.68, 0.47, 0.26], right):
        box(ax, (0.70, y), 0.22, 0.13, txt, c)

    for y in [0.72, 0.42]:
        arrow(ax, (0.22, y), (0.35, y), PALETTE["grey_3"])
    for y in [0.76, 0.59, 0.42, 0.25]:
        arrow(ax, (0.55, y), (0.70, min(max(y, 0.32), 0.72)), PALETTE["grey_3"], rad=0.04)
    save_all(fig, "fig3-1_data_road_modeling_nature")


def fig2_tgcn_spatiotemporal() -> None:
    fig, ax = plt.subplots(figsize=cm(14.5, 7.5))
    clean_axis(ax)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.03, 0.94, "T-GCN 时空预测模型结构", fontsize=11, fontweight="bold", va="top")
    times = ["t-11", "t-7", "t-3", "t"]
    for i, t in enumerate(times):
        x = 0.09 + i * 0.12
        for j in range(4):
            ax.add_patch(Circle((x, 0.27 + j * 0.08), 0.018, facecolor=PALETTE["blue_3"], edgecolor="white", lw=0.5))
            if j:
                ax.plot([x, x], [0.27 + (j - 1) * 0.08, 0.27 + j * 0.08], color=PALETTE["grey_2"], lw=0.5)
        ax.text(x, 0.20, t, ha="center", fontsize=7, color=PALETTE["grey_3"])
    box(ax, (0.08, 0.62), 0.40, 0.12, "历史速度序列 X\n12个时间步", PALETTE["blue_3"])
    box(ax, (0.57, 0.62), 0.18, 0.12, "邻接矩阵 A", PALETTE["teal_2"])
    box(ax, (0.34, 0.41), 0.20, 0.12, "图卷积\n空间聚合", PALETTE["lilac"])
    box(ax, (0.61, 0.41), 0.20, 0.12, "GRU递归\n时间建模", "#F0E0D0")
    box(ax, (0.73, 0.20), 0.20, 0.12, "未来速度预测\n5 / 10 / 15 min", PALETTE["red_2"])
    arrow(ax, (0.30, 0.62), (0.42, 0.53))
    arrow(ax, (0.64, 0.62), (0.48, 0.53))
    arrow(ax, (0.54, 0.47), (0.61, 0.47))
    arrow(ax, (0.71, 0.41), (0.81, 0.32))
    save_all(fig, "fig2-1_tgcn_spatiotemporal_nature")


def fig4_model_overview() -> None:
    fig, ax = plt.subplots(figsize=cm(16, 7.8))
    clean_axis(ax)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.03, 0.94, "T-GCN 模型总体结构", fontsize=11, fontweight="bold", va="top")
    labels = [
        ("输入\nX ∈ R^(12×N)", PALETTE["blue_3"]),
        ("GCN\n空间特征", PALETTE["lilac"]),
        ("GRU\n隐藏状态", "#F0E0D0"),
        ("Linear\n多步输出", PALETTE["teal_2"]),
        ("速度预测\nY ∈ R^(3×N)", PALETTE["red_2"]),
    ]
    xs = [0.06, 0.25, 0.44, 0.63, 0.80]
    for i, ((txt, c), x) in enumerate(zip(labels, xs)):
        box(ax, (x, 0.52), 0.13, 0.18, txt, c, fs=7.5)
        if i < len(labels) - 1:
            arrow(ax, (x + 0.13, 0.61), (xs[i + 1] - 0.01, 0.61))
    box(ax, (0.24, 0.27), 0.28, 0.12, "路网邻接矩阵 A 约束节点信息传播", PALETTE["grey_0"], ec=PALETTE["grey_1"], fs=7)
    arrow(ax, (0.38, 0.39), (0.315, 0.52), PALETTE["teal"], rad=0.15)
    save_all(fig, "fig4-1_tgcn_model_overview_nature")


def fig4_gcn_extraction() -> None:
    fig, axes = plt.subplots(1, 2, figsize=cm(16, 6.6), gridspec_kw={"width_ratios": [1.2, 1]})
    ax = axes[0]
    clean_axis(ax)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    add_panel_label(ax, "a")
    ax.set_title("邻域信息聚合", fontsize=9, pad=6)
    coords = {"目标节点": (0.50, 0.50), "上游": (0.26, 0.66), "下游": (0.76, 0.62), "匝道": (0.31, 0.28), "相邻主线": (0.70, 0.25)}
    for name, (x, y) in coords.items():
        c = PALETTE["red_2"] if name == "目标节点" else PALETTE["blue_3"]
        ax.add_patch(Circle((x, y), 0.055, facecolor=c, edgecolor="white", lw=1.0))
        ax.text(x, y - 0.10, name, ha="center", va="top", fontsize=7)
        if name != "目标节点":
            arrow(ax, (x, y), coords["目标节点"], PALETTE["grey_3"], lw=0.8)
    ax = axes[1]
    add_panel_label(ax, "b")
    mat = np.array(
        [
            [1.0, 0.6, 0.2, 0.0, 0.0],
            [0.6, 1.0, 0.5, 0.2, 0.0],
            [0.2, 0.5, 1.0, 0.4, 0.2],
            [0.0, 0.2, 0.4, 1.0, 0.5],
            [0.0, 0.0, 0.2, 0.5, 1.0],
        ]
    )
    im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=1)
    ax.set_title("归一化邻接权重", fontsize=9, pad=6)
    ax.set_xticks(range(5), [f"n{i}" for i in range(1, 6)], fontsize=7)
    ax.set_yticks(range(5), [f"n{i}" for i in range(1, 6)], fontsize=7)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cbar.ax.tick_params(labelsize=7, length=2)
    save_all(fig, "fig4-2_gcn_feature_extraction_nature")


def fig4_tgcn_cell() -> None:
    fig, ax = plt.subplots(figsize=cm(15, 7.2))
    clean_axis(ax)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.03, 0.94, "T-GCN 单元结构", fontsize=11, fontweight="bold", va="top")
    box(ax, (0.06, 0.57), 0.16, 0.12, "x_t\n当前速度", PALETTE["blue_3"])
    box(ax, (0.06, 0.30), 0.16, 0.12, "h_{t-1}\n历史状态", PALETTE["grey_0"], ec=PALETTE["grey_1"])
    box(ax, (0.32, 0.67), 0.17, 0.11, "更新门 z_t\nGCN", PALETTE["lilac"])
    box(ax, (0.32, 0.47), 0.17, 0.11, "重置门 r_t\nGCN", PALETTE["lilac"])
    box(ax, (0.32, 0.27), 0.17, 0.11, "候选状态 h~_t\nGCN", PALETTE["teal_2"])
    box(ax, (0.62, 0.47), 0.18, 0.14, "门控融合\nh_t", "#F0E0D0")
    box(ax, (0.82, 0.47), 0.12, 0.14, "输出\ny_t", PALETTE["red_2"])
    for y in [0.72, 0.52, 0.32]:
        arrow(ax, (0.22, 0.63), (0.32, y))
        arrow(ax, (0.22, 0.36), (0.32, y), rad=-0.08)
        arrow(ax, (0.49, y), (0.62, 0.54))
    arrow(ax, (0.80, 0.54), (0.82, 0.54))
    save_all(fig, "fig4-3_tgcn_cell_nature")


def load_training_data():
    with open(RESULT_DIR / "TGCN_history.json", encoding="utf-8") as f:
        history = json.load(f)
    with open(RESULT_DIR / "TGCN_results.json", encoding="utf-8") as f:
        results = json.load(f)
    with open(RESULT_DIR / "online_prediction_step1.json", encoding="utf-8") as f:
        online = json.load(f)
    with open(RESULT_DIR / "tgcn_experiment_comparison.csv", encoding="utf-8-sig") as f:
        experiments = list(csv.DictReader(f))
    return history, results, online, experiments


def load_online_arrays(online):
    preds = online["sensor_predictions"]
    speeds = np.array([float(p["pred_speed_kmh"]) for p in preds])
    lats = np.array([float(p["latitude"]) for p in preds])
    lons = np.array([float(p["longitude"]) for p in preds])
    interp = np.array([bool(p["is_interpolated"]) for p in preds])
    fwy = np.array([str(p.get("fwy", "?")) for p in preds])
    return speeds, lats, lons, interp, fwy


def fig4_loss_and_metrics(history) -> None:
    epochs = np.arange(1, len(history["train_loss"]) + 1)
    fig, ax = plt.subplots(figsize=cm(11.5, 7.2))
    add_panel_label(ax, "a")
    ax.plot(epochs, history["train_loss"], color=PALETTE["blue"], lw=1.2, label="训练损失")
    ax.plot(epochs, history["val_loss"], color=PALETTE["gold"], lw=1.2, label="验证损失")
    best = int(np.argmin(history["val_loss"]) + 1)
    ax.axvline(best, color=PALETTE["grey_2"], lw=0.8, ls="--")
    ax.text(best + 1, max(history["val_loss"]) * 0.93, f"best epoch {best}", fontsize=7, color=PALETTE["grey_3"])
    ax.set_xlabel("训练轮次")
    ax.set_ylabel("MSE loss")
    ax.legend(loc="upper right", fontsize=7)
    ax.grid(axis="y", color=PALETTE["grey_1"], lw=0.4, alpha=0.8)
    save_all(fig, "fig4-4_loss_curves_nature")

    fig, axes = plt.subplots(1, 3, figsize=cm(18, 5.5), sharex=True)
    metrics = [("RMSE", "km/h", PALETTE["blue"]), ("MAE", "km/h", PALETTE["teal"]), ("MAPE", "%", PALETTE["red"])]
    for i, (key, unit, color) in enumerate(metrics):
        ax = axes[i]
        add_panel_label(ax, chr(ord("a") + i))
        values = np.array(history[key], dtype=float)
        ax.plot(epochs, values, color=color, lw=1.1)
        ax.scatter([epochs[-1]], [values[-1]], s=16, color=color, zorder=3)
        ax.text(0.98, 0.92, f"final {values[-1]:.2f}", transform=ax.transAxes, ha="right", va="top", fontsize=7)
        ax.set_title(key, fontsize=9)
        ax.set_xlabel("训练轮次")
        ax.set_ylabel(unit)
        ax.grid(axis="y", color=PALETTE["grey_1"], lw=0.4, alpha=0.8)
    save_all(fig, "fig4-5_metrics_convergence_nature")

    fig, ax = plt.subplots(figsize=cm(11.5, 6.8))
    add_panel_label(ax, "a")
    r2 = np.array(history["R2"], dtype=float)
    ax.plot(epochs, r2, color=PALETTE["violet"], lw=1.2)
    ax.fill_between(epochs, np.minimum(r2, 0), r2, color=PALETTE["lilac"], alpha=0.65)
    ax.axhline(0, color=PALETTE["grey_2"], ls="--", lw=0.8)
    ax.axhline(r2[-1], color=PALETTE["red"], ls="--", lw=0.8)
    ax.text(0.98, 0.12, f"final R² = {r2[-1]:.3f}", transform=ax.transAxes, ha="right", fontsize=7)
    ax.set_xlabel("训练轮次")
    ax.set_ylabel("R²")
    ax.grid(axis="y", color=PALETTE["grey_1"], lw=0.4, alpha=0.8)
    save_all(fig, "fig4-6_r2_analysis_nature")


def fig4_experiment_comparison(experiments) -> None:
    configs = [e["config"] for e in experiments]
    display = {
        "fast": "fast",
        "recommended": "recommended",
        "full": "full",
        "standard": "standard",
        "allstations_48g": "all stations",
    }
    colors = [PALETTE["blue_3"], PALETTE["red"], PALETTE["teal_2"], PALETTE["lilac"], PALETTE["grey_2"]]
    order = sorted(range(len(configs)), key=lambda i: ["fast", "recommended", "full", "standard", "allstations_48g"].index(configs[i]))
    labels = [display[configs[i]] for i in order]

    fig, axes = plt.subplots(1, 3, figsize=cm(18, 5.8))
    for j, metric in enumerate(["RMSE", "MAE", "MAPE"]):
        ax = axes[j]
        add_panel_label(ax, chr(ord("a") + j))
        vals = np.array([float(experiments[i][metric]) for i in order])
        bars = ax.bar(np.arange(len(vals)), vals, color=colors, edgecolor="white", linewidth=0.6)
        ax.set_xticks(np.arange(len(vals)), labels, rotation=35, ha="right")
        ax.set_title(metric, fontsize=9)
        ax.set_ylabel("km/h" if metric != "MAPE" else "%")
        ax.grid(axis="y", color=PALETTE["grey_1"], lw=0.4, alpha=0.8)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, val, f"{val:.2f}", ha="center", va="bottom", fontsize=6.5)
    save_all(fig, "fig4-7_error_metrics_comparison_nature")

    fig = plt.figure(figsize=cm(18, 6.2))
    gs = gridspec.GridSpec(1, 3, width_ratios=[1, 1, 1.1], wspace=0.35)
    panels = [("Accuracy", "准确率", PALETTE["blue"]), ("R2", "R²", PALETTE["violet"]), ("total_time_sec", "训练耗时 (min)", PALETTE["gold"])]
    for j, (metric, title, color) in enumerate(panels):
        ax = fig.add_subplot(gs[j])
        add_panel_label(ax, chr(ord("a") + j))
        vals = np.array([float(experiments[i][metric]) for i in order])
        if metric == "total_time_sec":
            vals = vals / 60
        bars = ax.bar(np.arange(len(vals)), vals, color=[color if labels[k] == "recommended" else PALETTE["grey_1"] for k in range(len(vals))], edgecolor="white", linewidth=0.6)
        ax.set_xticks(np.arange(len(vals)), labels, rotation=35, ha="right")
        ax.set_title(title, fontsize=9)
        ax.grid(axis="y", color=PALETTE["grey_1"], lw=0.4, alpha=0.8)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, val, f"{val:.2f}" if val < 10 else f"{val:.1f}", ha="center", va="bottom", fontsize=6.5)
    save_all(fig, "fig4-8_quality_time_comparison_nature")


def fig4_online_distributions(online) -> None:
    speeds, lats, lons, interp, fwy = load_online_arrays(online)
    low = speeds < 50

    fig, ax = plt.subplots(figsize=cm(11.5, 6.8))
    add_panel_label(ax, "a")
    bins = np.linspace(20, 82, 42)
    counts, edges, patches = ax.hist(speeds, bins=bins, color=PALETTE["blue_2"], edgecolor="white", linewidth=0.35)
    for patch, left, right in zip(patches, edges[:-1], edges[1:]):
        if right <= 50:
            patch.set_facecolor(PALETTE["red"])
        elif left < 50:
            patch.set_facecolor(PALETTE["red_2"])
    ax.axvline(50, color=PALETTE["red"], ls="--", lw=1.0, label="低速阈值 50 km/h")
    ax.axvline(speeds.mean(), color=PALETTE["black"], lw=0.9, label=f"均值 {speeds.mean():.1f} km/h")
    ax.set_xlabel("预测速度 (km/h)")
    ax.set_ylabel("detector 数量")
    ax.legend(fontsize=7)
    ax.grid(axis="y", color=PALETTE["grey_1"], lw=0.4, alpha=0.8)
    save_all(fig, "fig4-9_speed_distribution_nature")

    fig, ax = plt.subplots(figsize=cm(11.5, 6.8))
    add_panel_label(ax, "a")
    sorted_s = np.sort(speeds)
    cdf = np.arange(1, len(sorted_s) + 1) / len(sorted_s)
    ax.plot(sorted_s, cdf, color=PALETTE["blue"], lw=1.4)
    ax.axvline(50, color=PALETTE["red"], ls="--", lw=0.9)
    ax.axhline(low.mean(), color=PALETTE["red"], ls=":", lw=0.9)
    ax.text(0.05, 0.88, f"P(v < 50) = {low.mean() * 100:.1f}%", transform=ax.transAxes, fontsize=7)
    ax.set_xlabel("预测速度 (km/h)")
    ax.set_ylabel("累计概率")
    ax.grid(color=PALETTE["grey_1"], lw=0.4, alpha=0.8)
    save_all(fig, "fig4-10_speed_cdf_nature")

    fig, ax = plt.subplots(figsize=cm(11.5, 6.8))
    add_panel_label(ax, "a")
    bin_edges = np.arange(20, 86, 5)
    counts, _ = np.histogram(speeds, bins=bin_edges)
    centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    colors = [PALETTE["red"] if c < 50 else PALETTE["blue_2"] for c in centers]
    ax.bar(centers, counts, width=4.4, color=colors, edgecolor="white", linewidth=0.45)
    ax.set_xlabel("速度区间 (km/h)")
    ax.set_ylabel("detector 数量")
    ax.legend(handles=[Patch(facecolor=PALETTE["red"], label="<50 km/h"), Patch(facecolor=PALETTE["blue_2"], label="≥50 km/h")], fontsize=7)
    ax.grid(axis="y", color=PALETTE["grey_1"], lw=0.4, alpha=0.8)
    save_all(fig, "fig4-11_speed_bin_counts_nature")

    fig, ax = plt.subplots(figsize=cm(12.5, 9.2))
    add_panel_label(ax, "a")
    ax.scatter(lons[interp], lats[interp], s=3, color=PALETTE["grey_1"], alpha=0.55, linewidths=0, label=f"IDW扩展 n={interp.sum()}")
    ax.scatter(lons[~interp], lats[~interp], s=7, color=PALETTE["blue"], alpha=0.80, linewidths=0, label=f"核心节点 n={(~interp).sum()}")
    ax.scatter(lons[low], lats[low], s=13, color=PALETTE["red"], alpha=0.95, linewidths=0, label=f"低速 n={low.sum()}")
    ax.set_xlabel("经度")
    ax.set_ylabel("纬度")
    ax.legend(loc="lower left", fontsize=7)
    ax.grid(color=PALETTE["grey_1"], lw=0.35, alpha=0.7)
    save_all(fig, "fig4-12_sensor_spatial_map_nature")

    fig, axes = plt.subplots(1, 2, figsize=cm(16, 6.4), sharey=True)
    for ax, mask, color, title, label in [
        (axes[0], ~interp, PALETTE["blue"], "核心预测节点", "a"),
        (axes[1], interp, PALETTE["gold"], "IDW扩展节点", "b"),
    ]:
        add_panel_label(ax, label)
        ax.hist(speeds[mask], bins=28, color=color, edgecolor="white", linewidth=0.35, alpha=0.90)
        ax.axvline(speeds[mask].mean(), color=PALETTE["black"], lw=0.9)
        ax.set_title(f"{title} (n={mask.sum()}, μ={speeds[mask].mean():.1f})", fontsize=9)
        ax.set_xlabel("速度 (km/h)")
        ax.grid(axis="y", color=PALETTE["grey_1"], lw=0.4, alpha=0.8)
    axes[0].set_ylabel("数量")
    save_all(fig, "fig4-13_core_vs_interpolated_nature")

    unique, counts = np.unique(fwy, return_counts=True)
    top = unique[np.argsort(counts)[::-1][:10]]
    data = [speeds[fwy == f] for f in top]
    fig, ax = plt.subplots(figsize=cm(14.5, 6.8))
    add_panel_label(ax, "a")
    bp = ax.boxplot(data, widths=0.55, patch_artist=True, showfliers=False, medianprops={"color": PALETTE["black"], "lw": 0.9})
    for patch in bp["boxes"]:
        patch.set_facecolor(PALETTE["blue_3"])
        patch.set_edgecolor(PALETTE["blue"])
        patch.set_linewidth(0.8)
    ax.axhline(50, color=PALETTE["red"], ls="--", lw=0.9)
    ax.set_xticks(np.arange(1, len(top) + 1), [f"FWY-{f}" for f in top], rotation=35, ha="right")
    ax.set_ylabel("预测速度 (km/h)")
    ax.grid(axis="y", color=PALETTE["grey_1"], lw=0.4, alpha=0.8)
    save_all(fig, "fig4-14_speed_by_freeway_nature")


def fig5_dynamic_edge_weight() -> None:
    fig, ax = plt.subplots(figsize=cm(16, 7))
    clean_axis(ax)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.03, 0.94, "预测速度到动态边权映射", fontsize=11, fontweight="bold", va="top")
    steps = [
        ("T-GCN多步\n节点速度", PALETTE["blue_3"]),
        ("方差恢复\n速度校正", PALETTE["lilac"]),
        ("IDW扩展\n全部detector", PALETTE["teal_2"]),
        ("路段速度融合\nv_edge", "#F0E0D0"),
        ("通行时间\nw_e(t)=l/v", PALETTE["red_2"]),
    ]
    xs = [0.06, 0.24, 0.42, 0.60, 0.78]
    for i, ((txt, c), x) in enumerate(zip(steps, xs)):
        box(ax, (x, 0.48), 0.14, 0.17, txt, c)
        if i < len(steps) - 1:
            arrow(ax, (x + 0.14, 0.565), (xs[i + 1] - 0.01, 0.565))
    ax.text(0.08, 0.25, "节点域", color=PALETTE["blue"], fontsize=7)
    ax.text(0.44, 0.25, "空间映射", color=PALETTE["teal"], fontsize=7)
    ax.text(0.76, 0.25, "路径搜索代价", color=PALETTE["red"], fontsize=7)
    ax.plot([0.06, 0.92], [0.32, 0.32], color=PALETTE["grey_1"], lw=0.8)
    save_all(fig, "fig5-1_dynamic_edge_weight_nature")


def fig5_route_results() -> None:
    algos = ["Dijkstra", "A*", "ALT", "预测驱动", "时变A*"]
    distance = np.array([18.22, 19.07, 21.73, 19.07, 18.43])
    time = np.array([11.3, 16.4, 14.2, 19.0, 37.8])
    compute = np.array([2504.2, 2341.7, 1803.0, np.nan, 910.6])
    colors = [METHOD_COLORS[a] for a in algos]

    fig, axes = plt.subplots(1, 3, figsize=cm(18, 5.8))
    for ax, vals, title, ylabel, label in [
        (axes[0], distance, "路径长度", "km", "a"),
        (axes[1], time, "预计时间", "min", "b"),
        (axes[2], compute, "计算耗时", "ms", "c"),
    ]:
        add_panel_label(ax, label)
        vals_plot = np.nan_to_num(vals, nan=0.0)
        bars = ax.bar(np.arange(len(algos)), vals_plot, color=colors, edgecolor="white", linewidth=0.6)
        ax.set_title(title, fontsize=9)
        ax.set_ylabel(ylabel)
        ax.set_xticks(np.arange(len(algos)), algos, rotation=35, ha="right")
        ax.grid(axis="y", color=PALETTE["grey_1"], lw=0.4, alpha=0.8)
        for bar, val in zip(bars, vals):
            text = "N/A" if np.isnan(val) else (f"{val:.1f}" if val < 100 else f"{val:.0f}")
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), text, ha="center", va="bottom", fontsize=6.5)
    save_all(fig, "fig5-2_algorithm_comparison_nature")

    fig, ax = plt.subplots(figsize=cm(12, 7))
    x = np.arange(3)
    cats = ["静态A*", "预测驱动", "时变A*"]
    dist2 = np.array([19.07, 19.07, 18.43])
    time2 = np.array([16.4, 19.0, 37.8])
    width = 0.34
    add_panel_label(ax, "a")
    b1 = ax.bar(x - width / 2, dist2, width=width, color=PALETTE["blue_2"], edgecolor="white", label="长度 (km)")
    ax2 = ax.twinx()
    b2 = ax2.bar(x + width / 2, time2, width=width, color=PALETTE["red"], edgecolor="white", label="时间 (min)")
    ax.set_xticks(x, cats)
    ax.set_ylabel("路径长度 (km)", color=PALETTE["blue"])
    ax2.set_ylabel("预计时间 (min)", color=PALETTE["red"])
    ax.grid(axis="y", color=PALETTE["grey_1"], lw=0.4, alpha=0.8)
    ax.legend([b1, b2], ["长度 (km)", "时间 (min)"], loc="upper left", fontsize=7)
    for bars, vals, axis in [(b1, dist2, ax), (b2, time2, ax2)]:
        for bar, val in zip(bars, vals):
            axis.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{val:.1f}", ha="center", va="bottom", fontsize=7)
    save_all(fig, "fig5-3_static_vs_dynamic_nature")

    fig, ax = plt.subplots(figsize=cm(9.5, 7))
    add_panel_label(ax, "a")
    drive = 37.8 * 60 - 1080.2
    delay = 1080.2
    ax.barh([0], [drive / 60], color=PALETTE["blue_2"], edgecolor="white", label="道路行驶")
    ax.barh([0], [delay / 60], left=[drive / 60], color=PALETTE["red"], edgecolor="white", label="路口延迟")
    ax.set_yticks([0], ["时变A*"])
    ax.set_xlabel("时间 (min)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.13), ncol=2, fontsize=7)
    ax.text(drive / 120, 0, f"{drive/60:.1f}", ha="center", va="center", color="white", fontsize=8)
    ax.text(drive / 60 + delay / 120, 0, f"{delay/60:.1f}", ha="center", va="center", color="white", fontsize=8)
    ax.set_xlim(0, 40)
    ax.grid(axis="x", color=PALETTE["grey_1"], lw=0.4, alpha=0.8)
    save_all(fig, "fig5-4_time_decomposition_nature")


def fig6_system_architecture() -> None:
    fig, ax = plt.subplots(figsize=cm(17, 8.2))
    clean_axis(ax)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.03, 0.94, "原型系统总体架构", fontsize=11, fontweight="bold", va="top")
    layers = [
        ("数据层", ["PeMS速度数据", "OSM路网", "模型权重"], PALETTE["blue_3"]),
        ("服务层", ["预测服务", "路网管理", "动态边权"], PALETTE["teal_2"]),
        ("算法层", ["Dijkstra / A* / ALT", "预测驱动重规划", "时变A*"], "#F0E0D0"),
        ("展示层", ["地图渲染", "路径结果", "交通状态"], PALETTE["red_2"]),
    ]
    y0 = 0.72
    for idx, (name, items, color) in enumerate(layers):
        y = y0 - idx * 0.16
        ax.text(0.07, y + 0.035, name, ha="right", va="center", fontsize=8, fontweight="bold", color=PALETTE["grey_3"])
        for j, item in enumerate(items):
            box(ax, (0.12 + j * 0.25, y), 0.19, 0.08, item, color, fs=7)
            if idx < len(layers) - 1:
                arrow(ax, (0.215 + j * 0.25, y), (0.215 + j * 0.25, y - 0.08), PALETTE["grey_2"], lw=0.7)
    save_all(fig, "fig6-1_system_architecture_nature")


def fig6_composite(experiments) -> None:
    configs = [e["config"] for e in experiments]
    rec = next(e for e in experiments if e["config"] == "recommended")
    order = sorted(range(len(configs)), key=lambda i: ["fast", "recommended", "full", "standard", "allstations_48g"].index(configs[i]))
    labels = [configs[i].replace("allstations_48g", "all stations") for i in order]

    fig = plt.figure(figsize=cm(18, 10))
    gs = gridspec.GridSpec(2, 3, height_ratios=[0.82, 1], hspace=0.48, wspace=0.38)

    ax = fig.add_subplot(gs[0, 0])
    add_panel_label(ax, "a")
    ax.axis("off")
    metrics = [("RMSE", float(rec["RMSE"]), "km/h"), ("MAE", float(rec["MAE"]), "km/h"), ("MAPE", float(rec["MAPE"]), "%"), ("Accuracy", float(rec["Accuracy"]), "")]
    for i, (name, val, unit) in enumerate(metrics):
        y = 0.82 - i * 0.22
        ax.text(0.05, y, name, fontsize=8, color=PALETTE["grey_3"], ha="left", va="center")
        ax.text(0.95, y, f"{val:.2f} {unit}".strip(), fontsize=10, fontweight="bold", ha="right", va="center", color=PALETTE["blue" if i < 3 else "green"])
    ax.set_title("推荐配置结果", fontsize=9, loc="left")

    for j, metric in enumerate(["RMSE", "MAE"]):
        ax = fig.add_subplot(gs[0, j + 1])
        add_panel_label(ax, chr(ord("b") + j))
        vals = np.array([float(experiments[i][metric]) for i in order])
        colors = [PALETTE["red"] if labels[k] == "recommended" else PALETTE["grey_1"] for k in range(len(vals))]
        ax.bar(np.arange(len(vals)), vals, color=colors, edgecolor="white", linewidth=0.6)
        ax.set_xticks(np.arange(len(vals)), labels, rotation=35, ha="right", fontsize=6.5)
        ax.set_title(metric, fontsize=9)
        ax.grid(axis="y", color=PALETTE["grey_1"], lw=0.4, alpha=0.8)

    for j, metric in enumerate(["MAPE", "Accuracy", "total_time_sec"]):
        ax = fig.add_subplot(gs[1, j])
        add_panel_label(ax, chr(ord("d") + j))
        vals = np.array([float(experiments[i][metric]) for i in order])
        title = metric
        if metric == "total_time_sec":
            vals = vals / 60
            title = "Training time (min)"
        colors = [PALETTE["red"] if labels[k] == "recommended" else PALETTE["grey_1"] for k in range(len(vals))]
        ax.bar(np.arange(len(vals)), vals, color=colors, edgecolor="white", linewidth=0.6)
        ax.set_xticks(np.arange(len(vals)), labels, rotation=35, ha="right", fontsize=6.5)
        ax.set_title(title, fontsize=9)
        ax.grid(axis="y", color=PALETTE["grey_1"], lw=0.4, alpha=0.8)
    save_all(fig, "fig6-2_tgcn_composite_nature")


def fig6_route_flow() -> None:
    flow_figure(
        "fig6-3_route_experiment_flow_nature",
        "路径规划实验对比流程",
        ["统一OD输入", "静态基线搜索", "预测速度修正边权", "时变A*搜索", "距离 时间 耗时对比"],
        "A controlled comparison of static, prediction-aware, and time-dependent routing",
    )


def write_nature_markdown_copy() -> None:
    if not DRAFT_MD.exists():
        return
    text = DRAFT_MD.read_text(encoding="utf-8")
    replacements = {
        "../docs/paper_assets/fig1-1_research_route_clean.png": "../docs/nature_figures/fig1-1_research_route_nature.png",
        "../TGCN/T-GCN-master/T-GCN/pics/arc.png": "../docs/nature_figures/fig2-1_tgcn_spatiotemporal_nature.png",
        "../docs/paper_assets/fig3-1_data_road_modeling_clean.png": "../docs/nature_figures/fig3-1_data_road_modeling_nature.png",
        "../TGCN/T-GCN-master/big picture2.png": "../docs/nature_figures/fig4-1_tgcn_model_overview_nature.png",
        "../TGCN/T-GCN-master/T-GCN/pics/gcn.png": "../docs/nature_figures/fig4-2_gcn_feature_extraction_nature.png",
        "../TGCN/T-GCN-master/T-GCN/pics/Cell.png": "../docs/nature_figures/fig4-3_tgcn_cell_nature.png",
        "../docs/generated_figures/fig_loss_curves.png": "../docs/nature_figures/fig4-4_loss_curves_nature.png",
        "../docs/generated_figures/fig_metrics_convergence.png": "../docs/nature_figures/fig4-5_metrics_convergence_nature.png",
        "../docs/generated_figures/fig_r2_analysis.png": "../docs/nature_figures/fig4-6_r2_analysis_nature.png",
        "../TGCN/result/tgcn_error_metrics_comparison.png": "../docs/nature_figures/fig4-7_error_metrics_comparison_nature.png",
        "../TGCN/result/tgcn_quality_time_comparison.png": "../docs/nature_figures/fig4-8_quality_time_comparison_nature.png",
        "../docs/generated_figures/fig_speed_distribution.png": "../docs/nature_figures/fig4-9_speed_distribution_nature.png",
        "../docs/generated_figures/fig_speed_cdf.png": "../docs/nature_figures/fig4-10_speed_cdf_nature.png",
        "../docs/generated_figures/fig_speed_bin_counts.png": "../docs/nature_figures/fig4-11_speed_bin_counts_nature.png",
        "../docs/generated_figures/fig_sensor_spatial_map.png": "../docs/nature_figures/fig4-12_sensor_spatial_map_nature.png",
        "../docs/generated_figures/fig_core_vs_interpolated.png": "../docs/nature_figures/fig4-13_core_vs_interpolated_nature.png",
        "../docs/generated_figures/fig_speed_by_freeway.png": "../docs/nature_figures/fig4-14_speed_by_freeway_nature.png",
        "../docs/paper_assets/fig5-1_dynamic_edge_weight_clean.png": "../docs/nature_figures/fig5-1_dynamic_edge_weight_nature.png",
        "../docs/generated_figures/fig_algorithm_comparison.png": "../docs/nature_figures/fig5-2_algorithm_comparison_nature.png",
        "../docs/generated_figures/fig_static_vs_dynamic.png": "../docs/nature_figures/fig5-3_static_vs_dynamic_nature.png",
        "../docs/generated_figures/fig_time_decomposition.png": "../docs/nature_figures/fig5-4_time_decomposition_nature.png",
        "../docs/paper_assets/fig6-1_system_architecture_clean.png": "../docs/nature_figures/fig6-1_system_architecture_nature.png",
        "../TGCN/result/tgcn_paper_single_figure_cn_600dpi.png": "../docs/nature_figures/fig6-2_tgcn_composite_nature.png",
        "../docs/paper_assets/fig6-2_route_experiment_flow_clean.png": "../docs/nature_figures/fig6-3_route_experiment_flow_nature.png",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    NATURE_DRAFT_MD.write_text(text, encoding="utf-8")
    print(f"[OK] wrote {NATURE_DRAFT_MD.relative_to(ROOT)}")


def main() -> None:
    apply_publication_style()
    history, _results, online, experiments = load_training_data()

    fig1_research_route()
    fig2_tgcn_spatiotemporal()
    fig3_data_modeling()
    fig4_model_overview()
    fig4_gcn_extraction()
    fig4_tgcn_cell()
    fig4_loss_and_metrics(history)
    fig4_experiment_comparison(experiments)
    fig4_online_distributions(online)
    fig5_dynamic_edge_weight()
    fig5_route_results()
    fig6_system_architecture()
    fig6_composite(experiments)
    fig6_route_flow()
    write_nature_markdown_copy()
    print(f"Done. Figures saved to {OUT}")


if __name__ == "__main__":
    main()
