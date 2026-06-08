#!/usr/bin/env python3
"""为所有轨迹生成带 bbox 标注的可视化"""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def visualize_trajectory(traj_dir):
    """为单个轨迹生成可视化"""
    traj_file = traj_dir / 'trajectory.json'
    if not traj_file.exists():
        return
    
    with open(traj_file) as f:
        traj = json.load(f)
    
    output_dir = traj_dir / 'visualized'
    output_dir.mkdir(exist_ok=True)
    
    print(f'\n📂 {traj["task"]}')
    
    for step_data in traj['steps']:
        step_num = step_data['step']
        img_path = traj_dir / step_data['screenshot']
        
        if not img_path.exists():
            continue
        
        # 加载图片
        img = Image.open(img_path).convert('RGB')
        draw = ImageDraw.Draw(img)
        
        # 尝试加载字体
        try:
            font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 20)
            font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
        except:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        action = step_data['action']
        
        # 绘制顶部信息栏
        draw.rectangle([(0, 0), (1280, 60)], fill=(255, 0, 0))
        
        # 步骤信息
        step_text = f"Step {step_num}: {action['action'].upper()}"
        draw.text((10, 10), step_text, fill='white', font=font_large)
        
        # 目标文本
        if 'target_text' in action:
            target = action['target_text'][:60]
            draw.text((10, 35), f"Target: {target}", fill='yellow', font=font_small)
        
        # 如果动作是 click，尝试高亮目标区域（模拟）
        if action['action'] == 'click' and 'target_text' in action:
            # 在右下角绘制动作说明
            reason = action.get('reason', '')[:150]
            
            # 绘制半透明背景
            overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            
            text_y = 650
            overlay_draw.rectangle([(10, text_y), (1270, text_y + 60)], 
                                  fill=(0, 0, 0, 180))
            
            img_with_overlay = Image.alpha_composite(img.convert('RGBA'), overlay)
            img = img_with_overlay.convert('RGB')
            draw = ImageDraw.Draw(img)
            
            draw.text((20, text_y + 10), f"Reasoning:", 
                     fill='lightblue', font=font_small)
            draw.text((20, text_y + 30), reason, 
                     fill='white', font=font_small)
        
        # 保存标注后的图片
        output_path = output_dir / f'annotated_{img_path.name}'
        img.save(output_path)
        print(f'  ✅ Step {step_num}')
    
    print(f'  💾 输出: {output_dir}')

# 主程序
base_dir = Path.home() / 'Explorer/trajectories/kimi_20260604_081405'

print('='*60)
print('🎨 生成轨迹可视化（带 bbox 标注）')
print('='*60)

for task_dir in sorted(base_dir.glob('*/')):
    if task_dir.is_dir():
        visualize_trajectory(task_dir)

print('\n' + '='*60)
print('✅ 所有轨迹可视化完成！')
print('='*60)
