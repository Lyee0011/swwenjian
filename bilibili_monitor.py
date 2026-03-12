#!/usr/bin/env python3
"""
B站UP主新视频监控脚本
检查指定UP主的最新视频，如果有新视频则通过飞书 Webhook 发送提醒。
设计为通过 crontab 每小时调用一次，每次执行完即退出。

使用方法:
1. 安装依赖: pip install requests
2. 设置环境变量:
   - FEISHU_WEBHOOK_URL: 飞书自定义机器人 Webhook 地址
3. 添加 crontab:
   0 * * * * FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxx" /usr/bin/python3 /path/to/bilibili_monitor.py >> /var/log/bilibili_monitor.log 2>&1
"""

import os
import sys
import json
import logging
import requests
from datetime import datetime
from pathlib import Path

# ==================== 配置 ====================

# 要监控的UP主 (UID -> 名称)
# 获取 UID: 打开UP主主页，URL 中 space.bilibili.com/ 后面的数字就是 UID
UP_LIST = {
    "3546572535073498": "秋芝2046",
    "520819684": "小Lin说",
}

# 状态文件路径，记录已通知的视频，避免重复提醒
STATE_FILE = Path(__file__).parent / "bilibili_monitor_state.json"

# B站 API（无需登录/密钥，公开接口）
BILIBILI_SPACE_API = "https://api.bilibili.com/x/space/wbi/arc/search"

# 请求头，模拟浏览器避免被拦截
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}

# ==================== 日志 ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ==================== 核心函数 ====================


def load_state() -> dict:
    """加载状态文件。"""
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"notified_bvids": []}


def save_state(state: dict):
    """保存状态文件。"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_latest_videos(uid: str, page_size: int = 5) -> list[dict]:
    """
    获取UP主最新投稿的视频列表。
    使用 B站空间搜索接口，无需 API Key。
    """
    params = {
        "mid": uid,
        "ps": page_size,
        "pn": 1,
        "order": "pubdate",
    }

    resp = requests.get(BILIBILI_SPACE_API, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 0:
        log.warning("B站接口返回错误: code=%s, message=%s", data.get("code"), data.get("message"))
        # 尝试备用接口
        return get_latest_videos_fallback(uid, page_size)

    vlist = data.get("data", {}).get("list", {}).get("vlist", [])
    videos = []
    for v in vlist:
        videos.append({
            "bvid": v.get("bvid", ""),
            "title": v.get("title", ""),
            "author": v.get("author", ""),
            "description": v.get("description", "")[:100],
            "pic": v.get("pic", ""),
            "created": v.get("created", 0),
            "length": v.get("length", ""),
            "play": v.get("play", 0),
            "url": f"https://www.bilibili.com/video/{v.get('bvid', '')}",
        })
    return videos


def get_latest_videos_fallback(uid: str, page_size: int = 5) -> list[dict]:
    """
    备用方案：通过 B站搜索接口获取UP主视频。
    当 wbi 接口需要签名时使用此方案。
    """
    url = "https://api.bilibili.com/x/space/arc/search"
    params = {
        "mid": uid,
        "ps": page_size,
        "pn": 1,
        "order": "pubdate",
    }
    resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 0:
        # 再尝试 RSS 方案
        return get_latest_videos_rss(uid)

    vlist = data.get("data", {}).get("list", {}).get("vlist", [])
    videos = []
    for v in vlist:
        videos.append({
            "bvid": v.get("bvid", ""),
            "title": v.get("title", ""),
            "author": v.get("author", ""),
            "description": v.get("description", "")[:100],
            "pic": v.get("pic", ""),
            "created": v.get("created", 0),
            "length": v.get("length", ""),
            "play": v.get("play", 0),
            "url": f"https://www.bilibili.com/video/{v.get('bvid', '')}",
        })
    return videos


def get_latest_videos_rss(uid: str) -> list[dict]:
    """
    最终备用方案：通过 RSSHub 获取UP主视频。
    需要公共 RSSHub 实例可用。
    """
    rss_url = f"https://rsshub.app/bilibili/user/video/{uid}"
    try:
        resp = requests.get(rss_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        log.warning("RSSHub 也不可用，跳过 UID=%s", uid)
        return []

    # 简单解析 RSS XML
    import xml.etree.ElementTree as ET
    root = ET.fromstring(resp.text)
    videos = []
    for item in root.findall(".//item")[:5]:
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        pub_date = item.findtext("pubDate", "")
        # 从链接提取 bvid
        bvid = link.split("/")[-1] if link else ""
        videos.append({
            "bvid": bvid,
            "title": title,
            "author": UP_LIST.get(uid, "未知"),
            "description": "",
            "pic": "",
            "created": 0,
            "length": "",
            "play": 0,
            "url": link,
        })
    return videos


def format_timestamp(ts: int) -> str:
    """将 Unix 时间戳转为可读时间。"""
    if not ts:
        return "未知"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def send_feishu_notification(webhook_url: str, video: dict):
    """通过飞书 Webhook 发送新视频提醒（卡片消息）。"""
    publish_time = format_timestamp(video["created"])
    play_text = f"{video['play']}" if video["play"] else "暂无"

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "📺 B站新视频提醒",
                },
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**UP主**: {video['author']}\n"
                            f"**标题**: {video['title']}\n"
                            f"**时长**: {video['length']}\n"
                            f"**发布时间**: {publish_time}\n"
                            f"**播放量**: {play_text}"
                        ),
                    },
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🎬 去B站观看"},
                            "url": video["url"],
                            "type": "primary",
                        }
                    ],
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": f"BVID: {video['bvid']}",
                        }
                    ],
                },
            ],
        },
    }

    resp = requests.post(webhook_url, json=card, timeout=10)
    resp.raise_for_status()
    result = resp.json()
    if result.get("code") == 0 or result.get("StatusCode") == 0:
        log.info("飞书通知已发送: [%s] %s", video["author"], video["title"])
    else:
        log.warning("飞书发送异常: %s", result)


def check_all_ups(webhook_url: str):
    """主流程：检查所有UP主的新视频并发送通知。"""
    state = load_state()
    notified = set(state.get("notified_bvids", []))
    is_first_run = len(notified) == 0
    new_count = 0

    for uid, name in UP_LIST.items():
        log.info("检查UP主: %s (UID: %s)", name, uid)
        try:
            videos = get_latest_videos(uid)
        except requests.RequestException as e:
            log.error("获取 %s 的视频列表失败: %s", name, e)
            continue

        if not videos:
            log.info("  未获取到视频")
            continue

        log.info("  获取到 %d 个视频", len(videos))

        for video in videos:
            bvid = video["bvid"]
            if not bvid:
                continue
            if bvid in notified:
                continue

            if is_first_run:
                # 首次运行只记录，不发通知
                log.info("  [首次记录] %s", video["title"])
            else:
                log.info("  [新视频] %s", video["title"])
                try:
                    send_feishu_notification(webhook_url, video)
                    new_count += 1
                except requests.RequestException as e:
                    log.error("  发送飞书通知失败: %s", e)
                    continue

            notified.add(bvid)

    # 保存状态，最多保留 500 条
    state["notified_bvids"] = list(notified)[-500:]
    save_state(state)

    if is_first_run:
        log.info("首次运行完成，已记录 %d 个现有视频，下次运行将检测新视频", len(notified))
    else:
        log.info("检查完成，共发送 %d 条新视频通知", new_count)


# ==================== 入口 ====================


def main():
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL")

    if not webhook_url:
        log.error("请设置环境变量 FEISHU_WEBHOOK_URL")
        log.error("获取方式: 飞书群 -> 设置 -> 群机器人 -> 添加自定义机器人 -> 复制 Webhook 地址")
        sys.exit(1)

    log.info("=" * 50)
    log.info("B站新视频监控 - 开始检查")
    log.info("监控UP主: %s", "、".join(UP_LIST.values()))
    log.info("=" * 50)

    check_all_ups(webhook_url)

    log.info("本次运行结束")


if __name__ == "__main__":
    main()
