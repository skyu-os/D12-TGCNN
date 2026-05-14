import torch
import torch.nn as nn
from utils.graph_conv import calculate_laplacian_with_self_loop


class GCN(nn.Module):
    def __init__(self, adj, hidden_dim: int, output_dim: int = 1):
        super().__init__()
        self._num_nodes = adj.shape[0]
        self.register_buffer(
            "laplacian", calculate_laplacian_with_self_loop(torch.FloatTensor(adj))
        )
        self.weights = nn.Parameter(
            torch.FloatTensor(hidden_dim, hidden_dim)
        )
        self.regressor = nn.Linear(hidden_dim, output_dim)
        self.reset_parameters()

    def reset_parameters(self):
        nn.init.xavier_uniform_(self.weights, gain=nn.init.calculate_gain("tanh"))

    def forward(self, inputs):
        batch_size, seq_len, num_nodes = inputs.shape
        inputs = inputs.transpose(0, 2).transpose(1, 2)
        inputs = inputs.reshape((num_nodes, batch_size * seq_len))
        ax = self.laplacian @ inputs
        ax = ax.reshape((num_nodes, batch_size, seq_len))
        ax = ax.reshape((num_nodes * batch_size, seq_len))
        outputs = torch.tanh(ax @ self.weights)
        outputs = outputs.reshape((num_nodes, batch_size, -1))
        outputs = outputs.transpose(0, 1)
        predictions = self.regressor(outputs)
        return predictions
