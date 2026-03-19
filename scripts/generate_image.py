#!/usr/bin/env python3
"""
科技日报 - 图片生成脚本
直接调用 AI Gateway（https://ai-gateway.happycapy.ai）+ IMGBB 上传
无本地路径依赖，可在 GitHub Actions 中正常运行
"""

import base64
import json
import os
import sys
import time
from urllib import request as urllib_request
from urllib.error import HTTPError
from urllib.parse import urlencode

API_BASE = "https://ai-gateway.happycapy.ai/api/v1"
DEFAULT_MODEL = "google/gemini-3.1-flash-image-preview"


def _generate_image_b64(prompt, model=DEFAULT_MODEL, retry=3):
    """直接调用 AI Gateway 生成图片，返回 base64 数据"""
    api_key = os.environ.get("AI_GATEWAY_API_KEY")
    if not api_key:
        return {"success": False, "error": "未设置 AI_GATEWAY_API_KEY"}

    payload = {
        "model": model,
        "prompt": prompt,
        "response_format": "b64_json",
        "n": 1,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Origin": "https://trickle.so",
        "User-Agent": "Mozilla/5.0 (compatible; AI-Gateway-Client/1.0)",
    }

    for attempt in range(retry):
        try:
            req = urllib_request.Request(
                f"{API_BASE}/images/generations",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib_request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if "data" in data and data["data"]:
                b64 = data["data"][0].get("b64_json")
                if b64:
                    return {"success": True, "b64_json": b64}
            return {"success": False, "error": "API 响应无图片数据"}

        except HTTPError as e:
            err = e.read().decode("utf-8")
            if attempt < retry - 1:
                time.sleep(5)
                continue
            return {"success": False, "error": f"HTTP {e.code}: {err[:300]}"}
        except Exception as e:
            if attempt < retry - 1:
                time.sleep(5)
                continue
            return {"success": False, "error": str(e)}

    return {"success": False, "error": "超过重试次数"}


def _upload_imgbb(b64_data):
    """上传 base64 图片到 IMGBB，返回 URL"""
    api_key = os.environ.get("IMGBB_API_KEY")
    if not api_key:
        return None

    try:
        body = urlencode({"key": api_key, "image": b64_data})
        req = urllib_request.Request(
            "https://api.imgbb.com/1/upload",
            data=body.encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("success"):
            return result["data"]["url"]
    except Exception:
        pass
    return None


def generate_image(prompt, retry=3, retry_delay=3, size="1024x1024"):
    """生成图片并上传到 IMGBB，返回统一格式结果"""
    result = _generate_image_b64(prompt, retry=retry)
    if not result.get("success"):
        return result

    imgbb_url = _upload_imgbb(result["b64_json"])

    return {
        "success": True,
        "url": imgbb_url,
        "imgbb_url": imgbb_url,
        "attempts": 1,
        "source": "ai-gateway",
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AI 图片生成工具（AI Gateway 直连）")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    gen_parser = subparsers.add_parser("generate", help="生成图片")
    gen_parser.add_argument("--prompt", "-p", required=True)
    gen_parser.add_argument("--retry", type=int, default=3)
    gen_parser.add_argument("--size", default="1024x1024")

    cover_parser = subparsers.add_parser("cover", help="生成封面图")
    cover_parser.add_argument("--title", "-t", required=True)
    cover_parser.add_argument("--style", "-s", default="tech",
                              choices=["modern", "minimalist", "tech", "warm", "creative"])
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
            "creative": "artistic creative, vibrant colors, modern illustration, eye-catching composition",
        }
        style_desc = style_prompts.get(args.style, style_prompts["tech"])
        prompt = (
            f"Professional cover image for tech news article. Style: {style_desc}. "
            "NO text, NO letters, NO typography. Clean composition, visually striking, "
            "suitable for social media cover. High quality, sharp details."
        )
        result = generate_image(prompt, retry=args.retry)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
