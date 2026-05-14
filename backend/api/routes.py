"""
REST API 路由
"""

from flask import Blueprint, jsonify, request

from backend.graph.sensor_parser import get_sensors_by_fwy, parse_sensors
from backend.prediction.predictive_routing_service import PredictiveRouteService
from backend.prediction.traffic_prediction_service import TrafficPredictionService
from backend.prediction.segment_traffic_service import SegmentTrafficService
from backend.routing.dynamic_router_service import DynamicRouterService
from backend.routing.enhanced_router import EnhancedRouterService
from backend.routing.router import RouterService
from backend.api.cache import cache, make_cache_key

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/route", methods=["POST"])
@cache.cached(timeout=30, make_cache_key=make_cache_key)
def find_route():
    """
    路径规划接口

    Request JSON:
    {
        "start_lat": 33.7175,
        "start_lon": -117.8311,
        "end_lat": 33.6470,
        "end_lon": -117.7441,
        "weight_type": "time",  // "time" | "distance"
        "algorithm": "astar"    // "astar" | "dijkstra" | "greedy"
    }

    Response JSON:
    {
        "success": true,
        "route": {
            "path": [node_ids],
            "coords": [[lat, lon], ...],
            "distance_m": 12345.6,
            "distance_km": 12.35,
            "time_s": 780.5,
            "time_min": 13.0
        }
    }
    """
    data = request.get_json()

    print(f"\n[DEBUG] 收到路径规划请求:")
    print(f"  原始数据: {data}")

    if not data:
        print("[ERROR] 请求体不能为空")
        return jsonify({"success": False, "error": "请求体不能为空"}), 400

    required = ["start_lat", "start_lon", "end_lat", "end_lon"]
    missing = [k for k in required if k not in data]
    if missing:
        print(f"[ERROR] 缺少参数: {missing}")
        return jsonify({"success": False, "error": f"缺少参数: {missing}"}), 400

    weight_type = data.get("weight_type", "time")
    if weight_type not in ("time", "distance"):
        print(f"[ERROR] weight_type错误: {weight_type}")
        return jsonify(
            {"success": False, "error": "weight_type 必须是 time 或 distance"}
        ), 400

    algorithm = data.get("algorithm", "astar")
    if algorithm not in ("astar", "dijkstra", "greedy", "alt"):
        print(f"[ERROR] algorithm错误: {algorithm}")
        return jsonify(
            {"success": False, "error": "algorithm 必须是 astar、dijkstra、greedy 或 alt"}
        ), 400

    print(f"[INFO] 路径规划参数:")
    print(f"  起点: ({data['start_lat']}, {data['start_lon']})")
    print(f"  终点: ({data['end_lat']}, {data['end_lon']})")
    print(f"  优化: {weight_type}")
    print(f"  算法: {algorithm}")

    service = RouterService.get_instance()

    try:
        result = service.find_route(
            start_lat=data["start_lat"],
            start_lon=data["start_lon"],
            end_lat=data["end_lat"],
            end_lon=data["end_lon"],
            weight_type=weight_type,
            algorithm=algorithm,
        )

        print(f"[DEBUG] 路径规划结果:")
        print(f"  success: {result['success']}")
        if result["success"]:
            route = result["route"]
            print(f"  节点数: {len(route['path'])}")
            print(f"  距离: {route['distance_km']:.2f} km")
            print(f"  时间: {route['time_min']:.1f} 分钟")

        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] 路径规划异常: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.route("/graph/stats", methods=["GET"])
def graph_stats():
    """获取路网统计信息"""
    service = RouterService.get_instance()
    stats = service._road_graph.get_stats()
    return jsonify({"success": True, "stats": stats})


@api_bp.route("/sensors", methods=["GET"])
def get_sensors():
    """
    获取 PeMS D12 传感器站点列表

    Query params:
      fwy: 可选，按高速公路编号过滤，如 ?fwy=405

    Response JSON:
    {
        "success": true,
        "sensors": [...],
        "count": 500
    }
    """
    fwy_filter = request.args.get("fwy", "").strip()

    if fwy_filter:
        groups = get_sensors_by_fwy()
        sensors = groups.get(fwy_filter, [])
    else:
        sensors = parse_sensors()

    return jsonify({"success": True, "sensors": sensors, "count": len(sensors)})


@api_bp.route("/traffic/predict", methods=["GET", "POST"])
def predict_traffic():
    """
    交通预测接口（TGCN）。

    GET Query 或 POST JSON 参数：
      step: 预测步长（1-based）
      top_k: 返回速度最低的前 K 个传感器

    Response JSON:
    {
        "success": true,
        "prediction": { ... }
    }
    """
    if request.method == "GET":
        payload = request.args
    else:
        payload = request.get_json(silent=True) or {}

    raw_step = payload.get("step", 1)
    raw_top_k = payload.get("top_k", 12)

    try:
        step = int(raw_step)
        top_k = int(raw_top_k)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "step/top_k 必须为整数"}), 400

    try:
        service = TrafficPredictionService.get_instance()
        prediction = service.predict(step=step, top_k=top_k)
        return jsonify({"success": True, "prediction": prediction})
    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        print(f"[ERROR] 交通预测异常: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/traffic/predictive-route", methods=["POST"])
@cache.cached(timeout=30, make_cache_key=make_cache_key)
def predictive_route():
    """
    预测拥堵驱动的路径重规划接口。

    Request JSON:
    {
        "start_lat": 33.7175,
        "start_lon": -117.8311,
        "end_lat": 33.6470,
        "end_lon": -117.7441,
        "step": 1,
        "weight_type": "time",
        "congestion_top_n": 350
    }
    """
    data = request.get_json(silent=True) or {}

    required = ["start_lat", "start_lon", "end_lat", "end_lon"]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"success": False, "error": f"缺少参数: {missing}"}), 400

    try:
        step = int(data.get("step", 1))
        congestion_top_n = int(data.get("congestion_top_n", 350))
    except (TypeError, ValueError):
        return jsonify(
            {"success": False, "error": "step/congestion_top_n 必须为整数"}
        ), 400

    weight_type = data.get("weight_type", "time")
    if weight_type not in ("time", "distance"):
        return jsonify(
            {"success": False, "error": "weight_type 必须是 time 或 distance"}
        ), 400

    try:
        service = PredictiveRouteService.get_instance()
        result = service.plan_route(
            start_lat=float(data["start_lat"]),
            start_lon=float(data["start_lon"]),
            end_lat=float(data["end_lat"]),
            end_lon=float(data["end_lon"]),
            step=step,
            weight_type=weight_type,
            congestion_top_n=congestion_top_n,
        )
        return jsonify({"success": True, **result})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        print(f"[ERROR] 预测重规划异常: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/enhanced-route", methods=["POST"])
def find_enhanced_route():
    """
    增强版路径规划接口 - 支持多目标优化和路口约束

    Request JSON:
    {
        "start_lat": 33.7175,
        "start_lon": -117.8311,
        "end_lat": 33.6470,
        "end_lon": -117.7441,
        "objective": "time",        // 优化目标: "time" | "distance" | "energy" | "carbon" | "comfort" | "balanced"
        "mode": "standard",          // 优化模式: "standard" | "multi_objective" | "with_constraints" | "full"
        "vehicle_type": "gasoline",  // 车辆类型: "gasoline" | "diesel" | "electric" | "hybrid"
        "hour": 12                   // 小时(0-23)，用于时段判断
    }

    Response JSON:
    {
        "success": true,
        "route": {
            "path": [node_ids],
            "coords": [[lat, lon], ...],
            "distance_m": 12345.6,
            "distance_km": 12.35,
            "time_s": 780.5,
            "time_min": 13.0,
            "objective": "balanced",
            "mode": "full",
            "energy_mj": 15.234,        // 多目标模式返回
            "carbon_kg": 4.789,          // 多目标模式返回
            "avg_comfort": 0.75,         // 多目标模式返回
            "turn_penalties_s": 25.0,    // 约束模式返回
            "signal_waits_s": 60.0,       // 约束模式返回
            "total_constraint_s": 85.0,   // 约束模式返回
            "turn_types": ["left", "right"],
            "intersection_types": ["signal", "unsignalized"]
        }
    }
    """
    data = request.get_json()

    print(f"\n[DEBUG] 收到增强版路径规划请求:")
    print(f"  原始数据: {data}")

    if not data:
        print("[ERROR] 请求体不能为空")
        return jsonify({"success": False, "error": "请求体不能为空"}), 400

    required = ["start_lat", "start_lon", "end_lat", "end_lon"]
    missing = [k for k in required if k not in data]
    if missing:
        print(f"[ERROR] 缺少参数: {missing}")
        return jsonify({"success": False, "error": f"缺少参数: {missing}"}), 400

    # 验证优化目标
    objective = data.get("objective", "time")
    valid_objectives = ["time", "distance", "energy", "carbon", "comfort", "balanced"]
    if objective not in valid_objectives:
        print(f"[ERROR] objective错误: {objective}")
        return jsonify(
            {
                "success": False,
                "error": f"objective 必须是 {', '.join(valid_objectives)}",
            }
        ), 400

    # 验证优化模式
    mode = data.get("mode", "standard")
    valid_modes = ["standard", "multi_objective", "with_constraints", "full"]
    if mode not in valid_modes:
        print(f"[ERROR] mode错误: {mode}")
        return jsonify(
            {"success": False, "error": f"mode 必须是 {', '.join(valid_modes)}"}
        ), 400

    # 验证车辆类型
    vehicle_type = data.get("vehicle_type", "gasoline")
    valid_vehicles = ["gasoline", "diesel", "electric", "hybrid"]
    if vehicle_type not in valid_vehicles:
        print(f"[ERROR] vehicle_type错误: {vehicle_type}")
        return jsonify(
            {
                "success": False,
                "error": f"vehicle_type 必须是 {', '.join(valid_vehicles)}",
            }
        ), 400

    # 验证小时
    hour = data.get("hour", 12)
    if not isinstance(hour, int) or hour < 0 or hour > 23:
        print(f"[ERROR] hour错误: {hour}")
        return jsonify({"success": False, "error": "hour 必须是 0-23 的整数"}), 400

    print(f"[INFO] 增强版路径规划参数:")
    print(f"  起点: ({data['start_lat']}, {data['start_lon']})")
    print(f"  终点: ({data['end_lat']}, {data['end_lon']})")
    print(f"  优化目标: {objective}")
    print(f"  优化模式: {mode}")
    print(f"  车辆类型: {vehicle_type}")
    print(f"  时段: {hour}时")

    service = EnhancedRouterService.get_instance()

    try:
        result = service.find_route(
            start_lat=data["start_lat"],
            start_lon=data["start_lon"],
            end_lat=data["end_lat"],
            end_lon=data["end_lon"],
            objective=objective,
            mode=mode,
            vehicle_type=vehicle_type,
            hour=hour,
        )

        print(f"[DEBUG] 增强版路径规划结果:")
        print(f"  success: {result['success']}")
        if result["success"]:
            route = result["route"]
            print(f"  节点数: {len(route['path'])}")
            print(f"  距离: {route['distance_km']:.2f} km")
            print(f"  时间: {route['time_min']:.1f} 分钟")
            if "energy_mj" in route:
                print(f"  能耗: {route['energy_mj']:.3f} MJ")
            if "carbon_kg" in route:
                print(f"  碳排放: {route['carbon_kg']:.3f} kg CO2")
            if "total_constraint_s" in route:
                print(f"  约束代价: {route['total_constraint_s']:.1f} 秒")

        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] 增强版路径规划异常: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.route("/route/dynamic", methods=["POST"])
def dynamic_route():
    """
    时变动态路径规划接口 — TGCN 预测 + 时变 A*

    Request JSON:
    {
        "start_lat": 33.7175,
        "start_lon": -117.8311,
        "end_lat": 33.6470,
        "end_lon": -117.7441,
        "departure_time": null,       // Unix 时间戳，null=当前时间
        "vehicle_type": "gasoline",   // gasoline | diesel | electric | hybrid
        "time_of_day": "normal"       // normal | morning_peak | evening_peak | night
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "请求体不能为空"}), 400

    required = ["start_lat", "start_lon", "end_lat", "end_lon"]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"success": False, "error": f"缺少参数: {missing}"}), 400

    departure_time = data.get("departure_time")
    if departure_time is not None:
        try:
            departure_time = int(departure_time)
        except (TypeError, ValueError):
            return jsonify(
                {"success": False, "error": "departure_time 必须为整数时间戳"}
            ), 400

    vehicle_type = data.get("vehicle_type", "gasoline")
    if vehicle_type not in ("gasoline", "diesel", "electric", "hybrid"):
        return jsonify({"success": False, "error": "vehicle_type 无效"}), 400

    time_of_day = data.get("time_of_day", "normal")
    if time_of_day not in ("normal", "morning_peak", "evening_peak", "night"):
        return jsonify({"success": False, "error": "time_of_day 无效"}), 400

    try:
        service = DynamicRouterService.get_instance()
        result = service.find_dynamic_route(
            start_lat=float(data["start_lat"]),
            start_lon=float(data["start_lon"]),
            end_lat=float(data["end_lat"]),
            end_lon=float(data["end_lon"]),
            departure_time=departure_time,
            vehicle_type=vehicle_type,
            time_of_day=time_of_day,
        )

        if not result["success"]:
            return jsonify(result), 400

        route = result["route"]
        print(
            f"[DEBUG] 动态路径: {route['distance_km']} km, {route['time_min']} min, "
            f"路口延迟 {route.get('total_intersection_delay_s', 0):.1f}s, "
            f"计算耗时 {result['compute_ms']:.0f}ms"
        )

        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] 动态路径规划异常: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/traffic/segments", methods=["GET", "POST"])
def segment_traffic():
    """
    路段级交通预测接口（TGCN + 传感器-路段映射）

    GET Query 或 POST JSON 参数：
      step: 预测步长（1-based）
      speed_threshold: 畅通速度阈值（km/h）

    Response JSON:
    {
        "success": true,
        "segments": [
            {
                "edge_key": [node1, node2],
                "coordinates": [[lat1, lon1], [lat2, lon2]],
                "speed": 45.5,
                "status": "缓行",
                "color": "#f59e0b",
                "weight": 5,
                "road_name": "I-405",
                "road_type": "motorway",
                "max_speed": 88,
                "length": 234.5
            },
            ...
        ],
        "stats": {
            "total_segments": 15234,
            "total_sensors": 2587,
            "coverage_ratio": 5.89,
            "avg_speed": 52.3,
            "min_speed": 12.5,
            "max_speed": 78.6,
            "congestion_counts": {
                "畅通": 8523,
                "缓行": 4212,
                "拥堵": 1899,
                "严重拥堵": 600
            },
            "congestion_ratio": 0.125
        },
        "legend": [
            {"status": "畅通", "color": "#34a853", "range": "> 60.0 km/h"},
            {"status": "缓行", "color": "#fbbc04", "range": "40-60 km/h"},
            {"status": "拥堵", "color": "#ea4335", "range": "20-40 km/h"},
            {"status": "严重拥堵", "color": "#dc2626", "range": "< 20 km/h"}
        ],
        "step": 1,
        "horizon_minutes": 5
    }
    """
    if request.method == "GET":
        payload = request.args
    else:
        payload = request.get_json(silent=True) or {}

    raw_step = payload.get("step", 1)
    raw_threshold = payload.get("speed_threshold", 60.0)

    try:
        step = int(raw_step)
        speed_threshold = float(raw_threshold)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "step必须为整数，speed_threshold必须为数字"}), 400

    try:
        # 添加请求时间戳日志
        import time
        request_time = time.time()
        print(f"[DEBUG] API请求 #{int(request_time % 10000)}: step={step}, threshold={speed_threshold}")

        # 每次都强制重新创建服务实例以确保动态变化
        SegmentTrafficService._instance = None
        service = SegmentTrafficService.get_instance()

        result = service.get_segment_predictions(step=step, speed_threshold=speed_threshold)

        # 添加详细的调试信息
        avg_speed = result.get('stats', {}).get('avg_speed', 0)
        print(f"[DEBUG] API响应 #{int(request_time % 10000)}: segments={len(result.get('segments', []))}, avg_speed={avg_speed:.2f}")

        # 添加时间戳到响应中，帮助前端验证数据是否更新
        result['timestamp'] = request_time
        result['request_id'] = int(request_time % 10000)

        return jsonify({"success": True, **result})
    except Exception as e:
        print(f"[ERROR] 路段级预测异常: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/traffic/hotspots", methods=["GET"])
def traffic_hotspots():
    """
    获取交通拥堵热点路段接口

    GET Query 参数：
      top_k: 返回前K个最拥堵的路段（默认10）

    Response JSON:
    {
        "success": true,
        "hotspots": [...],
        "count": 10
    }
    """
    raw_top_k = request.args.get("top_k", 10)

    try:
        top_k = int(raw_top_k)
        if top_k <= 0 or top_k > 50:
            top_k = 10  # 限制最大返回数量
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "top_k必须为正整数"}), 400

    try:
        service = SegmentTrafficService.get_instance(force_reload=False)
        hotspots = service.get_congestion_hotspots(top_k=top_k)
        return jsonify({"success": True, "hotspots": hotspots, "count": len(hotspots)})
    except Exception as e:
        print(f"[ERROR] 拥堵热点查询异常: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/routes/compare", methods=["POST"])
def compare_routes():
    """
    一次请求计算全部优化目标的路线，类似高德多方案对比。

    Request JSON:
    {
        "start_lat": 33.669, "start_lon": -117.823,
        "end_lat": 33.745, "end_lon": -117.867,
        "mode": "full",           // 优化模式
        "vehicle_type": "gasoline",
        "hour": 12
    }

    Response JSON:
    {
        "success": true,
        "routes": [
            { "objective": "time",     "label": "最快路线", ... },
            { "objective": "distance", "label": "最短路线", ... },
            ...
        ]
    }
    """
    data = request.get_json() or {}
    required = ["start_lat", "start_lon", "end_lat", "end_lon"]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"success": False, "error": f"缺少参数: {missing}"}), 400

    mode = "multi_objective"  # 纯多目标对比，确保各目标差异化
    vehicle_type = data.get("vehicle_type", "gasoline")
    hour = int(data.get("hour", 12))

    objectives = [
        ("time", "最快路线", "astar"),
        ("distance", "最短路线", "dijkstra"),
        ("energy", "最省能耗", "multi"),
        ("carbon", "最低排放", "multi"),
        ("comfort", "最舒适", "multi"),
        ("balanced", "综合最优", "multi"),
    ]

    try:
        std_service = RouterService.get_instance()
        enh_service = EnhancedRouterService.get_instance()
        routes = []
        for obj, label, algo in objectives:
            if algo == "multi":
                result = enh_service.find_route(
                    start_lat=data["start_lat"], start_lon=data["start_lon"],
                    end_lat=data["end_lat"], end_lon=data["end_lon"],
                    objective=obj, mode=mode,
                    vehicle_type=vehicle_type, hour=hour,
                )
            else:
                result = std_service.find_route(
                    start_lat=data["start_lat"], start_lon=data["start_lon"],
                    end_lat=data["end_lat"], end_lon=data["end_lon"],
                    weight_type=obj, algorithm=algo,
                )
            if result["success"]:
                route = result["route"]
                route["objective"] = obj
                route["label"] = label
                if "energy_mj" not in route:
                    route["energy_mj"] = 0
                    route["carbon_kg"] = 0
                    route["avg_comfort"] = 0
                    route["total_constraint_s"] = 0
                routes.append(route)

        if not routes:
            return jsonify({"success": False, "error": "所有目标均未找到可达路径"}), 404

        return jsonify({"success": True, "routes": routes, "count": len(routes)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/traffic/route-overlay", methods=["POST"])
def route_traffic_overlay():
    """
    对已规划的路线叠加交通预测——返回每段路的预测速度/拥堵等级/传感器覆盖状态。
    """
    import os
    import numpy as np
    import pickle

    data = request.get_json() or {}
    path = data.get("path")
    step = int(data.get("step", 2))

    if not path or len(path) < 2:
        return jsonify({"success": False, "error": "path 至少需要两个节点"}), 400

    try:
        pred_svc = TrafficPredictionService.get_instance()
        route_svc = PredictiveRouteService.get_instance()

        prediction = pred_svc.predict(step=step, top_k=200)
        sensor_ctx = route_svc._build_sensor_context(prediction)
        edge_speeds = {}

        # 加载预构建的边-传感器映射 + 道路速度先验
        edge_sensor_map = None
        road_prior = {}
        map_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "edge_sensor_map.pkl")
        prior_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "road_speed_prior.pkl")
        if os.path.exists(map_path):
            with open(map_path, "rb") as f:
                edge_sensor_map = pickle.load(f).get("edge_to_sensors", {})
        if os.path.exists(prior_path):
            with open(prior_path, "rb") as f:
                road_prior = pickle.load(f).get("osm_prior", {})

        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            try:
                if v not in route_svc._road_graph.G[u]:
                    continue
                for key in route_svc._road_graph.G[u][v]:
                    route_svc._interpolate_edge_speed(u, v, key, sensor_ctx, edge_speeds)
                    break
            except (KeyError, TypeError):
                continue

        speeds = np.array([v["speed_kmh"] for v in edge_speeds.values()])
        threshold = route_svc._get_congestion_threshold(speeds) if speeds.size > 0 else 50.0

        segments = []
        covered_edges = 0
        for (u, v, key), info in edge_speeds.items():
            spd = info["speed_kmh"]
            max_spd = float(route_svc._road_graph.get_edge_speed(u, v, key))
            # 读取道路类型（用于速度先验查找）
            try:
                e = route_svc._road_graph.G.edges[u, v, key]
                rt = e.get("highway", "primary")
                if isinstance(rt, list):
                    rt = rt[0]
            except (KeyError, IndexError):
                rt = "primary"

            # 传感器覆盖距离
            nearest_sensor_km = None
            if edge_sensor_map and (u, v, key) in edge_sensor_map:
                nearest = edge_sensor_map[(u, v, key)]
                nearest_sensor_km = round(nearest[0][1], 3) if nearest else None
                if nearest_sensor_km is not None and nearest_sensor_km <= 1.0:
                    covered_edges += 1

            # 无传感器覆盖时，用道路类型速度先验作为更准确的估计
            if not (nearest_sensor_km is not None and nearest_sensor_km <= 1.0):
                prior = road_prior.get(rt, {})
                if prior:
                    spd = prior.get("mean", spd)

            segments.append({
                "u": u, "v": v,
                "speed_kmh": round(spd, 2),
                "max_speed_kmh": round(max_spd, 2),
                "congestion": "congested" if spd < threshold else "smooth",
                "nearest_sensor_km": nearest_sensor_km,
                "covered": nearest_sensor_km is not None and nearest_sensor_km <= 1.0,
                "road_type": rt,
                "coords": route_svc._road_graph.get_edge_coords(u, v, key),
            })

        total = len(segments)
        congested = sum(1 for s in segments if s["congestion"] == "congested")
        return jsonify({
            "success": True,
            "segments": segments,
            "summary": {
                "total_segments": total,
                "avg_speed_kmh": round(float(speeds.mean()), 2) if speeds.size > 0 else 0,
                "congested_segments": congested,
                "congested_pct": round(congested / max(total, 1) * 100, 1),
                "threshold_kmh": round(float(threshold), 2),
                "covered_segments": covered_edges,
                "covered_pct": round(covered_edges / max(total, 1) * 100, 1),
                "has_edge_map": edge_sensor_map is not None,
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
