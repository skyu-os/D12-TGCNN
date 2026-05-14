# 📊 OSMnx支持的路网数据格式

## ✅ 推荐格式(可以直接使用)

### 1. **OSM XML格式** (.osm 或 .xml) ⭐推荐

**优点**:
- OSMnx原生支持
- 文本格式,可读性好
- 容易获取和转换
- 兼容性最好

**如何获取**:
```bash
# 方法1: 从OSM官网下载
# 访问 https://download.geofabrik.de/
# 下载 north-america/us/california.osm.bz2
# 解压后得到 .osm 文件

# 方法2: 使用osmium转换PBF
osmium cat input.osm.pbf -o output.osm.xml

# 方法3: 使用OsmiumTool
osmium convert input.osm.pbf -o output.osm.xml
```

**使用方法**:
```python
import osmnx as ox

# 直接读取
G = ox.graph_from_xml("path/to/file.osm", simplify=True)
```

---

### 2. **在线下载** (最简单) ⭐⭐推荐

**优点**:
- 无需手动下载
- 自动获取最新数据
- OSMnx内置功能
- 支持多种筛选条件

**使用方法**:
```python
import osmnx as ox

# 按地点名称下载
G = ox.graph_from_place("Orange County, California, USA", network_type="drive")

# 按中心点和半径下载
G = ox.graph_from_point((33.7175, -117.8311), dist=10000, network_type="drive")

# 按边界框下载(当前使用的方法)
G = ox.graph_from_bbox(
    bbox=(-118.10, 33.38, -117.41, 33.95),  # west, south, east, north
    network_type="drive"
)
```

**前提条件**:
- 需要互联网连接
- 无代理限制

---

### 3. **GraphML格式** (.graphml)

**优点**:
- OSMnx可以读取
- 通用图格式
- 可以保存和加载

**使用方法**:
```python
import osmnx as ox

# 读取GraphML
G = ox.load_graphml("path/to/file.graphml")
```

**如何获取**:
```python
# 从其他格式转换后保存
G = ox.graph_from_xml("input.osm")
ox.save_graphml(G, "output.graphml")
```

---

## ❌ 不推荐格式(需要额外处理)

### 1. **PBF格式** (.osm.pbf) ❌

**问题**:
- 二进制压缩格式
- OSMnx无法直接读取
- 需要额外工具转换

**解决方法**:
```bash
# 需要先转换为XML
pip install osmium
osmium cat input.osm.pbf -o output.osm.xml
```

---

### 2. **其他格式**

- **Shapefile (.shp)**: 需要额外处理
- **GeoJSON (.geojson)**: 不适合路网图
- **PostgreSQL数据库**: 需要额外配置

---

## 🎯 最佳实践推荐

### 方案A: 在线下载(推荐) ⭐⭐⭐

**如果有网络连接,这是最简单的方法**:

```python
# backend/graph/road_graph.py
import osmnx as ox

# 直接下载Orange County的路网
G = ox.graph_from_place(
    "Orange County, California, USA",
    network_type="drive",
    simplify=True
)

# 或者使用bbox
G = ox.graph_from_bbox(
    bbox=(-118.10, 33.38, -117.41, 33.95),
    network_type="drive"
)
```

**优点**:
- 无需手动下载
- 代码简单
- 自动获取最新数据

---

### 方案B: 预下载OSM XML文件

**如果需要离线使用**:

#### 步骤1: 下载OSM数据

**方法1 - 从Geofabrik下载**:
```
访问: https://download.geofabrik.de/north-america.html
下载: california-latest.osm.bz2 (约1GB)
解压: california.osm
```

**方法2 - 使用BBBike下载**:
```
访问: https://extract.bbbike.org/
选择区域: Orange County, CA
格式: OSM XML (.osm)
下载: 约50-100MB
```

#### 步骤2: 放置文件

```bash
# 将下载的 .osm 文件放到:
D:\D12_TGCN_Planning\data\osm\orange_county.osm
```

#### 步骤3: 修改代码使用本地文件

```python
# backend/graph/road_graph.py
import osmnx as ox

LOCAL_OSM_PATH = os.path.join(DATA_DIR, "osm", "orange_county.osm")

# 读取本地OSM文件
G = ox.graph_from_xml(LOCAL_OSM_PATH, simplify=True)

# 过滤机动车道
# ... 后续处理
```

---

### 方案C: 转换PBF为XML

**如果已经有PBF文件**:

#### 安装工具

**Windows**:
```bash
pip install osmium
# 或下载 osmium-tool
```

**Linux/Mac**:
```bash
sudo apt-get install osmium-tool  # Ubuntu/Debian
brew install osmium  # Mac
```

#### 转换命令

```bash
# 基本转换
osmium cat input.osm.pbf -o output.osm.xml

# 只保留特定区域
osmium cat input.osm.pbf -b -118.1,33.38,-117.41,33.95 -o output.osm.xml

# 只保留机动车道
osmium cat input.osm.pbf -o output.osm.xml \
  --overwrite \
  --set "oneway=yes@highway=motorway,trunk,primary,secondary,tertiary,unclassified,residential"
```

---

## 📊 格式对比

| 格式 | 文件大小 | 读取速度 | 兼容性 | 推荐度 |
|------|---------|---------|--------|--------|
| 在线下载 | N/A | 慢 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| OSM XML | 大 | 快 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| GraphML | 中 | 快 | ⭐⭐⭐⭐ | ⭐⭐ |
| PBF | 小 | 需转换 | ⭐⭐ | ⭐ |

---

## 💡 当前项目建议

### 短期方案(当前)
- ✅ 使用生成的测试路网(225节点)
- ✅ 功能完整可用
- ✅ 适合演示和开发

### 长期方案(生产环境)
1. **推荐**: 在有网络环境运行首次启动,自动下载真实OSM数据
2. **备选**: 下载Orange County的.osm文件,放到data/osm/目录
3. **转换**: 如果已有PBF,使用osmium工具转换为XML

---

## 🔧 快速测试命令

```bash
# 测试在线下载(需要网络)
python -c "import osmnx as ox; G = ox.graph_from_place('Orange County, California', network_type='drive'); print(f'节点: {G.number_of_nodes()}, 边: {G.number_of_edges()}')"

# 测试本地XML文件
python -c "import osmnx as ox; G = ox.graph_from_xml('data/osm/orange_county.osm'); print(f'节点: {G.number_of_nodes()}, 边: {G.number_of_edges()}')"
```

---

**总结**: 
- **在线下载**: 最简单,推荐用于首次运行
- **OSM XML**: 最通用,推荐用于离线部署
- **PBF**: 需要转换,不推荐直接使用
