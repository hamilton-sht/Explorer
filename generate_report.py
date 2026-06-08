#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime

traj_dir = Path.home() / 'Explorer/trajectories/kimi_20260604_081405'

print('='*60)
print('🎯 Explorer + kimi-k2-5 轨迹采集报告')
print('='*60)
print(f'时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print(f'输出目录: {traj_dir}')
print()

tasks_summary = []
total_steps = 0
total_screenshots = 0

for task_path in sorted(traj_dir.glob('*/')):
    if not task_path.is_dir():
        continue
    
    traj_file = task_path / 'trajectory.json'
    if not traj_file.exists():
        continue
    
    with open(traj_file) as f:
        traj = json.load(f)
    
    screenshots = list(task_path.glob('*.png'))
    steps = len(traj['steps'])
    
    tasks_summary.append({
        'name': traj['task'],
        'goal': traj['goal'],
        'url': traj['url'],
        'steps': steps,
        'screenshots': len(screenshots)
    })
    
    total_steps += steps
    total_screenshots += len(screenshots)

print('📊 任务汇总:')
print()
for i, task in enumerate(tasks_summary, 1):
    print(f'{i}. {task["name"]}')
    print(f'   目标: {task["goal"]}')
    print(f'   URL: {task["url"]}')
    print(f'   步数: {task["steps"]} | 截图: {task["screenshots"]}')
    print()

print('='*60)
print('📈 统计')
print('='*60)
print(f'任务总数: {len(tasks_summary)}')
print(f'总步数: {total_steps}')
print(f'总截图: {total_screenshots}')
print(f'平均步数/任务: {total_steps/len(tasks_summary):.1f}')
print()

print('='*60)
print('🔍 示例轨迹详情 (GitHub Trending)')
print('='*60)
github_traj = traj_dir / 'github_trending/trajectory.json'
with open(github_traj) as f:
    gh = json.load(f)

for i in range(min(3, len(gh['steps']))):
    step = gh['steps'][i]
    print(f'\nStep {i}:')
    print(f'  URL: {step["url"]}')
    print(f'  动作: {step["action"]["action"]}')
    if 'target_text' in step['action']:
        print(f'  目标: {step["action"]["target_text"]}')
    print(f'  推理: {step["action"]["reason"][:100]}...')

print('\n' + '='*60)
print('✅ 轨迹采集完成！')
print('='*60)
