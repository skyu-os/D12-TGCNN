"""
TGCN 智能路径规划系统 — 一键启动器
后端 + 前端一起启动，浏览器自动打开
"""
import os
import sys
import time
import socket
import webbrowser
import subprocess
import signal

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

HOST = "127.0.0.1"
PORT = 5000
URL = f"http://{HOST}:{PORT}"


def check_port(port):
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, port)) == 0


def kill_port(port):
    """释放被占用的端口"""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid],
                               capture_output=True, timeout=5)
                print(f"  [OK] 释放端口 {port} (PID {pid})")
                time.sleep(0.5)
    except Exception:
        pass


def main():
    print("=" * 52)
    print("  TGCN 智能路径规划系统")
    print("=" * 52)

    # 1. 端口检查
    if check_port(PORT):
        print(f"\n[!] 端口 {PORT} 被占用，尝试释放...")
        kill_port(PORT)

    # 2. 导入并启动
    print(f"\n[1] 启动服务 http://{HOST}:{PORT}")
    print("    (后端 API + 前端页面)")

    from backend.app import app

    # 预加载路网
    from backend.routing.router import RouterService
    service = RouterService.get_instance()
    stats = service._road_graph.get_stats()
    print(f"    路网节点: {stats['nodes']}")
    print(f"    路网边数: {stats['edges']}")
    print(f"    总长:     {stats.get('total_length_km', 0):.1f} km")

    # 3. 启动后自动打开浏览器
    def open_browser():
        time.sleep(1.5)
        webbrowser.open(URL)
        print(f"\n[2] 浏览器已打开: {URL}")

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # 4. 后台预热 TGCN 预测模型
    import threading
    def _warmup():
        try:
            from backend.prediction.traffic_prediction_service import TrafficPredictionService
            TrafficPredictionService.get_instance().predict(step=1, top_k=12)
            print("\n[OK] TGCN 预测模型预热完成")
        except Exception as e:
            print(f"\n[WARN] TGCN 预热失败: {e}")
    threading.Thread(target=_warmup, daemon=True).start()

    print(f"\n[3] 服务运行中... 按 Ctrl+C 停止")
    print("=" * 52)

    try:
        app.run(host=HOST, port=PORT, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\n服务已停止。")


if __name__ == "__main__":
    main()
