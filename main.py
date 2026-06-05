"""财智8 Web — 一键启动入口

用法：
    python main.py          # 开发模式：同时启动后端(8000) + 前端 Vite(5173，热更新)
    python main.py --prod   # 生产模式：构建前端后由后端单进程托管(8000)
    python main.py --skip-install  # 跳过依赖自检（依赖已装好时更快启动）
    python main.py --init   # 重置为初始默认数据库（一个空的默认账本）后退出
    python main.py --demo   # 生成一套覆盖全部功能的演示数据库后退出

首次运行会自动检测并安装前后端依赖，无需手动准备。
"""
import argparse
import atexit
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def ensure_backend_deps():
    """后端依赖自检：缺少关键包时自动 pip install。"""
    if importlib.util.find_spec("fastapi") and importlib.util.find_spec("uvicorn"):
        return
    print("[main] 检测到后端依赖缺失，正在安装 (pip install -r requirements.txt) ...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(BACKEND / "requirements.txt")],
        check=True,
    )


def ensure_frontend_deps():
    """前端依赖自检：node_modules 不存在时自动 npm install。"""
    if (FRONTEND / "node_modules").exists():
        return
    if shutil.which("npm") is None:
        print("[main] 未检测到 npm，请先安装 Node.js（https://nodejs.org）后重试。")
        sys.exit(1)
    print("[main] 检测到前端依赖缺失，正在安装 (npm install) ...")
    subprocess.run("npm install", cwd=FRONTEND, shell=True, check=True)


def run_backend():
    sys.path.insert(0, str(BACKEND))
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, app_dir=str(BACKEND))


def start_frontend_dev() -> subprocess.Popen:
    proc = subprocess.Popen("npm run dev", cwd=FRONTEND, shell=True)
    atexit.register(proc.terminate)
    return proc


def build_frontend():
    print("[main] 正在构建前端 (npm run build) ...")
    subprocess.run("npm run build", cwd=FRONTEND, shell=True, check=True)


def run_db_command(mode: str):
    """初始化数据库：mode 为 'init'（默认空账本）或 'demo'（演示数据）。"""
    sys.path.insert(0, str(BACKEND))
    from app import demo

    if mode == "demo":
        demo.build_demo()
    else:
        demo.init_database()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prod", action="store_true", help="生产模式：单进程托管")
    parser.add_argument("--skip-install", action="store_true", help="跳过依赖自检")
    parser.add_argument("--init", action="store_true", help="重置为初始默认数据库后退出")
    parser.add_argument("--demo", action="store_true", help="生成覆盖全部功能的演示数据库后退出")
    args = parser.parse_args()

    # 数据库初始化命令：执行后直接退出，不启动服务
    if args.init or args.demo:
        if args.init and args.demo:
            print("[main] --init 与 --demo 不能同时使用。")
            sys.exit(1)
        run_db_command("demo" if args.demo else "init")
        return

    if not args.skip_install:
        ensure_backend_deps()
        ensure_frontend_deps()

    if args.prod:
        build_frontend()
        print("[main] 启动后端（单进程托管前端） -> http://localhost:8000")
        run_backend()
    else:
        print("[main] 开发模式：后端 http://localhost:8000 ，前端 http://localhost:5173")
        start_frontend_dev()
        run_backend()


if __name__ == "__main__":
    main()
