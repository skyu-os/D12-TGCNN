"""
T-GCN 训练脚本 (PeMS D12 交通预测)

用法:
    # 用 YAML 配置文件启动（推荐）
    python train.py --config configs/fast.yaml
    python train.py --config configs/recommended.yaml

    # 命令行参数
    python train.py --model TGCN --epochs 100 --hidden_dim 64

    # 配置文件 + 命令行覆盖
    python train.py --config configs/recommended.yaml --epochs 200 --lr 0.002
"""
import os
import sys
import time
import json
import yaml
import argparse
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from models import MODELS
from data import load_speed_data, load_adjacency_matrix, normalize_data, TrafficDataset
from utils.metrics import numpy_metrics


def load_yaml_config(yaml_path):
    """加载 YAML 配置文件，返回 flat dict"""
    with open(yaml_path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    flat = {}
    for section in cfg.values():
        if isinstance(section, dict):
            flat.update(section)
    return flat


def train_one_epoch(model, train_loader, optimizer, criterion, device, scaler=None, use_amp=False):
    model.train()
    total_loss = 0
    amp_enabled = use_amp and device.type == "cuda"
    non_blocking = device.type == "cuda"
    for batch_x, batch_y in train_loader:
        batch_x = batch_x.to(device, non_blocking=non_blocking)
        batch_y = batch_y.to(device, non_blocking=non_blocking)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp_enabled):
            pred = model(batch_x)
            loss = criterion(pred, batch_y)

        if scaler is not None and amp_enabled:
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            optimizer.step()
        total_loss += loss.item()
    return total_loss / len(train_loader)


def evaluate(model, test_loader, criterion, max_val, device, use_amp=False):
    model.eval()
    all_preds = []
    all_targets = []
    total_loss = 0
    amp_enabled = use_amp and device.type == "cuda"
    non_blocking = device.type == "cuda"
    with torch.no_grad():
        for batch_x, batch_y in test_loader:
            batch_x = batch_x.to(device, non_blocking=non_blocking)
            batch_y = batch_y.to(device, non_blocking=non_blocking)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp_enabled):
                pred = model(batch_x)
                loss = criterion(pred, batch_y)
            total_loss += loss.item()
            all_preds.append((pred.cpu().numpy() * max_val))
            all_targets.append((batch_y.cpu().numpy() * max_val))

    preds = np.concatenate(all_preds, axis=0).flatten()
    targets = np.concatenate(all_targets, axis=0).flatten()
    metrics = numpy_metrics(preds, targets)
    metrics["loss"] = total_loss / max(len(test_loader), 1)
    return metrics


def main():
    # 第一遍：只解析 --config
    parser = argparse.ArgumentParser(description="T-GCN 交通预测训练")
    parser.add_argument("--config", type=str, default=None,
                        help="YAML 配置文件路径，命令行参数可覆盖配置文件")
    # 所有训练参数都设为 None，由配置文件或默认值填充
    parser.add_argument("--model", type=str, default=None, choices=list(MODELS.keys()))
    parser.add_argument("--speed_path", type=str, default=None)
    parser.add_argument("--adj_path", type=str, default=None)
    parser.add_argument("--hidden_dim", type=int, default=None)
    parser.add_argument("--seq_len", type=int, default=None, help="输入序列长度")
    parser.add_argument("--pre_len", type=int, default=None, help="预测步长")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch_size", type=int, default=None)
    parser.add_argument("--lr", type=float, default=None)
    parser.add_argument("--weight_decay", type=float, default=None)
    parser.add_argument("--split_ratio", type=float, default=None,
                        help="训练/验证划分比例")
    parser.add_argument("--config_path", type=str, default=None,
                        help="data_config.json 路径，自动计算 split")
    parser.add_argument("--save_dir", type=str, default=None)
    parser.add_argument("--results_dir", type=str, default=None)
    parser.add_argument("--use_regularization", action="store_true", default=None)
    parser.add_argument("--num_workers", type=int, default=None,
                        help="DataLoader 进程数")
    parser.add_argument("--prefetch_factor", type=int, default=None,
                        help="每个 worker 的预取批次数（num_workers>0 时生效）")
    parser.add_argument("--amp", action="store_true", default=None,
                        help="启用 CUDA AMP 混合精度")
    parser.add_argument("--no-amp", action="store_false", dest="amp",
                        help="禁用 CUDA AMP 混合精度")

    args = parser.parse_args()

    # 默认值
    defaults = dict(
        model="TGCN", speed_path="data/d12_speed.csv", adj_path="data/d12_adj.csv",
        hidden_dim=64, seq_len=12, pre_len=3, epochs=100, batch_size=32,
        lr=0.001, weight_decay=1.5e-3, split_ratio=0.85,
        config_path=None, save_dir="saved_models", results_dir="results",
        use_regularization=False, num_workers=8, prefetch_factor=4, amp=True,
    )

    # 优先级：命令行 > YAML > 默认值
    if args.config:
        yaml_cfg = load_yaml_config(args.config)
        print(f"已加载配置: {args.config}")
        defaults.update(yaml_cfg)

    # 命令行显式参数覆盖（非 None 的值）
    for k, v in vars(args).items():
        if v is not None and k != 'config':
            defaults[k] = v

    # 写回 args
    for k, v in defaults.items():
        setattr(args, k, v)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"设备: {device}")
    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("high")
    if device.type == "cuda":
        torch.backends.cudnn.benchmark = True

    # 如果有 config，自动算 split_ratio
    if args.config_path and os.path.exists(args.config_path):
        import json
        with open(args.config_path) as f:
            cfg = json.load(f)
        train_ts = cfg.get("train_timesteps", 0)
        total_ts = cfg.get("total_timesteps", 0)
        if train_ts and total_ts:
            args.split_ratio = train_ts / total_ts
            print(f"自动 split_ratio={args.split_ratio:.4f} (训练{train_ts}/总计{total_ts})")

    # 加载数据
    print("加载数据...")
    speed_data = load_speed_data(args.speed_path)
    adj = load_adjacency_matrix(args.adj_path)
    num_nodes = adj.shape[0]
    print(f"传感器数: {num_nodes}, 时间步: {speed_data.shape[0]}")

    assert speed_data.shape[1] == num_nodes, \
        f"速度数据列数({speed_data.shape[1]}) != 邻接矩阵维度({num_nodes})"

    # 归一化
    normalized_data, max_val = normalize_data(speed_data)
    print(f"速度最大值: {max_val:.1f}")

    # 划分训练/测试集
    train_size = int(len(normalized_data) * args.split_ratio)
    train_data = normalized_data[:train_size]
    test_data = normalized_data[train_size:]
    train_dataset = TrafficDataset(train_data, args.seq_len, args.pre_len)
    test_dataset = TrafficDataset(test_data, args.seq_len, args.pre_len)
    num_workers = max(0, int(args.num_workers))
    loader_kwargs = {
        "num_workers": num_workers,
        "pin_memory": device.type == "cuda",
    }
    if num_workers > 0:
        loader_kwargs["persistent_workers"] = True
        loader_kwargs["prefetch_factor"] = max(2, int(args.prefetch_factor))
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, **loader_kwargs)
    test_loader = DataLoader(test_dataset, batch_size=len(test_dataset), shuffle=False, **loader_kwargs)
    print(f"训练样本: {len(train_dataset)}, 测试样本: {len(test_dataset)}")

    # 创建模型
    model = MODELS[args.model]
    if args.model == "TGCN":
        model = model(adj=adj, hidden_dim=args.hidden_dim, output_dim=args.pre_len)
    elif args.model == "GRU":
        model = model(num_nodes=num_nodes, hidden_dim=args.hidden_dim, output_dim=args.pre_len)
    elif args.model == "GCN":
        model = model(adj=adj, hidden_dim=args.seq_len, output_dim=args.pre_len)
    model = model.to(device)

    total_params = sum(p.numel() for p in model.parameters())
    print(f"模型: {args.model}, 参数量: {total_params:,}")

    # 损失函数和优化器
    if args.use_regularization:
        from utils.losses import mse_with_regularizer_loss
        criterion = lambda pred, target: mse_with_regularizer_loss(pred, target, model)
    else:
        criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=20, gamma=0.95)
    use_amp = bool(args.amp) and device.type == "cuda"
    scaler = torch.cuda.amp.GradScaler(enabled=use_amp)
    print(f"加速设置: amp={use_amp}, num_workers={num_workers}, pin_memory={loader_kwargs['pin_memory']}")

    # 训练
    print("\n开始训练...")
    print("-" * 70)
    best_rmse = float("inf")
    history = {"train_loss": [], "val_loss": [], "RMSE": [], "MAE": [], "MAPE": [], "R2": []}
    start_time = time.time()

    for epoch in range(1, args.epochs + 1):
        train_loss = train_one_epoch(
            model, train_loader, optimizer, criterion, device, scaler=scaler, use_amp=use_amp
        )
        metrics = evaluate(model, test_loader, criterion, max_val, device, use_amp=use_amp)
        scheduler.step()

        history["train_loss"].append(train_loss)
        history["val_loss"].append(metrics["loss"])
        history["RMSE"].append(metrics["RMSE"])
        history["MAE"].append(metrics["MAE"])
        history["MAPE"].append(metrics["MAPE"])
        history["R2"].append(metrics["R2"])

        if metrics["RMSE"] < best_rmse:
            best_rmse = metrics["RMSE"]
            os.makedirs(args.save_dir, exist_ok=True)
            best_path = os.path.join(args.save_dir, f"{args.model}_best.pth")
            torch.save({
                "model_state": model.state_dict(),
                "adj": adj,
                "hidden_dim": args.hidden_dim,
                "num_nodes": num_nodes,
                "max_val": max_val,
                "seq_len": args.seq_len,
                "pre_len": args.pre_len,
                "model_name": args.model,
                "metrics": metrics,
                "epoch": epoch,
            }, best_path)

        if epoch % 5 == 0 or epoch == 1:
            elapsed = time.time() - start_time
            print(f"Epoch {epoch:3d}/{args.epochs} | "
                  f"Loss: {train_loss:.6f} | "
                  f"RMSE: {metrics['RMSE']:.4f} | "
                  f"MAE: {metrics['MAE']:.4f} | "
                  f"MAPE: {metrics['MAPE']:.2f}% | "
                  f"R2: {metrics['R2']:.4f} | "
                  f"Time: {elapsed:.1f}s")

    total_time = time.time() - start_time
    print("-" * 70)
    print(f"训练完成! 总时间: {total_time:.1f}s ({total_time/60:.1f}min)")
    print(f"最佳 RMSE: {best_rmse:.4f}")
    print(f"模型保存: {best_path}")

    # 保存训练历史
    os.makedirs(args.results_dir, exist_ok=True)
    history_path = os.path.join(args.results_dir, f"{args.model}_history.json")
    for k in history:
        history[k] = [float(v) for v in history[k]]
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)

    # 最终评估
    checkpoint = torch.load(best_path, weights_only=False)
    model.load_state_dict(checkpoint["model_state"])
    final_metrics = evaluate(model, test_loader, criterion, max_val, device, use_amp=use_amp)
    print(f"\n最终评估 (最佳模型 Epoch {checkpoint['epoch']}):")
    for k, v in final_metrics.items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    # 保存最终结果
    results_path = os.path.join(args.results_dir, f"{args.model}_results.json")
    final_metrics["total_time"] = total_time
    final_metrics["epochs"] = args.epochs
    final_metrics["model"] = args.model
    final_metrics["hidden_dim"] = args.hidden_dim
    with open(results_path, "w") as f:
        json.dump(final_metrics, f, indent=2, default=str)
    print(f"结果保存: {results_path}")


if __name__ == "__main__":
    main()
