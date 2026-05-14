import os
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader


class TrafficDataset(Dataset):
    def __init__(self, data, seq_len, pre_len):
        self.data = data
        self.seq_len = seq_len
        self.pre_len = pre_len
        self.samples = []
        for i in range(len(data) - seq_len - pre_len):
            x = data[i : i + seq_len]
            y = data[i + seq_len : i + seq_len + pre_len]
            self.samples.append((x, y))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        x, y = self.samples[idx]
        # x: (seq_len, nodes), y: (pre_len, nodes) -> (nodes, pre_len)
        return torch.FloatTensor(x), torch.FloatTensor(y).transpose(0, 1)


def load_speed_data(speed_path):
    df = pd.read_csv(speed_path)
    data = np.array(df, dtype=np.float32)
    return data


def load_adjacency_matrix(adj_path):
    df = pd.read_csv(adj_path, header=None)
    adj = np.array(df, dtype=np.float32)
    return adj


def normalize_data(data):
    max_val = np.max(data)
    return data / max_val, max_val


def create_dataloaders(data, seq_len, pre_len, batch_size, split_ratio=0.8):
    normalized_data, max_val = normalize_data(data)
    train_size = int(len(normalized_data) * split_ratio)
    train_data = normalized_data[:train_size]
    test_data = normalized_data[train_size:]
    train_dataset = TrafficDataset(train_data, seq_len, pre_len)
    test_dataset = TrafficDataset(test_data, seq_len, pre_len)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=len(test_dataset), shuffle=False)
    return train_loader, test_loader, max_val
