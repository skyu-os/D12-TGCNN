"""
T-GCN 预测模块

用法:
    # 命令行预测
    python predict.py --model_path saved_models/TGCN_best.pth --speed_path data/d12_speed.csv

    # Python API 调用
    from predict import TGCNPredictor
    predictor = TGCNPredictor("saved_models/TGCN_best.pth")
    predictions = predictor.predict(recent_speed_data)
"""
import os
import argparse
import sys
import numpy as np
import torch
from models import MODELS
from data import normalize_data


class TGCNPredictor:
    def __init__(self, model_path, device=None):
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        checkpoint = self._load_checkpoint(model_path)
        self.model_name = checkpoint["model_name"]
        self.max_val = checkpoint["max_val"]
        self.seq_len = checkpoint["seq_len"]
        self.pre_len = checkpoint["pre_len"]
        self.num_nodes = checkpoint["num_nodes"]
        self._checkpoint = checkpoint

        # 重建模型
        adj = checkpoint["adj"]
        hidden_dim = checkpoint["hidden_dim"]
        model_cls = MODELS[self.model_name]
        if self.model_name == "TGCN":
            self.model = model_cls(adj=adj, hidden_dim=hidden_dim, output_dim=self.pre_len)
        elif self.model_name == "GRU":
            self.model = model_cls(num_nodes=self.num_nodes, hidden_dim=hidden_dim,
                                    output_dim=self.pre_len)
        elif self.model_name == "GCN":
            self.model = model_cls(adj=adj, hidden_dim=self.seq_len, output_dim=self.pre_len)

        self.model.load_state_dict(checkpoint["model_state"])
        self.model.to(self.device)
        self.model.eval()
        print(f"模型已加载: {self.model_name} (Epoch {checkpoint['epoch']})")
        print(f"  传感器: {self.num_nodes}, 输入: {self.seq_len}步, 预测: {self.pre_len}步")

    def _load_checkpoint(self, model_path):
        """兼容不同 numpy 版本的 checkpoint 反序列化。"""
        try:
            return torch.load(model_path, map_location=self.device, weights_only=False)
        except ModuleNotFoundError as e:
            if "numpy._core" not in str(e):
                raise
            import numpy.core as npcore
            # 某些 checkpoint 由新版本 numpy 序列化，旧版本环境需要模块别名兼容。
            sys.modules.setdefault("numpy._core", npcore)
            sys.modules.setdefault("numpy._core.multiarray", npcore.multiarray)
            return torch.load(model_path, map_location=self.device, weights_only=False)

    def predict(self, speed_data):
        """
        输入: speed_data, shape=(seq_len, num_nodes) 或 (num_nodes,)
              最近的 seq_len 个时间步的速度数据（原始值，非归一化）
        输出: predictions, shape=(pre_len, num_nodes)
              预测未来 pre_len 个时间步的速度（原始值）
        """
        if isinstance(speed_data, np.ndarray):
            speed_data = torch.FloatTensor(speed_data)

        if speed_data.dim() == 1:
            raise ValueError(f"需要至少 {self.seq_len} 个时间步的数据")

        if speed_data.shape[0] < self.seq_len:
            raise ValueError(f"输入数据时间步({speed_data.shape[0]}) < seq_len({self.seq_len})")

        # 取最近 seq_len 步
        recent = speed_data[-self.seq_len:].numpy()
        normalized = recent / self.max_val

        # (1, seq_len, num_nodes)
        x = torch.FloatTensor(normalized).unsqueeze(0).to(self.device)

        with torch.no_grad():
            pred = self.model(x)  # (1, num_nodes, pre_len)

        # (num_nodes, pre_len) -> (pre_len, num_nodes)
        pred = pred.cpu().numpy()[0].T * self.max_val
        return np.clip(pred, 0, None)

    def predict_from_file(self, speed_path):
        """从速度数据文件预测"""
        import pandas as pd
        data = np.array(pd.read_csv(speed_path), dtype=np.float32)
        if data.shape[0] < self.seq_len:
            raise ValueError(f"数据时间步({data.shape[0]}) < seq_len({self.seq_len})")
        predictions = self.predict(data)
        return predictions

    def predict_single_step(self, speed_data):
        """单步预测：预测下一个时间步"""
        pred = self.predict(speed_data)
        return pred[0] if pred.ndim > 1 else pred

    @property
    def adj(self):
        return self._checkpoint.get("adj")

    @property
    def hidden_dim(self):
        return self._checkpoint.get("hidden_dim")


def main():
    parser = argparse.ArgumentParser(description="T-GCN 交通预测")
    parser.add_argument("--model_path", type=str, default="saved_models/TGCN_best.pth")
    parser.add_argument("--speed_path", type=str, default="data/d12_speed.csv")
    parser.add_argument("--output_path", type=str, default=None)
    args = parser.parse_args()

    predictor = TGCNPredictor(args.model_path)

    print(f"\n从文件加载速度数据: {args.speed_path}")
    predictions = predictor.predict_from_file(args.speed_path)

    print(f"\n预测结果 (未来 {predictor.pre_len} 步):")
    for t in range(predictor.pre_len):
        step_pred = predictions[t] if predictions.ndim > 1 else predictions
        print(f"  步骤 {t+1}: 均值={step_pred.mean():.2f}, "
              f"范围=[{step_pred.min():.2f}, {step_pred.max():.2f}]")

    if args.output_path:
        np.save(args.output_path, predictions)
        print(f"\n预测结果已保存: {args.output_path}")


if __name__ == "__main__":
    main()
