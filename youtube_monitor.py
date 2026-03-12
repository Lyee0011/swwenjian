"""
YouTube 博主新视频监控脚本
每隔1小时检查指定YouTube博主的最新视频，如果有新视频则通过飞书 Webhook 发送提醒。

使用方法:
1. 安装依赖: pip install requests
2. 设置环境变量:
   - FEISHU_WEBHOOK_URL: 飞书机器人 Webhook 地址
   - YOUTUBE_API_KEY: YouTube Data API v3 密钥 (从 Google Cloud Console 获取)
3. 运行: python youtube_monitor.py
"""

import os
import sys
import json
import time
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path

# ==================== 配置 ====================

# 要监控的 YouTube 频道 (handle -> 显示名称)
CHANNELS = {
    "@BizofFame": "Biz of Fame",
    "@TheValley101": "The Valley 101",
    "@ThinkSchool": "Think School",
}

# 检查间隔（秒），默认 1 小时
CHECK_INTERVAL = 3600

# 记录已通知视频的文件，避免重复提醒
STATE_FILE = Path(__file__).parent / "youtube_monitor_state.json"

# ==================== 日志 ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ==================== 核心函数 ====================


def load_state() -> dict:
    """加载已通知视频 ID 的状态文件。"""
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"notified_video_ids": []}


def save_state(state: dict):
    """保存状态到文件。"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_channel_id(api_key: str, handle: str) -> str | None:
    """通过 YouTube handle 获取频道 ID。"""
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {"part": "id", "forHandle": handle.lstrip("@"), "key": api_key}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if items:
        return items[0]["id"]
    return None


def get_latest_videos(api_key: str, channel_id: str, max_results: int = 3) -> list[dict]:
    """获取频道最新发布的视频列表。"""
    # 先通过 search 接口获取最新视频
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "order": "date",
        "type": "video",
        "maxResults": max_results,
        "key": api_key,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    videos = []
    for item in data.get("items", []):
        snippet = item["snippet"]
        videos.append({
            "video_id": item["id"]["videoId"],
            "title": snippet["title"],
            "channel_title": snippet["channelTitle"],
            "published_at": snippet["publishedAt"],
            "thumbnail": snippet["thumbnails"].get("high", snippet["thumbnails"]["default"])["url"],
            "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
        })
    return videos


def send_feishu_notification(webhook_url: str, video: dict):
    """通过飞书 Webhook 发送新视频提醒。"""
    published = video["published_at"]
    try:
        dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        published = dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        pass

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🎬 YouTube 新视频提醒",
                },
                "template": "red",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**频道**: {video['channel_title']}\n"
                            f"**标题**: {video['title']}\n"
                            f"**发布时间**: {published}\n"
                            f"**链接**: [点击观看]({video['url']})"
                        ),
                    },
                    "extra": {
                        "tag": "img",
                        "img_key": "",
                        "alt": {"tag": "plain_text", "content": "thumbnail"},
                    },
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "打开视频"},
                            "url": video["url"],
                            "type": "primary",
                        }
                    ],
                },
            ],
        },
    }

    resp = requests.post(webhook_url, json=card, timeout=10)
    resp.raise_for_status()
    result = resp.json()
    if result.get("code") != 0 and result.get("StatusCode") != 0:
        log.warning("飞书消息发送结果: %s", result)
    else:
        log.info("飞书通知已发送: %s", video["title"])


def resolve_channel_ids(api_key: str) -> dict[str, str]:
    """将所有频道 handle 解析为 channel ID，返回 {channel_id: display_name}。"""
    channel_map = {}
    for handle, name in CHANNELS.items():
        log.info("正在解析频道: %s (%s)", name, handle)
        channel_id = get_channel_id(api_key, handle)
        if channel_id:
            channel_map[channel_id] = name
            log.info("  -> 频道 ID: %s", channel_id)
        else:
            log.warning("  -> 未找到频道: %s", handle)
    return channel_map


def check_new_videos(api_key: str, webhook_url: str, channel_map: dict[str, str], state: dict):
    """检查所有频道的新视频并发送通知。"""
    notified = set(state.get("notified_video_ids", []))

    for channel_id, name in channel_map.items():
        log.info("检查频道: %s", name)
        try:
            videos = get_latest_videos(api_key, channel_id)
        except requests.RequestException as e:
            log.error("获取 %s 视频列表失败: %s", name, e)
            continue

        for video in videos:
            vid = video["video_id"]
            if vid not in notified:
                log.info("发现新视频: %s", video["title"])
                try:
                    send_feishu_notification(webhook_url, video)
                except requests.RequestException as e:
                    log.error("发送飞书通知失败: %s", e)
                    continue
                notified.add(vid)

    state["notified_video_ids"] = list(notified)
    # 只保留最近 500 条记录，防止文件无限增长
    if len(state["notified_video_ids"]) > 500:
        state["notified_video_ids"] = state["notified_video_ids"][-500:]
    save_state(state)


# ==================== 主循环 ====================


def main():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL")

    if not api_key:
        log.error("请设置环境变量 YOUTUBE_API_KEY (YouTube Data API v3 密钥)")
        log.error("获取方式: https://console.cloud.google.com/ -> API 和服务 -> 凭据")
        sys.exit(1)

    if not webhook_url:
        log.error("请设置环境变量 FEISHU_WEBHOOK_URL (飞书自定义机器人 Webhook 地址)")
        log.error("获取方式: 飞书群 -> 设置 -> 群机器人 -> 自定义机器人")
        sys.exit(1)

    log.info("=" * 50)
    log.info("YouTube 新视频监控已启动")
    log.info("监控频道: %s", ", ".join(CHANNELS.values()))
    log.info("检查间隔: %d 秒 (%d 分钟)", CHECK_INTERVAL, CHECK_INTERVAL // 60)
    log.info("=" * 50)

    # 解析频道 ID（只需解析一次）
    channel_map = resolve_channel_ids(api_key)
    if not channel_map:
        log.error("没有有效的频道，退出")
        sys.exit(1)

    state = load_state()

    # 首次运行：记录当前视频但不发通知（避免启动时刷屏）
    if not state.get("notified_video_ids"):
        log.info("首次运行，记录现有视频（不发送通知）...")
        notified = set()
        for channel_id, name in channel_map.items():
            try:
                videos = get_latest_videos(api_key, channel_id)
                for v in videos:
                    notified.add(v["video_id"])
                    log.info("  已记录: [%s] %s", name, v["title"])
            except requests.RequestException as e:
                log.error("获取 %s 视频列表失败: %s", name, e)
        state["notified_video_ids"] = list(notified)
        save_state(state)
        log.info("首次记录完成，后续新视频将发送飞书通知")

    while True:
        log.info("--- 开始检查新视频 ---")
        check_new_videos(api_key, webhook_url, channel_map, state)
        log.info("下次检查时间: %s", datetime.now(timezone.utc).strftime("%H:%M:%S UTC") + f" + {CHECK_INTERVAL}s")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
