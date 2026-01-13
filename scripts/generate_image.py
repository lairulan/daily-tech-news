#!/usr/bin/env python3
"""
图片生成脚本
使用 Gemini API 生成图片，上传到 imgbb 图床
"""

import os
import sys
import json
import base64
import argparse
import subprocess
import tempfile

# API 配置
DOUBAO_IMAGE_API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
DOUBAO_IMAGE_MODEL = "doubao-seedream-4-5-251128"
IMGBB_API_URL = "https://api.imgbb.com/1/upload"

def get_env_var(name, default=None):
    """获取环境变量"""
    value = os.environ.get(name, default)
    if not value:
        print(json.dumps({
            "success": False,
            "error": f"环境变量 {name} 未设置",
            "code": "ENV_VAR_MISSING"
        }, ensure_ascii=False))
        sys.exit(1)
    return value

def generate_image(prompt, retry=3, retry_delay=3, size="2048x2048"):
    """调用豆包图片生成 API（带重试机制）"""
    api_key = get_env_var("DOUBAO_API_KEY")

    import time
    last_error = None

    for attempt in range(retry):
        if attempt > 0:
            print(json.dumps({
                "status": "retrying",
                "message": f"重试第 {attempt}/{retry-1} 次...",
                "delay": retry_delay
            }, ensure_ascii=False), file=sys.stderr)
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

            # 检查是否有错误
            if "error" in response:
                last_error = {
                    "success": False,
                    "error": f"API错误: {response['error'].get('message', str(response['error']))}",
                    "code": "API_ERROR",
                    "attempt": attempt + 1,
                    "response": str(response)[:500]
                }
                print(json.dumps(last_error, ensure_ascii=False), file=sys.stderr)
                continue

            # 提取图片 URL（豆包直接返回 URL）
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
                "response": str(response)[:500],
                "attempt": attempt + 1
            }
            print(json.dumps(last_error, ensure_ascii=False), file=sys.stderr)

        except subprocess.TimeoutExpired:
            last_error = {
                "success": False,
                "error": "图片生成超时",
                "code": "TIMEOUT",
                "attempt": attempt + 1
            }
            print(json.dumps(last_error, ensure_ascii=False), file=sys.stderr)
        except json.JSONDecodeError as e:
            last_error = {
                "success": False,
                "error": f"响应解析失败: {str(e)}",
                "code": "PARSE_ERROR",
                "raw_output": result.stdout[:500] if 'result' in locals() else "",
                "attempt": attempt + 1
            }
            print(json.dumps(last_error, ensure_ascii=False), file=sys.stderr)
        except Exception as e:
            last_error = {
                "success": False,
                "error": str(e),
                "code": "UNKNOWN_ERROR",
                "attempt": attempt + 1
            }
            print(json.dumps(last_error, ensure_ascii=False), file=sys.stderr)

    # 所有重试都失败
    return last_error if last_error else {
        "success": False,
        "error": "图片生成失败，已重试所有次数",
        "code": "ALL_RETRIES_FAILED"
    }

def upload_to_imgbb(image_base64, retry=3, retry_delay=2):
    """上传图片到 imgbb（带重试机制）"""
    api_key = get_env_var("IMGBB_API_KEY")

    import time
    last_error = None

    for attempt in range(retry):
        if attempt > 0:
            print(json.dumps({
                "status": "retrying_upload",
                "message": f"上传重试第 {attempt}/{retry-1} 次...",
                "delay": retry_delay
            }, ensure_ascii=False), file=sys.stderr)
            time.sleep(retry_delay)

        # 使用临时文件传递图片数据
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(image_base64)
            image_file = f.name

        try:
            # 使用 -F 和 @ 从文件读取
            cmd = [
                "curl", "-s", "--max-time", "60",
                "-X", "POST",
                f"{IMGBB_API_URL}?key={api_key}",
                "-F", f"image=<{image_file}"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            response = json.loads(result.stdout)

            if response.get("success"):
                return {
                    "success": True,
                    "url": response["data"]["url"],
                    "display_url": response["data"]["display_url"],
                    "delete_url": response["data"]["delete_url"],
                    "attempts": attempt + 1
                }
            else:
                last_error = {
                    "success": False,
                    "error": response.get("error", {}).get("message", "上传失败"),
                    "code": "UPLOAD_FAILED",
                    "attempt": attempt + 1
                }
                print(json.dumps(last_error, ensure_ascii=False), file=sys.stderr)

        except subprocess.TimeoutExpired:
            last_error = {
                "success": False,
                "error": "上传超时",
                "code": "TIMEOUT",
                "attempt": attempt + 1
            }
            print(json.dumps(last_error, ensure_ascii=False), file=sys.stderr)
        except json.JSONDecodeError as e:
            last_error = {
                "success": False,
                "error": f"响应解析失败: {str(e)}",
                "code": "PARSE_ERROR",
                "raw_output": result.stdout[:500] if 'result' in locals() else "",
                "attempt": attempt + 1
            }
            print(json.dumps(last_error, ensure_ascii=False), file=sys.stderr)
        except Exception as e:
            last_error = {
                "success": False,
                "error": str(e),
                "code": "UNKNOWN_ERROR",
                "attempt": attempt + 1
            }
            print(json.dumps(last_error, ensure_ascii=False), file=sys.stderr)
        finally:
            if os.path.exists(image_file):
                os.unlink(image_file)

    # 所有重试都失败
    return last_error if last_error else {
        "success": False,
        "error": "上传失败，已重试所有次数",
        "code": "ALL_RETRIES_FAILED"
    }

def generate_and_upload(prompt, retry=3, retry_delay=3, size="1024x1024"):
    """生成图片（豆包 API 直接返回 URL，无需上传）"""
    # 生成图片
    print(json.dumps({"status": "generating", "message": "正在生成图片...", "prompt": prompt[:100]}, ensure_ascii=False), file=sys.stderr)

    gen_result = generate_image(prompt, retry=retry, retry_delay=retry_delay, size=size)

    if not gen_result.get("success"):
        print(json.dumps({"status": "generate_failed", "error": gen_result.get("error"), "prompt": prompt[:100]}, ensure_ascii=False), file=sys.stderr)
        return gen_result

    # 豆包 API 直接返回可用的图片 URL，无需上传到图床
    print(json.dumps({"status": "completed", "message": "图片生成成功"}, ensure_ascii=False), file=sys.stderr)

    return {
        "success": True,
        "url": gen_result["url"],
        "display_url": gen_result["url"],
        "prompt": prompt,
        "generate_attempts": gen_result.get("attempts", 1),
        "source": "doubao"
    }

def main():
    parser = argparse.ArgumentParser(description="AI 图片生成工具（豆包 API）")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # generate 命令 - 生成图片
    gen_parser = subparsers.add_parser("generate", help="生成图片")
    gen_parser.add_argument("--prompt", "-p", required=True, help="图片描述提示词")
    gen_parser.add_argument("--retry", type=int, default=3, help="失败重试次数 (默认: 3)")
    gen_parser.add_argument("--retry-delay", type=int, default=3, help="重试延迟秒数 (默认: 3)")
    gen_parser.add_argument("--size", default="2048x2048", help="图片尺寸 (默认: 2048x2048)")

    # cover 命令 - 生成封面图
    cover_parser = subparsers.add_parser("cover", help="根据文章标题生成封面图")
    cover_parser.add_argument("--title", "-t", required=True, help="文章标题")
    cover_parser.add_argument("--style", "-s", default="modern",
                             choices=["modern", "minimalist", "tech", "warm", "creative"],
                             help="封面风格")
    cover_parser.add_argument("--retry", type=int, default=3, help="失败重试次数 (默认: 3)")
    cover_parser.add_argument("--retry-delay", type=int, default=3, help="重试延迟秒数 (默认: 3)")
    cover_parser.add_argument("--size", default="2048x2048", help="图片尺寸 (默认: 2048x2048)")

    args = parser.parse_args()

    if args.command == "generate":
        result = generate_and_upload(args.prompt, retry=args.retry, retry_delay=args.retry_delay, size=args.size)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "cover":
        # 根据风格生成优化的提示词（适配中文内容）
        style_prompts = {
            "modern": "ultra high quality, 8K resolution, professional magazine cover style, clean composition, modern aesthetic, vibrant but elegant colors, premium design, photorealistic lighting",
            "minimalist": "ultra high quality, 8K, minimalist style, negative space, elegant simplicity, refined aesthetic, soft natural lighting, premium feel, zen atmosphere",
            "tech": "ultra high quality, 8K, futuristic technology, cyberpunk elements, neon blue and purple gradients, digital art style, high tech atmosphere, clean composition, no text overlay",
            "warm": "ultra high quality, 8K, warm golden hour lighting, soft gradient background, inviting atmosphere, friendly and approachable, cozy vibe, pastel tones, gentle and warm aesthetic, clean and modern",
            "creative": "ultra high quality, 8K, artistic and creative, vibrant colors, modern illustration style, eye-catching composition, unique visual design, professional art direction, bold but tasteful"
        }

        style_desc = style_prompts.get(args.style, style_prompts["modern"])

        # 中文内容适配：强调无文字、高质量、适合公众号
        prompt = f"Professional cover image for article: '{args.title}'. Style requirements: {style_desc}. Critical constraints: NO text, NO Chinese characters, NO typography in the image. Image must be suitable for WeChat Official Account cover. Composition: clean, uncluttered, visually striking at small size. Quality: photorealistic or premium illustration, sharp details, professional lighting. Colors: vibrant but not oversaturated, modern aesthetic. Format: horizontal 16:9 aspect ratio."

        result = generate_and_upload(prompt, retry=args.retry, retry_delay=args.retry_delay, size=args.size)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
