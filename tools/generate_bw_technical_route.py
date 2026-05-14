#!/usr/bin/env python3
"""Generate a Nature-style black-and-white technical route diagram."""

from __future__ import annotations

from pathlib import Path
from textwrap import wrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "nature_figures"
OUT.mkdir(parents=True, exist_ok=True)


def setup_style() -> None:
    for font_path in [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]:
        if font_path.exists():
            fm.fontManager.addfont(str(font_path))

    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "Arial"]
    plt.rcParams["svg.fonttype"] = "none"
    plt.rcParams["axes.unicode_minus"] = False


def add_box(ax, x, y, w, h, title, body=None, lw=1.05, face="#FFFFFF", dashed=False):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.014,rounding_size=0.012",
        facecolor=face,
        edgecolor="#111111",
        linewidth=lw,
        linestyle="--" if dashed else "-",
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h * 0.66, title, ha="center", va="center", fontsize=10.2, fontweight="bold")
    if body:
        wrapped = "\n".join(wrap(body, 18))
        ax.text(x + w / 2, y + h * 0.32, wrapped, ha="center", va="center", fontsize=7.0, linespacing=1.22)
    return patch


def add_arrow(ax, start, end, lw=1.0, style="-|>", rad=0.0):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle=style,
            mutation_scale=10,
            linewidth=lw,
            color="#111111",
            connectionstyle=f"arc3,rad={rad}",
            shrinkA=2,
            shrinkB=2,
        )
    )


def main() -> None:
    setup_style()
    fig, ax = plt.subplots(figsize=(6.6, 10.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(0.08, 0.965, "技术路线图", fontsize=15, fontweight="bold", ha="left", va="top")
    ax.text(
        0.08,
        0.932,
        "基于实时交通状态预测的智能路径规划系统设计与实现",
        fontsize=8.5,
        ha="left",
        va="top",
    )
    ax.plot([0.08, 0.92], [0.90, 0.90], color="#111111", linewidth=0.9)

    flow_x = 0.22
    flow_w = 0.56
    flow_h = 0.086
    ys = [0.785, 0.665, 0.545, 0.425, 0.305, 0.185]
    steps = [
        ("1  原始数据输入", "PeMS detector 速度数据\nOSM 道路网络数据"),
        ("2  数据清洗与图建模", "缺失值处理、传感器筛选\n构建速度序列 X 与邻接矩阵 A"),
        ("3  T-GCN 短时交通预测", "利用图卷积提取空间依赖\n利用 GRU 捕获时间变化"),
        ("4  预测速度空间扩展", "方差恢复修正速度波动\nIDW 映射至全部 detector"),
        ("5  动态边权计算", "将节点速度映射到道路边\n由路段长度和速度计算通行时间"),
        ("6  路径规划与实验验证", "静态 A*、预测驱动规划、时变 A*\n对比路径长度、时间和计算耗时"),
    ]

    for i, (y, (title, body)) in enumerate(zip(ys, steps)):
        face = "#FFFFFF" if i % 2 == 0 else "#F8F8F8"
        add_box(ax, flow_x, y, flow_w, flow_h, title, body, face=face)
        if i < len(ys) - 1:
            add_arrow(
                ax,
                (flow_x + flow_w / 2, y),
                (flow_x + flow_w / 2, ys[i + 1] + flow_h),
                lw=1.05,
                rad=0.0,
            )

    # Straight side labels for domains, drawn as brackets without curves.
    domains = [
        ("数据基础", 0.665, 0.871),
        ("预测建模", 0.425, 0.631),
        ("路径决策", 0.185, 0.391),
    ]
    for label, y0, y1 in domains:
        x = 0.12
        ax.plot([x, x], [y0, y1], color="#111111", linewidth=0.75)
        ax.plot([x, x + 0.035], [y1, y1], color="#111111", linewidth=0.75)
        ax.plot([x, x + 0.035], [y0, y0], color="#111111", linewidth=0.75)
        ax.text(x - 0.02, (y0 + y1) / 2, label, rotation=90, ha="center", va="center", fontsize=7.8)

    ax.add_patch(Rectangle((0.12, 0.075), 0.76, 0.065, facecolor="white", edgecolor="#111111", linewidth=0.7))
    ax.text(
        0.50,
        0.108,
        "主流程：真实数据 → 图结构输入 → 交通状态预测 → 动态通行代价 → 路径规划验证",
        fontsize=7.5,
        ha="center",
        va="center",
    )

    ax.text(
        0.50,
        0.035,
        "注：全图采用黑白线稿和直线箭头，适合论文正文黑白打印。",
        fontsize=7.2,
        ha="center",
        va="center",
    )

    for suffix in ("png", "svg", "pdf"):
        fig.savefig(OUT / f"technical_route_bw.{suffix}", bbox_inches="tight", dpi=600, facecolor="white")
    plt.close(fig)
    print(f"saved: {OUT / 'technical_route_bw.png'}")


if __name__ == "__main__":
    main()
