# 基于TGCN交通预测的智能路径规划系统

> 集成时空图卷积网络(TGCN)的实时交通预测与多算法路径规划系统

## 项目简介

本项目基于加州PeMS D12区域交通数据，将**时空图卷积网络(TGCN)**应用于交通预测，结合多种路径规划算法，提供实时交通状态下的最优路径推荐与多方案对比。

### 核心特性

- **智能路径规划** — A*、ALT(地标三角)、Dijkstra、贪心四种算法，支持距离/时间双目标
- **时变动态路由** — TGCN预测 + 时变A*，融合路口约束与交通信号延迟
- **多目标优化** — 时间/距离/能耗/碳排放/舒适度/综合最优六维对比
- **TGCN交通预测** — 时空图卷积网络，5分钟粒度，覆盖2,587个传感器
- **路段级交通可视化** — 15,000+路段实时速度与拥堵等级，含路况热力图
- **API响应缓存** — 30秒TTL SimpleCache，重复请求5x加速
- **数据驱动** — PeMS真实传感器数据 + OSM路网 + 用地性质速度先验

## 项目结构

```
D12_TGCN_Planning/
├── backend/
│   ├── app.py                              # Flask应用入口，线程池预热
│   ├── api/
│   │   ├── routes.py                       # 11个REST API端点
│   │   └── cache.py                        # API响应缓存 (SimpleCache, 30s TTL)
│   ├── graph/
│   │   ├── road_graph.py                   # OSM路网图 (312,869节点, 776,851边)
│   │   ├── osm_parser.py                   # OSM数据解析
│   │   └── sensor_parser.py                # PeMS传感器站点解析
│   ├── routing/
│   │   ├── astar.py                        # A*算法 (Haversine启发式)
│   │   ├── alt.py                          # ALT算法 (地标三角启发式, ~20%加速)
│   │   ├── dijkstra.py                     # Dijkstra算法
│   │   ├── greedy.py                       # 贪心搜索
│   │   ├── time_dependent_astar.py         # 时变A* (TGCN动态边权)
│   │   ├── dynamic_edge_weight.py          # 动态边权管理 (含缓存)
│   │   ├── enhanced_astar.py               # 多目标A* (能耗/碳排放/舒适度)
│   │   ├── enhanced_router.py              # 增强路由服务 (多目标+路口约束)
│   │   ├── router.py                       # 基础路由服务 (单例)
│   │   ├── dynamic_router_service.py       # 动态路由服务
│   │   ├── multi_objective_optimizer.py    # 多目标优化器
│   │   ├── intersection_constraints.py     # 路口约束分析 (信号/转弯代价)
│   │   ├── sensor_road_mapper.py           # 传感器-路网映射
│   │   └── apn_sensor_interpolator.py      # APN自适应传感器插值
│   └── prediction/
│       ├── traffic_prediction_service.py   # TGCN预测服务 (单例+文件缓存)
│       ├── segment_traffic_service.py      # 路段级交通预测 (15K+路段)
│       ├── simple_segment_service.py       # 简化路段预测
│       ├── predictive_routing_service.py   # 预测驱动的路径重规划
│       └── variance_restorer.py            # 预测方差还原
├── frontend/
│   ├── index.html                          # 主页面 (地图+路径规划+交通热力)
│   ├── compare.html                        # 多方案对比页面 (6目标x4算法)
│   ├── css/
│   │   ├── style.css                       # 主样式
│   │   └── segment-traffic.css             # 路段交通可视化样式
│   └── js/
│       ├── map.js                          # 地图交互 (Leaflet)
│       ├── route.js                        # 路径规划请求
│       ├── prediction.js                   # 交通预测面板
│       ├── compare.js                      # 多方案对比逻辑
│       ├── compare-map.js                  # 对比地图渲染
│       └── segment-traffic.js              # 路段交通图层
├── TGCN/
│   ├── tgcn_pytorch/                       # T-GCN PyTorch实现
│   │   ├── models/                         # TGCN模型架构
│   │   ├── utils/                          # 数据处理工具
│   │   └── train.py                        # 训练脚本
│   └── data/                               # 邻接矩阵、速度数据
├── data/
│   ├── osm/                                # OSM原始数据 (D12区域)
│   └── processed/                          # 预处理数据
│       ├── road_graph.pkl                  # 路网图缓存
│       ├── edge_sensor_map.pkl             # 边-传感器映射
│       ├── road_speed_prior.pkl            # 用地性质速度先验
│       ├── landuse_polygons.pkl            # 65,023个用地多边形
│       └── edge_landuse_map.pkl            # 边-用地映射 (48.5%覆盖率)
├── docs/                                   # 算法文档与论文图表
├── 说明/                                   # 中文项目说明文档
├── requirements.txt                        # Python依赖
└── README.md                               # 项目说明
```

## 技术栈

### 后端
- **框架**: Python 3.8+, Flask 2.0+, Flask-CORS, Flask-Caching
- **图处理**: OSMnx, NetworkX
- **路径规划**: A*, ALT (Landmark Triangulation), Dijkstra, Greedy, 时变A*
- **交通预测**: T-GCN时空图卷积网络 (PyTorch)
- **数据科学**: NumPy, Pandas, SciPy, GeoPandas, scikit-learn

### 前端
- **核心**: HTML5, CSS3, JavaScript ES6+
- **地图**: Leaflet.js + OpenStreetMap
- **可视化**: 交通热力图、路段拥堵着色、多路径对比

### 数据源
- **交通数据**: PeMS D12 实时传感器 (2,587个站点)
- **路网数据**: OpenStreetMap (D12区域, 57,200km总长)
- **用地数据**: OSM landuse polygons (65,023个, 7类)

## 快速开始

### 环境要求
- Python 3.8+
- 现代浏览器 (Chrome, Firefox, Edge)

### 安装步骤

```bash
# 1. 安装后端依赖
pip install -r requirements.txt

# 2. 安装TGCN依赖
cd TGCN/tgcn_pytorch && pip install -r requirements.txt && cd ../..

# 3. 启动服务
python backend/app.py

# 4. 访问
# 主页面: http://localhost:5000
# 多方案对比: http://localhost:5000/compare.html
```

启动时服务器自动：加载路网图 (312,869节点)、后台预热TGCN模型、初始化API缓存。

## API文档

### 路径规划

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/route` | POST | 基础路径规划 (A*/ALT/Dijkstra/Greedy) **[30s缓存]** |
| `/api/enhanced-route` | POST | 多目标+路口约束路径规划 |
| `/api/route/dynamic` | POST | 时变动态路由 (TGCN预测驱动) |
| `/api/routes/compare` | POST | 六目标全方案对比 |
| `/api/traffic/predictive-route` | POST | 预测拥堵驱动的路径重规划 **[30s缓存]** |
| `/api/traffic/route-overlay` | POST | 已规划路线叠加交通预测 |

### 交通数据

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/traffic/predict` | GET/POST | TGCN传感器级交通预测 |
| `/api/traffic/segments` | GET/POST | 路段级交通预测 (15K+路段+拥堵等级) |
| `/api/traffic/hotspots` | GET | 拥堵热点Top-K查询 |

### 系统信息

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/graph/stats` | GET | 路网统计 (节点/边/总长度) |
| `/api/sensors` | GET | 传感器站点列表 (可按高速过滤) |

### 路径规划请求示例

```json
POST /api/route
{
  "start_lat": 33.7175,  "start_lon": -117.8311,
  "end_lat": 33.6470,    "end_lon": -117.7441,
  "weight_type": "time",
  "algorithm": "astar"
}

POST /api/enhanced-route
{
  "start_lat": 33.7175,  "start_lon": -117.8311,
  "end_lat": 33.6470,    "end_lon": -117.7441,
  "objective": "balanced",
  "mode": "full",
  "vehicle_type": "gasoline",
  "hour": 12
}

POST /api/routes/compare
{
  "start_lat": 33.669,   "start_lon": -117.823,
  "end_lat": 33.745,     "end_lon": -117.867,
  "mode": "full",
  "vehicle_type": "gasoline",
  "hour": 12
}
```

### 响应示例

```json
{
  "success": true,
  "route": {
    "path": [3696094958, 122819041, ...],
    "coords": [[33.7176, -117.8314], ...],
    "distance_km": 19.07,
    "time_min": 18.9,
    "energy_mj": 15.23,
    "carbon_kg": 4.79,
    "avg_comfort": 0.75,
    "turn_penalties_s": 25.0,
    "total_constraint_s": 85.0
  }
}
```

## 算法性能

| 算法 | 平均耗时 | 启发式 | 适用场景 |
|---|---|---|---|
| ALT (地标三角) | ~241ms | Landmark + Haversine | 中长距离最优路径 |
| A* | ~303ms | Haversine | 通用路径规划 |
| Dijkstra | ~500ms+ | 无 | 最短路径保证 |
| Greedy | ~50ms | 仅Haversine | 快速近似解 |

> P2 API缓存开启后，30秒内相同请求命中缓存返回 ~140ms (5x加速)。

## 配置

创建 `.env` 文件：

```bash
FLASK_ENV=development
FLASK_PORT=5000
REGION_NAME=Orange County
BBOX_NORTH=33.95
BBOX_SOUTH=33.38
BBOX_EAST=-117.41
BBOX_WEST=-118.10
```

## 相关资源

- [TGCN原论文](https://arxiv.org/abs/1907.07489)
- [PeMS数据库](http://pems.dot.ca.gov/)
- [OSMnx文档](https://osmnx.readthedocs.io/)
- [Leaflet文档](https://leafletjs.com/)

---

**状态**: 活跃开发 | **版本**: 2.0.0 | **更新**: 2026-05-13
