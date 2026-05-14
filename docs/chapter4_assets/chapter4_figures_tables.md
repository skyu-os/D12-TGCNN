# 第四章图表补充素材

## 图4-1 T-GCN 模型结构示意图

```mermaid
flowchart LR
    A[历史速度序列<br/>12 个时间步] --> B[路网邻接矩阵<br/>空间拓扑关系]
    A --> C[图卷积层 GCN<br/>提取空间相关特征]
    B --> C
    C --> D[GRU 时间递归单元<br/>捕获时间依赖]
    D --> E[全连接输出层]
    E --> F[多步速度预测<br/>5 / 10 / 15 min]
    F --> G[方差恢复]
    G --> H[IDW 空间扩展]
    H --> I[路径规划动态边权]
```


## 图4-2 模型训练与验证损失曲线

文件：`fig4-2_loss_curve.png`，数据来源：`TGCN/result/TGCN_history.json`。


## 图4-3 RMSE、MAE、MAPE 随训练轮数变化曲线

文件：`fig4-3_metrics_curve.png`，数据来源：`TGCN/result/TGCN_history.json`。


## 表4-1 T-GCN 推荐配置参数表

| 参数 | 取值 | 说明 |
| --- | --- | --- |
| top_n | 200 | 核心 detector 数量 |
| days | 14 | 训练数据天数 |
| val_days | 7 | 验证数据天数 |
| threshold | 3.0 | 邻接矩阵距离阈值（km） |
| start_date | 2026_01_01 | 训练数据起始日期 |
| model | TGCN | 模型类型 |
| hidden_dim | 64 | 隐藏层维度 |
| seq_len | 12 | 输入序列长度 |
| pre_len | 3 | 预测步长 |
| epochs | 100 | 训练轮数 |
| batch_size | 32 | 批大小 |
| lr | 0.001 | 学习率 |
| weight_decay | 0.0015 | L2 正则化系数 |
| use_regularization | True | 是否启用正则化 |


## 表4-2 T-GCN 最终预测性能结果表

| 指标 | 取值 | 单位 |
| --- | --- | --- |
| RMSE | 6.761811 | km/h |
| MAE | 5.046261 | km/h |
| MAPE | 9.158084 | % |
| R² | 0.106939 | - |
| Accuracy | 0.896072 | - |
| loss | 0.005351 | - |
| 训练时间 | 1725.354 | s |
| 训练时间 | 28.756 | min |
| 训练轮数 | 100 | epoch |
| 隐藏层维度 | 64 | 维 |


## 图4-4 在线预测速度分布图

文件：`fig4-4_online_speed_distribution.png`，数据来源：`TGCN/result/online_prediction_step1.json`。


## 表4-3 第 1 步在线预测统计结果表

| 统计项 | 取值 | 单位 |
| --- | --- | --- |
| 模型 | TGCN+IDW | - |
| 预测步长 | 1 | step |
| 预测时长 | 5 | min |
| 直接预测节点数 | 200 | 个 |
| 扩展后 detector 总数 | 2587 | 个 |
| 插值扩展 detector 数 | 2387 | 个 |
| 平均速度 | 57.316 | km/h |
| 最小速度 | 21.902 | km/h |
| 最大速度 | 79.086 | km/h |
| 10% 分位速度 | 51.732 | km/h |
| 25% 分位速度 | 54.092 | km/h |
| 50% 分位速度 | 57.380 | km/h |
| 75% 分位速度 | 60.543 | km/h |
| 90% 分位速度 | 64.405 | km/h |
| 低速阈值 | 50.0 | km/h |
| 低速 detector 数 | 171 | 个 |
| 低速 detector 占比 | 0.0661 | - |
| 模型推理耗时 | 7.58 | ms |
| 空间扩展耗时 | 33.37 | ms |

