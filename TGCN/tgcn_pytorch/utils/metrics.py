import torch
import numpy as np


def accuracy(pred, y):
    return 1 - torch.linalg.norm(y - pred, "fro") / torch.linalg.norm(y, "fro")


def r2_score(pred, y):
    return 1 - torch.sum((y - pred) ** 2) / torch.sum((y - torch.mean(pred)) ** 2)


def explained_variance(pred, y):
    return 1 - torch.var(y - pred) / torch.var(y)


def numpy_metrics(pred, y):
    pred, y = np.array(pred), np.array(y)
    rmse = np.sqrt(np.mean((pred - y) ** 2))
    mae = np.mean(np.abs(pred - y))
    mape = np.mean(np.abs(pred - y) / (y + 1e-8)) * 100
    r2 = 1 - np.sum((y - pred) ** 2) / np.sum((y - np.mean(y)) ** 2)
    acc = 1 - np.linalg.norm(y - pred) / np.linalg.norm(y)
    return {"RMSE": rmse, "MAE": mae, "MAPE": mape, "R2": r2, "Accuracy": acc}
