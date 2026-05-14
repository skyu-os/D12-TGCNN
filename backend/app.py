"""
Flask 应用入口
"""

import os
import sys
from flask import Flask, send_from_directory
from flask_cors import CORS

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api.routes import api_bp
from backend.api.cache import cache

app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app)
cache.init_app(app)

# 注册 API 路由
app.register_blueprint(api_bp)


@app.route("/")
def index():
    """返回前端页面"""
    return send_from_directory(app.static_folder, "index.html")


def _warmup_prediction():
    """后台预热 TGCN 预测模型，避免首次请求超时。"""
    import threading
    def _load():
        try:
            from backend.prediction.traffic_prediction_service import TrafficPredictionService
            svc = TrafficPredictionService.get_instance()
            svc.predict(step=1, top_k=12)
            print("[OK] TGCN 预测模型预热完成")
        except Exception as e:
            print(f"[WARN] TGCN 预热失败（首次预测请求将触发加载）: {e}")
    t = threading.Thread(target=_load, daemon=True)
    t.start()


if __name__ == "__main__":
    print("=" * 50)
    print("  交通路径规划系统启动中...")
    print("=" * 50)

    # 预加载路网
    from backend.routing.router import RouterService

    service = RouterService.get_instance()
    stats = service._road_graph.get_stats()
    print(f"  路网节点: {stats['nodes']}")
    print(f"  路网边数: {stats['edges']}")
    print(f"  总长度: {stats.get('total_length_km', 0):.1f} km")
    print("=" * 50)

    # 后台预热 TGCN 模型
    _warmup_prediction()

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
