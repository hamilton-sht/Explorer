#!/usr/bin/env python3
"""
快速运行脚本 - 使用 Moonshot API 生成2条轨迹
使用方法：
    export MOONSHOT_API_KEY='your-api-key'
    python quick_run.py
"""

import os
import sys
import subprocess
from datetime import datetime

def check_environment():
    """检查环境配置"""
    if not os.getenv("MOONSHOT_API_KEY"):
        print("❌ 错误：未设置 MOONSHOT_API_KEY 环境变量")
        print("\n请先设置 API Key：")
        print("  export MOONSHOT_API_KEY='your-moonshot-api-key'")
        print("\n然后运行：")
        print("  python quick_run.py")
        sys.exit(1)

    print("✓ 检测到 MOONSHOT_API_KEY")
    return True

def start_xvfb():
    """启动虚拟显示服务器"""
    try:
        result = subprocess.run(['pgrep', '-x', 'Xvfb'], capture_output=True)
        if result.returncode != 0:
            print("启动 Xvfb 虚拟显示服务器...")
            subprocess.Popen(['Xvfb', ':99', '-screen', '0', '1920x1280x16'])
            import time
            time.sleep(2)
            print("✓ Xvfb 已启动")
        else:
            print("✓ Xvfb 已在运行")
    except Exception as e:
        print(f"⚠ 启动 Xvfb 失败: {e}")

def run_trajectory(traj_num, init_url):
    """运行单条轨迹"""
    print("\n" + "="*60)
    print(f"生成第 {traj_num} 条轨迹")
    print(f"初始 URL: {init_url}")
    print("="*60 + "\n")

    output_dir = "/home/ubuntu/Explorer/trajectories"
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    traj_dir = f"{output_dir}/traj_{traj_num}_{timestamp}"
    os.makedirs(traj_dir, exist_ok=True)

    cmd = [
        "python", "-m", "traj_gen.main",
        "--model-dir", traj_dir,
        "--init-url", init_url,
        "--max-steps", "10",
        "--deployment", "gpt-4o",
        "--viewport-width", "1280",
        "--viewport-height", "720"
    ]

    log_file = os.path.join(traj_dir, "run.log")
    print(f"日志文件: {log_file}")

    with open(log_file, 'w') as log:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )

        for line in process.stdout:
            print(line, end='')
            log.write(line)

        process.wait()

    print(f"\n✓ 轨迹 {traj_num} 完成")
    print(f"  保存位置: {traj_dir}")

    return traj_dir

def main():
    print("🚀 Explorer 轨迹生成工具 - Moonshot API 版本")
    print("="*60)

    # 检查环境
    check_environment()

    # 设置显示环境
    os.environ['DISPLAY'] = ':99'

    # 启动虚拟显示
    start_xvfb()

    # 定义要测试的 URL
    urls = [
        "https://www.amazon.com/",
        "https://www.wikipedia.org/",
    ]

    trajectories = []

    # 生成轨迹
    for i, url in enumerate(urls, 1):
        try:
            traj_dir = run_trajectory(i, url)
            trajectories.append(traj_dir)
        except Exception as e:
            print(f"\n❌ 生成轨迹 {i} 时出错: {e}")
            import traceback
            traceback.print_exc()

    # 输出总结
    print("\n" + "="*60)
    print("✅ 全部完成！")
    print(f"成功生成 {len(trajectories)} 条轨迹：")
    for i, traj in enumerate(trajectories, 1):
        print(f"  {i}. {traj}")
    print("="*60)

if __name__ == "__main__":
    main()
