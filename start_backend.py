import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import app

if __name__ == '__main__':
    print("启动TGCN路径规划系统...")
    print("后端服务将在 http://localhost:5000 运行")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
