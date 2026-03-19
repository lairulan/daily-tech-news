#!/usr/bin/env python3
"""
科技日报 - 图片生成脚本
调用中央 generate-image 技能（AI Gateway + IMGBB）
"""

import os
import sys
import json
import argparse
import subprocess

# 中央生图脚本路径
CENTRAL_SCRIPT = os.path.expanduser("~/.claude/skills/generate-image/scripts/generate_image.py")


def call_central_generate(prompt, upload_imgbb=True, output=None, retry=3):
    """调用中央生图脚本"""
    cmd = [
        sys.executable, CENTRAL_SCRIPT,
        prompt,
        "--json",
        "--retry", str(retry)
    ]
    if upload_imgbb:
        cmd.append("--upload-imgbb")
    if output:
        cmd.extend(["--output", output])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        stdout = result.stdout.strip()
        if not stdout:
            return {"success": False, "error": f"中央脚本无输出. stderr: {result.stderr[:500]}"}

        lines = stdout.split('\n')
        json_lines = []
        for line in reversed(lines):
            json_lines.insert(0, line)
            if line.strip().startswith('{'):
                break

        return json.loads('\n'.join(json_lines))
    except json.JSONDecodeError:
        return {"success": False, "error": f"JSON 解析失败: {stdout[:300]}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "生图超时", "code": "TIMEOUT"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def generate_image(prompt, retry=3, retry_delay=3, size="1024x1024"):
    """生成图片（通过中央脚本）"""
    result = call_central_generate(prompt, upload_imgbb=True, retry=retry)
    if result.get("success"):
        return {
            "success": True,
            "url": result.get("imgbb_url") or result.get("url"),
            "attempts": 1,
            "source": result.get("source", "ai-gateway")
        }
    return result


def main():
    parser = argparse.ArgumentParser(description="AI 图片生成工具（中央引擎）")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    gen_parser = subparsers.add_parser("generate", help="生成图片")
    gen_parser.add_argument("--prompt", "-p", required=True)
    gen_parser.add_argument("--retry", type=int, default=3)
    gen_parser.add_argument("--size", default="1024x1024")

    cover_parser = subparsers.add_parser("cover", help="生成封面图")
    cover_parser.add_argument("--title", "-t", required=True)
    cover_parser.add_argument("--style", "-s", default="tech", choices=["modern", "minimalist", "tech", "warm", "creative"])
    cover_parser.add_argument("--retry", type=int, default=3)
    cover_parser.add_argument("--size", default="1024x1024")

    args = parser.parse_args()

    if args.command == "generate":
        result = generate_image(args.prompt, retry=args.retry)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "cover":
        style_prompts = {
            "modern": "professional magazine cover, clean modern aesthetic, vibrant elegant colors",
            "minimalist": "minimalist style, elegant simplicity, soft natural lighting, zen atmosphere",
            "tech": "futuristic technology, cyberpunk, neon blue and purple gradients, digital art, high tech atmosphere",
            "warm": "warm golden hour lighting, soft gradients, inviting atmosphere, cozy vibe, pastel tones",
            "creative": "artistic creative, vibrant colors, modern illustration, eye-catching composition"
        }
        style_desc = style_prompts.get(args.style, style_prompts["tech"])
        prompt = f"Professional cover image for tech news article. Style: {style_desc}. NO text, NO letters, NO typography. Clean composition, visually striking, suitable for social media cover. High quality, sharp details."

        result = generate_image(prompt, retry=args.retry)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
