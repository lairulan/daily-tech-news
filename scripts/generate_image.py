#!/usr/bin/env python3
"""
图片生成脚本
支持 OpenRouter (Gemini) 和 豆包 API
"""

import os
import sys
import json
import base64
import argparse
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
import ssl

# 创建 SSL 上下文
ssl_context = ssl._create_unverified_context()

# API 配置
DOUBAO_IMAGE_API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
DOUBAO_IMAGE_MODEL = "doubao-seedream-4-5-251128"
IMGBB_API_URL = "https://api.imgbb.com/1/upload"

def get_env_var(name, default=None, required=True):
    """获取环境变量"""
    value = os.environ.get(name, default)
    if required and not value:
        return None
    return value

def log_stderr(message):
    """输出日志到 stderr"""
    print(json.dumps(message, ensure_ascii=False), file=sys.stderr)

def generate_image_doubao(prompt, retry=3, retry_delay=3, size="2048x2048"):
    """使用豆包 API 生成图片（备用）"""
    api_key = get_env_var("DOUBAO_API_KEY", required=True)
    if not api_key:
        return {"success": False, "error": "未设置 DOUBAO_API_KEY", "code": "ENV_VAR_MISSING"}

    last_error = None

    for attempt in range(retry):
        if attempt > 0:
            log_stderr({"status": "retrying", "message": f"豆包重试第 {attempt}/{retry-1} 次...", "delay": retry_delay})
            time.sleep(retry_delay)

        data = {
            "model": DOUBAO_IMAGE_MODEL,
            "prompt": prompt,
            "response_format": "url",
            "size": size,
            "guidance_scale": 3,
            "watermark": False
        }

        try:
            cmd = [
                "curl", "-s", "-X", "POST", DOUBAO_IMAGE_API_URL,
                "-H", f"Authorization: Bearer {api_key}",
                "-H", "Content-Type: application/json",
                "-d", json.dumps(data, ensure_ascii=False)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            response = json.loads(result.stdout)

            if "error" in response:
                last_error = {
                    "success": False,
                    "error": f"API错误: {response['error'].get('message', str(response['error']))}",
                    "code": "API_ERROR",
                    "attempt": attempt + 1
                }
                log_stderr(last_error)
                continue

            if "data" in response and len(response["data"]) > 0:
                image_url = response["data"][0].get("url")
                if image_url:
                    return {
                        "success": True,
                        "url": image_url,
                        "attempts": attempt + 1,
                        "source": "doubao"
                    }

            last_error = {
                "success": False,
                "error": "未能从响应中提取图片 URL",
                "attempt": attempt + 1
            }
            log_stderr(last_error)

        except subprocess.TimeoutExpired:
            last_error = {"success": False, "error": "图片生成超时", "code": "TIMEOUT", "attempt": attempt + 1}
            log_stderr(last_error)
        except json.JSONDecodeError as e:
            last_error = {"success": False, "error": f"响应解析失败: {str(e)}", "code": "PARSE_ERROR", "attempt": attempt + 1}
            log_stderr(last_error)
        except Exception as e:
            last_error = {"success": False, "error": str(e), "code": "UNKNOWN_ERROR", "attempt": attempt + 1}
            log_stderr(last_error)

    return last_error if last_error else {
        "success": False,
        "error": "豆包图片生成失败",
        "code": "ALL_RETRIES_FAILED"
    }

def generate_image(prompt, retry=3, retry_delay=3, size="1024x1024"):
    """生成图片（优先 OpenRouter，备用豆包）"""
    log_stderr({"status": "generating", "message": "正在生成图片...", "prompt": prompt[:100]})

    # 优先使用 OpenRouter

    # 备用：豆包
    doubao_key = get_env_var("DOUBAO_API_KEY", required=False)
    if doubao_key:
        log_stderr({"status": "using_doubao", "message": "使用豆包 API 生成图片"})
        return generate_image_doubao(prompt, retry=retry, retry_delay=retry_delay, size=size)

    return {
        "success": False,
        "error": "未设置 DOUBAO_API_KEY 环境变量",
        "code": "NO_API_KEY"
    }

def main():
    parser = argparse.ArgumentParser(description="AI 图片生成工具（支持 OpenRouter 和豆包）")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # generate 命令
    gen_parser = subparsers.add_parser("generate", help="生成图片")
    gen_parser.add_argument("--prompt", "-p", required=True, help="图片描述提示词")
    gen_parser.add_argument("--retry", type=int, default=3, help="失败重试次数")
    gen_parser.add_argument("--retry-delay", type=int, default=3, help="重试延迟秒数")
    gen_parser.add_argument("--size", default="1024x1024", help="图片尺寸")

    # cover 命令
    cover_parser = subparsers.add_parser("cover", help="根据文章标题生成封面图")
    cover_parser.add_argument("--title", "-t", required=True, help="文章标题")
    cover_parser.add_argument("--style", "-s", default="tech",
                             choices=["modern", "minimalist", "tech", "warm", "creative"],
                             help="封面风格")
    cover_parser.add_argument("--retry", type=int, default=3, help="失败重试次数")
    cover_parser.add_argument("--retry-delay", type=int, default=3, help="重试延迟秒数")
    cover_parser.add_argument("--size", default="1024x1024", help="图片尺寸")

    args = parser.parse_args()

    if args.command == "generate":
        result = generate_image(args.prompt, retry=args.retry, retry_delay=args.retry_delay, size=args.size)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "cover":
        style_prompts = {
            "modern": "ultra high quality, professional magazine cover, clean modern aesthetic, vibrant elegant colors",
            "minimalist": "minimalist style, elegant simplicity, soft natural lighting, zen atmosphere",
            "tech": "futuristic technology, cyberpunk, neon blue and purple gradients, digital art, high tech atmosphere",
            "warm": "warm golden hour lighting, soft gradients, inviting atmosphere, cozy vibe, pastel tones",
            "creative": "artistic creative, vibrant colors, modern illustration, eye-catching composition"
        }

        style_desc = style_prompts.get(args.style, style_prompts["tech"])

        prompt = f"Professional cover image for tech news article. Style: {style_desc}. NO text, NO letters, NO typography. Clean composition, visually striking, suitable for social media cover. High quality, sharp details."

        result = generate_image(prompt, retry=args.retry, retry_delay=args.retry_delay, size=args.size)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
