#!/usr/bin/env python3
"""
在轨迹截图上标注 bbox 动作坐标
"""
import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import argparse


def draw_bbox_on_image(image_path, actions, output_path):
    """在图片上绘制 bbox 和动作标注"""
    img = Image.open(image_path).convert('RGBA')
    overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # 尝试加载字体
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    for idx, action in enumerate(actions, 1):
        action_type = action.get('action_type', '')

        # 解析坐标
        if 'bbox' in action:
            bbox = action['bbox']
            if isinstance(bbox, list) and len(bbox) == 4:
                x1, y1, x2, y2 = bbox
            elif isinstance(bbox, dict):
                x1 = bbox.get('x1', bbox.get('left', 0))
                y1 = bbox.get('y1', bbox.get('top', 0))
                x2 = bbox.get('x2', bbox.get('right', 0))
                y2 = bbox.get('y2', bbox.get('bottom', 0))
            else:
                continue

            # 绘制半透明矩形
            draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0, 200), width=3)
            draw.rectangle([x1, y1, x2, y2], fill=(255, 0, 0, 50))

            # 绘制动作标签
            label = f"{idx}. {action_type}"
            text_bbox = draw.textbbox((0, 0), label, font=font)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]

            # 标签背景
            label_x = x1
            label_y = max(0, y1 - text_h - 4)
            draw.rectangle(
                [label_x, label_y, label_x + text_w + 8, label_y + text_h + 4],
                fill=(255, 0, 0, 220)
            )
            draw.text((label_x + 4, label_y + 2), label, fill=(255, 255, 255, 255), font=font)

            # 绘制坐标信息
            coord_text = f"({int(x1)},{int(y1)}) -> ({int(x2)},{int(y2)})"
            draw.text((x1 + 5, y1 + 5), coord_text, fill=(255, 255, 0, 255), font=small_font)

        elif 'coordinate' in action:
            coord = action['coordinate']
            if isinstance(coord, (list, tuple)) and len(coord) == 2:
                x, y = coord
            elif isinstance(coord, dict):
                x = coord.get('x', coord.get('left', 0))
                y = coord.get('y', coord.get('top', 0))
            else:
                continue

            # 绘制十字准星
            cross_size = 20
            draw.line([(x - cross_size, y), (x + cross_size, y)], fill=(255, 0, 0, 255), width=3)
            draw.line([(x, y - cross_size), (x, y + cross_size)], fill=(255, 0, 0, 255), width=3)
            draw.ellipse([x-5, y-5, x+5, y+5], fill=(255, 0, 0, 200))

            # 标签
            label = f"{idx}. {action_type}"
            text_bbox = draw.textbbox((0, 0), label, font=font)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]

            label_x = x + 10
            label_y = y - text_h - 4
            draw.rectangle(
                [label_x, label_y, label_x + text_w + 8, label_y + text_h + 4],
                fill=(255, 0, 0, 220)
            )
            draw.text((label_x + 4, label_y + 2), label, fill=(255, 255, 255, 255), font=font)

            coord_text = f"({int(x)},{int(y)})"
            draw.text((x + 10, y + 5), coord_text, fill=(255, 255, 0, 255), font=small_font)

    # 合并图层
    result = Image.alpha_composite(img, overlay)
    result.convert('RGB').save(output_path, 'PNG')
    print(f"✅ 已保存标注图: {output_path}")


def process_trajectory_dir(traj_dir):
    """处理单个轨迹目录"""
    traj_path = Path(traj_dir)
    if not traj_path.exists():
        print(f"❌ 目录不存在: {traj_dir}")
        return

    # 查找轨迹 JSON 文件
    traj_file = traj_path / "trajectory.json"
    if not traj_file.exists():
        print(f"❌ 未找到 trajectory.json: {traj_dir}")
        return

    # 读取轨迹
    with open(traj_file) as f:
        traj_data = json.load(f)

    actions = traj_data.get('actions', traj_data.get('steps', []))

    # 查找截图文件
    screenshots = sorted(traj_path.glob("screenshot_*.png"))

    if not screenshots:
        print(f"⚠️  未找到截图: {traj_dir}")
        return

    print(f"\n📂 处理轨迹: {traj_path.name}")
    print(f"   动作数: {len(actions)}, 截图数: {len(screenshots)}")

    # 创建输出目录
    output_dir = traj_path / "annotated"
    output_dir.mkdir(exist_ok=True)

    # 为每张截图标注对应的动作
    for i, screenshot in enumerate(screenshots):
        # 找到此截图后的动作
        step_actions = []
        if i < len(actions):
            step_actions = [actions[i]]

        output_path = output_dir / f"annotated_{screenshot.name}"
        draw_bbox_on_image(screenshot, step_actions, output_path)


def main():
    parser = argparse.ArgumentParser(description="在轨迹截图上标注 bbox 动作坐标")
    parser.add_argument("traj_dirs", nargs="+", help="轨迹目录路径")
    args = parser.parse_args()

    for traj_dir in args.traj_dirs:
        process_trajectory_dir(traj_dir)

    print("\n✅ 所有轨迹处理完成")


if __name__ == "__main__":
    main()
