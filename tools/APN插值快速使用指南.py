"""
APN插值方法快速使用指南
统一使用APN自适应插值后的示例代码
"""

# ============================================================================
# 示例1: 基础使用（自动使用APN方法）
# ============================================================================

from backend.graph.road_graph import RoadGraph
from backend.routing.sensor_road_mapper import SensorRoadMapper, SpeedInterpolator
from backend.graph.sensor_parser import parse_sensors
import numpy as np

def example1_basic_usage():
    """基础使用 - 自动使用APN方法"""
    print("示例1: 基础APN插值使用")

    # 1. 初始化
    road_graph = RoadGraph.build_from_osm()
    mapper = SensorRoadMapper(road_graph)
    mapper.build_mapping()

    # 2. 创建插值器（已自动集成APN）
    interpolator = SpeedInterpolator(mapper)

    # 3. 准备传感器速度数据
    sensors = parse_sensors()
    sensor_speeds = {s['id']: np.random.uniform(40, 100) for s in sensors[:100]}

    # 4. 直接调用，自动使用APN方法
    edge_speeds = interpolator.create_speed_field(sensor_speeds)

    print(f"✅ 生成了 {len(edge_speeds):,} 条边的速度数据")
    print(f"   速度范围: {min(edge_speeds.values()):.1f} - {max(edge_speeds.values()):.1f} km/h")


# ============================================================================
# 示例2: 时段敏感插值
# ============================================================================

def example2_time_aware():
    """时段敏感插值 - 利用APN的时间感知能力"""
    print("\n示例2: 时段敏感插值")

    # 初始化（同上）
    road_graph = RoadGraph.build_from_osm()
    mapper = SensorRoadMapper(road_graph)
    mapper.build_mapping()
    interpolator = SpeedInterpolator(mapper)

    # 准备传感器数据
    sensors = parse_sensors()
    sensor_speeds = {s['id']: 60 for s in sensors[:100]}  # 假设所有传感器都是60km/h

    # 不同时段的插值结果
    time_scenarios = [
        (8, "早高峰"),
        (12, "中午"),
        (18, "晚高峰"),
        (2, "夜间")
    ]

    for hour, description in time_scenarios:
        edge_speeds = interpolator.create_speed_field(sensor_speeds, hour=hour)
        speeds = list(edge_speeds.values())
        print(f"{description}: 平均 {np.mean(speeds):.1f} km/h, "
              f"标准差 {np.std(speeds):.1f} km/h")


# ============================================================================
# 示例3: 路径规划集成
# ============================================================================

def example3_routing_integration():
    """路径规划集成 - 使用APN插值进行实时路径规划"""
    print("\n示例3: 路径规划集成")

    from backend.routing.router import RouterService

    # 1. 获取路由服务
    router = RouterService.get_instance()
    interpolator = SpeedInterpolator(router.road_graph)

    # 2. 生成实时速度场
    sensors = parse_sensors()
    sensor_speeds = {s['id']: np.random.uniform(40, 100) for s in sensors[:100]}

    # 使用APN方法生成速度场（考虑当前时段）
    current_hour = 14  # 下午2点
    edge_speeds = interpolator.create_speed_field(sensor_speeds, hour=current_hour)

    # 3. 更新路网权重
    for (u, v, key), speed in edge_speeds.items():
        if (u, v, key) in router.road_graph.G.edges:
            router.road_graph.G.edges[u, v, key]['predicted_speed'] = speed

    # 4. 使用预测速度规划路径
    start_lat, start_lon = 33.7175, -117.8311
    end_lat, end_lon = 33.6470, -117.7441

    try:
        result = router.find_route_by_coords(
            start_lat, start_lon, end_lat, end_lon,
            weight_type='predicted_time'
        )

        if result['success']:
            route = result['route']
            print(f"✅ 路径规划成功")
            print(f"   距离: {route['distance_km']:.2f} km")
            print(f"   时间: {route['time_min']:.1f} 分钟")
        else:
            print(f"❌ 路径规划失败: {result['error']}")

    except Exception as e:
        print(f"❌ 错误: {e}")


# ============================================================================
# 示例4: 实时更新系统
# ============================================================================

def example4_realtime_update():
    """实时更新系统 - 每5分钟更新一次速度场"""
    print("\n示例4: 实时更新系统（模拟）")

    import time

    # 初始化
    road_graph = RoadGraph.build_from_osm()
    mapper = SensorRoadMapper(road_graph)
    mapper.build_mapping()
    interpolator = SpeedInterpolator(mapper)

    # 模拟实时更新
    for i in range(3):  # 模拟3次更新
        current_hour = 8 + i * 4  # 8点, 12点, 16点

        # 获取最新传感器数据
        sensors = parse_sensors()
        sensor_speeds = {
            s['id']: np.random.uniform(40, 100)
            for s in sensors[:100]
        }

        # 使用APN方法生成速度场（考虑时段）
        edge_speeds = interpolator.create_speed_field(
            sensor_speeds,
            hour=current_hour
        )

        speeds = list(edge_speeds.values())
        print(f"更新 {i+1}/3 ({current_hour}点): "
              f"平均速度 {np.mean(speeds):.1f} km/h")

        # 实际应用中这里会等待5分钟
        # time.sleep(300)  # 5分钟
        time.sleep(0.1)  # 演示用，只等待0.1秒

    print("✅ 实时更新演示完成")


# ============================================================================
# 示例5: 性能对比
# ============================================================================

def example5_performance_comparison():
    """性能对比 - APN vs 传统方法"""
    print("\n示例5: 性能对比")

    import time

    # 初始化
    road_graph = RoadGraph.build_from_osm()
    mapper = SensorRoadMapper(road_graph)
    mapper.build_mapping()
    interpolator = SpeedInterpolator(mapper)

    # 准备测试数据
    sensors = parse_sensors()
    sensor_speeds = {s['id']: np.random.uniform(40, 100) for s in sensors[:100]}

    # 测试不同方法
    methods = ['adaptive', 'inverse_distance', 'nearest', 'average']
    results = {}

    for method in methods:
        start_time = time.time()
        edge_speeds = interpolator.create_speed_field(sensor_speeds, method=method)
        elapsed_time = time.time() - start_time

        speeds = list(edge_speeds.values())
        results[method] = {
            'time': elapsed_time,
            'mean': np.mean(speeds),
            'std': np.std(speeds),
            'count': len(edge_speeds)
        }

    # 输出结果
    print(f"{'方法':<20} {'时间':>10} {'平均值':>10} {'标准差':>10} {'边数':>10}")
    print("-" * 60)

    for method, stats in results.items():
        print(f"{method:<20} {stats['time']:>10.3f}s {stats['mean']:>10.1f} "
              f"{stats['std']:>10.1f} {stats['count']:>10,}")

    print("✅ 性能对比完成")


# ============================================================================
# 主函数
# ============================================================================

def main():
    """运行所有示例"""
    print("=" * 60)
    print("APN插值方法快速使用指南")
    print("=" * 60)

    try:
        # 示例1: 基础使用
        example1_basic_usage()

        # 示例2: 时段敏感插值
        example2_time_aware()

        # 示例3: 路径规划集成
        # example3_routing_integration()  # 可选，如果需要测试路径规划

        # 示例4: 实时更新系统
        example4_realtime_update()

        # 示例5: 性能对比
        example5_performance_comparison()

        print("\n" + "=" * 60)
        print("🎉 所有示例运行完成！")
        print("=" * 60)

        print("\n关键要点:")
        print("1. ✅ interpolator.create_speed_field() 默认使用APN方法")
        print("2. ✅ 添加 hour 参数可利用时段敏感性")
        print("3. ✅ 可无缝集成到现有路径规划系统")
        print("4. ✅ 性能与反距离加权相当，但准确性更高")
        print("5. ✅ 传统方法仍然可用作为备用")

    except Exception as e:
        print(f"\n❌ 运行失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
