from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "初稿" / "图片"


def setup_fonts() -> None:
    candidates = [
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            break
    else:
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def rounded(ax, xy, wh, text, fontsize=10, lw=1.2, fc="white", ec="#111111", dashed=False):
    x, y = xy
    w, h = wh
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        linewidth=lw,
        edgecolor=ec,
        facecolor=fc,
        linestyle=(0, (5, 3)) if dashed else "solid",
    )
    ax.add_patch(box)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize, linespacing=1.35)
    return box


def arrow(ax, start, end, lw=1.15, rad=0.0):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=10,
            linewidth=lw,
            color="#111111",
            connectionstyle=f"arc3,rad={rad}",
            shrinkA=2,
            shrinkB=2,
        )
    )


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=320, bbox_inches="tight")
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)


def fig_research_route():
    fig, ax = plt.subplots(figsize=(7.2, 8.8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    rounded(ax, (0.12, 0.88), (0.76, 0.065), "第一章 绪论\n研究背景、研究现状与研究内容", fontsize=10.8, dashed=True)
    rounded(ax, (0.12, 0.76), (0.76, 0.075), "第二章 相关技术概述\n交通预测模型、T-GCN 与动态路径规划算法", fontsize=10.6, dashed=True)

    rounded(ax, (0.10, 0.56), (0.24, 0.13), "第三章\n数据处理与路网建模\nPeMS 数据 + OSM 路网", fontsize=9.2, dashed=True)
    rounded(ax, (0.38, 0.56), (0.24, 0.13), "第四章\nT-GCN 交通状态预测\n空间关联 + 时间依赖", fontsize=9.2, dashed=True)
    rounded(ax, (0.66, 0.56), (0.24, 0.13), "第五章\n动态路径规划算法\n边权更新 + 时变 A*", fontsize=9.2, dashed=True)

    rounded(ax, (0.14, 0.36), (0.72, 0.09), "第六章 原型系统实现与实验分析\n接口服务、前端展示、预测实验、路径规划对比", fontsize=10.2, dashed=True)
    rounded(ax, (0.14, 0.22), (0.72, 0.075), "第七章 总结与展望\n归纳结论，分析不足并提出改进方向", fontsize=10.2, dashed=True)

    arrow(ax, (0.50, 0.88), (0.50, 0.835))
    arrow(ax, (0.25, 0.76), (0.22, 0.69))
    arrow(ax, (0.50, 0.76), (0.50, 0.69))
    arrow(ax, (0.75, 0.76), (0.78, 0.69))
    arrow(ax, (0.34, 0.625), (0.38, 0.625))
    arrow(ax, (0.62, 0.625), (0.66, 0.625))
    arrow(ax, (0.22, 0.56), (0.38, 0.45), rad=-0.04)
    arrow(ax, (0.50, 0.56), (0.50, 0.45))
    arrow(ax, (0.78, 0.56), (0.62, 0.45), rad=0.04)
    arrow(ax, (0.50, 0.36), (0.50, 0.295))

    ax.text(0.50, 0.12, "图1-1 研究总体技术路线图", ha="center", va="center", fontsize=11)
    save(fig, "fig1-1_research_route")


def fig_metric(name, values, ylabel, color, filename):
    fig, ax = plt.subplots(figsize=(6.0, 3.0))
    epochs = list(range(1, len(values) + 1))
    ax.plot(epochs, values, color=color, linewidth=1.8)
    ax.scatter([epochs[-1]], [values[-1]], color=color, s=28, zorder=3)
    ax.grid(True, color="#e6e6e6", linewidth=0.8)
    ax.set_xlabel("训练轮次")
    ax.set_ylabel(ylabel)
    ax.set_title(name, fontsize=12, pad=8)
    ax.text(0.98, 0.08, f"最终值：{values[-1]:.4f}", ha="right", va="bottom", transform=ax.transAxes, fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    save(fig, filename)


def metric_figures():
    history = json.loads((ROOT / "TGCN" / "result" / "TGCN_history.json").read_text(encoding="utf-8"))
    fig_metric("T-GCN 验证集 RMSE 收敛趋势", history["RMSE"], "RMSE / km·h$^{-1}$", "#1f77b4", "fig4-5a_rmse_convergence")
    fig_metric("T-GCN 验证集 MAE 收敛趋势", history["MAE"], "MAE / km·h$^{-1}$", "#2ca02c", "fig4-5b_mae_convergence")
    fig_metric("T-GCN 验证集 MAPE 收敛趋势", history["MAPE"], "MAPE / %", "#d62728", "fig4-5c_mape_convergence")


def fig_time_decomposition():
    labels = ["道路行驶时间", "路口等待、转向与启停约束"]
    values = [19.8, 18.0]
    colors = ["#7aa6c2", "#d8a05f"]
    fig, ax = plt.subplots(figsize=(6.2, 2.2))
    left = 0.0
    for label, value, color in zip(labels, values, colors):
        ax.barh([0], [value], left=left, height=0.42, color=color, edgecolor="#333333", linewidth=0.8)
        ax.text(left + value / 2, 0, f"{label}\n{value:.1f} min", ha="center", va="center", fontsize=9)
        left += value
    ax.set_xlim(0, 40)
    ax.set_yticks([])
    ax.set_xlabel("时间 / min")
    ax.set_title("时变 A* 路径时间构成", fontsize=12, pad=8)
    ax.grid(True, axis="x", color="#e6e6e6", linewidth=0.8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.text(37.8, -0.43, "合计 37.8 min", ha="right", va="center", fontsize=9)
    save(fig, "fig5-4_time_decomposition_compact")


def fig_system_architecture():
    fig, ax = plt.subplots(figsize=(8.2, 6.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    layers = [
        (0.06, 0.78, 0.88, 0.12, "展示层", ["地图页面", "路径查询", "预测路况"], "#f7fbff"),
        (0.06, 0.58, 0.88, 0.13, "接口层", ["基础路径 API", "交通预测 API", "预测路径 API", "路段状态 API"], "#fffdf7"),
        (0.06, 0.36, 0.88, 0.15, "核心服务层", ["交通预测", "路网管理", "预测驱动规划", "时变 A*"], "#f8fff8"),
        (0.06, 0.15, 0.88, 0.13, "数据与模型层", ["模型权重", "PeMS 数据", "OSM 路网", "detector 映射"], "#fbf8ff"),
    ]

    centers = []
    for x, y, w, h, layer_name, items, fc in layers:
        ax.add_patch(Rectangle((x, y), w, h, linewidth=1.1, edgecolor="#111111", facecolor=fc))
        ax.text(x + 0.075, y + h / 2, layer_name, ha="center", va="center", fontsize=10.5, fontweight="bold")
        item_centers = []
        item_w = (w - 0.22) / len(items)
        for i, item in enumerate(items):
            bx = x + 0.15 + i * item_w
            rounded(ax, (bx, y + 0.035), (item_w - 0.018, h - 0.07), item, fontsize=8.8, lw=0.9, fc="white")
            item_centers.append((bx + (item_w - 0.018) / 2, y + h / 2))
        centers.append(item_centers)

    # Main clean top-down data flow.
    for upper, lower in zip(centers[:-1], centers[1:]):
        for idx in range(min(len(upper), len(lower))):
            arrow(ax, (upper[idx][0], upper[idx][1] - 0.06), (lower[idx][0], lower[idx][1] + 0.065), lw=0.95)
    arrow(ax, (centers[1][1][0], centers[1][1][1] - 0.065), (centers[2][0][0], centers[2][0][1] + 0.075), lw=0.95)
    arrow(ax, (centers[2][0][0], centers[2][0][1] - 0.075), (centers[3][0][0], centers[3][0][1] + 0.065), lw=0.95)
    arrow(ax, (centers[2][2][0], centers[2][2][1] - 0.075), (centers[3][3][0], centers[3][3][1] + 0.065), lw=0.95)

    ax.text(0.50, 0.07, "图6-1 系统总体架构图", ha="center", va="center", fontsize=11)
    save(fig, "fig6-1_system_architecture")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    setup_fonts()
    fig_research_route()
    metric_figures()
    fig_time_decomposition()
    fig_system_architecture()


if __name__ == "__main__":
    main()
