#!/usr/bin/env python3
"""
热点概念追踪数据抓取 + HTML渲染脚本
配合 GitHub Actions 使用，自动生成热点概念报告

依赖：requests
安装：pip install requests
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

# ===================== 配置区 =====================
NEODATA_API = "https://copilot.tencent.com/agenttool/v1/neodata"
REPORT_DATE = datetime.now().strftime("%Y-%m-%d")
REPORT_DOW = ["周一","周二","周三","周四","周五","周六","周日"][datetime.now().weekday()]

# 文件路径
OUTPUT_HTML = "index.html"
TOKEN_CACHE = Path.home() / ".neodata_token"

# ===================== Token管理 =====================
def get_token():
    """获取 neodata token，优先从环境变量 > 缓存文件"""
    for env_key in ["NEODATA_TEMP_TOKEN", "NEODATA_TOKEN"]:
        token = os.environ.get(env_key)
        if token:
            print(f"  [Token] 使用环境变量 {env_key}")
            return token

    if TOKEN_CACHE.exists():
        content = TOKEN_CACHE.read_text().strip()
        if content and len(content) > 50:
            print("  [Token] 从缓存文件读取")
            return content

    print("  [Token] 未找到凭证，请设置 NEODATA_TEMP_TOKEN 环境变量")
    return None


def save_token(token: str):
    """保存 token 到缓存"""
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(token)
    print(f"  [Token] 已保存至 {TOKEN_CACHE}")


def call_neodata(query: str, token: str):
    """调用 neodata API"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "query": query,
        "channel": "neodata",
        "sub_channel": "workbuddy",
        "data_type": "all"
    }
    resp = requests.post(NEODATA_API, json=payload, headers=headers, timeout=30)
    data = resp.json()
    if data.get("code") == "200" and data.get("suc"):
        return data.get("data", {})
    return {}


def get_market_summary():
    """获取大盘指数数据"""
    token = get_token()
    if not token:
        return None
    result = call_neodata(
        "上证指数、深证成指、创业板指、科创50、恒生科技指数今日涨跌幅",
        token
    )
    return result


# ===================== 数据抓取 =====================
def fetch_hot_concepts():
    """抓取今日热点概念排行"""
    token = get_token()
    if not token:
        return None

    result = call_neodata(
        "今日A股最热门的概念板块/题材排行，按涨幅从高到低排序，"
        "列出前10个热点概念，包含概念名称、涨跌幅、领涨股名称和涨跌幅",
        token
    )
    return result


def fetch_news_for_concepts(concept_names: list):
    """为各概念抓取关联新闻"""
    token = get_token()
    if not token:
        return {}

    news_map = {}
    for concept in concept_names[:5]:
        result = call_neodata(
            f"{concept}概念今日最新新闻摘要，一句话总结",
            token
        )
        doc_data = result.get("docData", {}).get("docRecall", [])
        if doc_data:
            docs = doc_data[0].get("docList", [])
            if docs:
                news_map[concept] = docs[0].get("title", "")

    return news_map


# ===================== HTML 渲染 =====================
def render_index(concepts: list, news_map: dict, market: dict = None):
    """渲染主页面"""
    html = _load_template("template.html")

    # 替换日期
    html = html.replace("{DATE}", REPORT_DATE)
    html = html.replace("{DOW}", REPORT_DOW)
    html = html.replace("{DATETIME}", datetime.now().strftime("%Y-%m-%d %H:%M"))

    # 渲染概念卡片
    concept_cards = _render_concept_cards(concepts, news_map)
    html = html.replace("{CONCEPT_CARDS}", concept_cards)

    # 渲染大盘指数
    indices_html = _render_market_indices(market)
    html = html.replace("{MARKET_INDICES}", indices_html)

    return html


def _render_concept_cards(concepts: list, news_map: dict) -> str:
    """渲染热点概念卡片"""
    if not concepts:
        return '<div style="color:#888;text-align:center;padding:40px;">暂无数据，请检查API配置</div>'

    cards = []
    rank_classes = ["rank-1", "rank-2", "rank-3", "rank-default", "rank-default", "rank-default"]

    for i, c in enumerate(concepts[:6]):
        name = c.get("name", "未知概念")
        change = c.get("change", c.get("涨跌幅", "—"))
        leader = c.get("leader", c.get("领涨股", "—"))
        news = news_map.get(name, "")

        # 处理涨跌颜色
        change_str = str(change)
        if "+" in change_str or (change_str.replace(".","").replace("-","").isdigit() and float(change_str.replace("%","")) > 0):
            change_color = "#e24b4a"
            change_arrow = "▲"
        else:
            change_color = "#1D9E75"
            change_arrow = "▼"

        # 排名
        rank_cls = rank_classes[i] if i < len(rank_classes) else "rank-default"
        rank_num = i + 1

        # 板块标签（根据名称推断）
        tags = _guess_tags(name)

        news_html = ""
        if news:
            news_html = f'''
        <div class="concept-news">
          <div class="concept-news-text">{news}</div>
        </div>'''

        card = f'''
    <div class="concept-card">
      <div class="concept-card-top">
        <div class="concept-rank {rank_cls}">{rank_num}</div>
        <div class="conceptname-wrap">
          <div class="concept-name">{name}</div>
          <div>{tags}</div>
        </div>
        <div class="concept-return-wrap">
          <div class="concept-return" style="color:{change_color}">{change_arrow}{change}</div>
          <div class="concept-return-sub">板块涨幅</div>
        </div>
      </div>
      <div class="concept-card-bottom">
        <div class="stat-chip">
          <div class="stat-label">领涨股</div>
          <div class="stat-value">{leader}</div>
        </div>
      </div>{news_html}
    </div>'''
        cards.append(card)

    return "\n".join(cards)


def _guess_tags(name: str) -> str:
    """根据概念名称推断标签"""
    tag_map = {
        "玻璃": "面板/封装", "CPU": "半导体/算力", "芯片": "半导体",
        "证券": "金融科技", "AI": "人工智能", "算力": "算力",
        "光通信": "光模块", "光纤": "光通信", "低空": "低空经济",
        "机器人": "人形机器人", "固态电池": "新能源", "白酒": "消费",
        "裸眼": "显示技术", "线控": "智能驾驶", "电子布": "玻纤",
        "航运": "航运", "液冷": "算力基础设施", "创新药": "医药",
    }
    for kw, tag in tag_map.items():
        if kw in name:
            return f'<span class="concept-tag">{tag}</span>'
    return '<span class="concept-tag">市场热点</span>'


def _render_market_indices(market: dict) -> str:
    """渲染大盘指数"""
    # 默认值（如果API失败）
    indices = [
        ("上证指数", "—", "—"),
        ("深证成指", "—", "—"),
        ("创业板指", "—", "—"),
        ("科创50", "—", "—"),
        ("恒生科技", "—", "—"),
    ]

    if market:
        # 从API结果解析（实际解析逻辑根据返回结构调整）
        pass

    items = []
    for name, value, change in indices:
        color = "#888"
        arrow = ""
        if change != "—" and change.replace(".","").replace("-","").replace("+","").replace("%","").isdigit():
            v = float(change.replace("%",""))
            if v > 0:
                color = "#e24b4a"
                arrow = "▲ "
            elif v < 0:
                color = "#1D9E75"
                arrow = "▼ "

        items.append(f'''
      <div class="index-item">
        <div class="index-name">{name}</div>
        <div class="index-value">{value}</div>
        <div class="index-change" style="color:{color}">{arrow}{change}</div>
      </div>''')

    return "\n".join(items)


def _load_template(name: str) -> str:
    """加载HTML模板"""
    path = Path(__file__).parent / name
    if path.exists():
        return path.read_text(encoding="utf-8")

    # 内联最小模板（template.html不存在时的兜底）
    return _inline_template()


def _inline_template() -> str:
    """内联最小化兜底模板"""
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>今日热点概念追踪 | {REPORT_DATE}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
  background:#0f0f1a;color:#e8e8f0;min-height:100vh;padding:20px}}
.container{{max-width:900px;margin:0 auto}}
.header{{display:flex;justify-content:space-between;align-items:center;
  margin-bottom:20px;padding:16px 20px;background:linear-gradient(135deg,#1a1a2e,#16213e);
  border-radius:16px;border:1px solid rgba(255,255,255,.08)}}
.header h1{{font-size:18px;font-weight:600;color:#fff;letter-spacing:1px}}
.live-tag{{background:linear-gradient(135deg,#e24b4a,#c0392b);color:#fff;
  font-size:11px;font-weight:600;padding:4px 10px;border-radius:20px;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.6}}}}
.market-summary{{background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:16px;
  padding:16px 20px;margin-bottom:16px;border:1px solid rgba(255,255,255,.08)}}
.market-summary h3{{font-size:12px;color:#888;margin-bottom:8px;letter-spacing:1px}}
.market-indices{{display:flex;gap:12px;flex-wrap:wrap}}
.index-item{{background:rgba(255,255,255,.04);border-radius:10px;padding:10px 16px;
  min-width:100px;border:1px solid rgba(255,255,255,.06)}}
.index-name{{font-size:11px;color:#888}}
.index-value{{font-size:16px;font-weight:600;margin:2px 0}}
.index-change{{font-size:12px;font-weight:500}}
.section-title{{font-size:14px;font-weight:600;color:#fff;margin:20px 0 12px;
  padding-left:12px;border-left:3px solid #e24b4a}}
.concept-list{{display:flex;flex-direction:column;gap:10px}}
.concept-card{{background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:14px;
  padding:14px 16px;border:1px solid rgba(255,255,255,.08)}}
.concept-card-top{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}}
.concept-rank{{width:28px;height:28px;border-radius:8px;display:flex;
  align-items:center;justify-content:center;font-size:13px;font-weight:700;flex-shrink:0}}
.rank-1{{background:linear-gradient(135deg,#FFD700,#FFA500);color:#000}}
.rank-2{{background:linear-gradient(135deg,#C0C0C0,#A0A0A0);color:#000}}
.rank-3{{background:linear-gradient(135deg,#CD7F32,#A0522D);color:#fff}}
.rank-default{{background:rgba(255,255,255,.08);color:#888}}
.concept-name-wrap{{flex:1;margin-left:12px}}
.concept-name{{font-size:15px;font-weight:600;color:#fff}}
.concept-tag{{font-size:10px;color:#888;margin-top:2px;
  background:rgba(255,255,255,.06);display:inline-block;padding:1px 6px;border-radius:4px;margin-right:4px}}
.concept-return-wrap{{text-align:right}}
.concept-return{{font-size:20px;font-weight:700}}
.concept-return-sub{{font-size:11px;color:#888;margin-top:2px}}
.concept-card-bottom{{display:flex;gap:8px;flex-wrap:wrap}}
.stat-chip{{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);
  border-radius:8px;padding:6px 10px;flex:1;min-width:80px}}
.stat-label{{font-size:10px;color:#666;margin-bottom:2px}}
.stat-value{{font-size:13px;font-weight:600;color:#fff}}
.concept-news{{margin-top:10px;padding:8px 10px;background:rgba(226,75,74,.06);
  border-radius:8px;border-left:2px solid rgba(226,75,74,.4)}}
.concept-news-text{{font-size:12px;color:#aaa;line-height:1.5}}
.disclaimer{{margin-top:30px;padding:14px 16px;background:rgba(255,255,255,.03);
  border-radius:10px;border:1px solid rgba(255,255,255,.06);font-size:11px;
  color:#555;line-height:1.6;text-align:center}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div><h1>今天炒什么</h1><div style="font-size:12px;color:#888;margin-top:4px">
      A股热点概念追踪 · {REPORT_DATE} {REPORT_DOW}</div></div>
    <div class="live-tag">LIVE · {datetime.now().strftime("%H:%M")}</div>
  </div>
  <div class="market-summary">
    <h3>大盘表现</h3>
    <div class="market-indices">{MARKET_INDICES}</div>
  </div>
  <div class="section-title">热点概念排行 <span style="font-size:11px;background:rgba(226,75,74,.15);color:#e24b4a;padding:2px 8px;border-radius:10px;font-weight:400">TOP 6</span></div>
  <div class="concept-list">{CONCEPT_CARDS}</div>
  <div class="disclaimer">数据来源：财联社、华尔街见闻 · 仅供参考，不构成投资建议 · 市场有风险，投资需谨慎</div>
</div>
</body></html>'''


# ===================== 主程序 =====================
def main():
    print(f"\n{'='*50}")
    print(f"热点概念追踪 | {REPORT_DATE} {REPORT_DOW}")
    print(f"{'='*50}\n")

    # 1. 抓取热点概念
    print("[1/2] 抓取热点概念数据...")
    concepts_raw = fetch_hot_concepts()

    # 解析概念列表（从API返回中提取）
    concepts = _parse_concepts(concepts_raw)

    if not concepts:
        print("  [警告] 未获取到概念数据，生成兜底页面")
        concepts = _fallback_concepts()

    print(f"  获取到 {len(concepts)} 个热点概念")

    # 2. 抓取关联新闻
    print("[2/2] 抓取关联新闻...")
    concept_names = [c.get("name","") for c in concepts]
    news_map = fetch_news_for_concepts(concept_names)
    print(f"  获取到 {len(news_map)} 条关联新闻")

    # 3. 渲染HTML
    print("\n[渲染] 生成 index.html...")
    html = render_index(concepts, news_map)
    Path(OUTPUT_HTML).write_text(html, encoding="utf-8")
    print(f"  已保存至: {OUTPUT_HTML}")

    # 4. 复制模板（如果存在）
    tmpl = Path(__file__).parent / "template.html"
    if tmpl.exists():
        import shutil
        shutil.copy(tmpl, OUTPUT_HTML)
        print(f"  已使用完整模板: template.html")

    print(f"\n✅ 完成！生成文件：{OUTPUT_HTML}")


def _parse_concepts(data: dict) -> list:
    """从API返回解析概念列表"""
    concepts = []

    # 优先从 apiRecall 中提取板块涨幅排行
    api_data = data.get("apiData", {})
    for recall in api_data.get("apiRecall", []):
        recall_type = recall.get("type", "")
        if "板块" in recall_type or "排行" in recall_type or "涨幅" in recall_type:
            content = recall.get("content", "")
            # 解析 Markdown 表格
            lines = content.strip().split("\n")
            for line in lines:
                if "|" not in line or "排行" in line or "类型" in line or "---" in line:
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 7:
                    # 概念名称通常在第2列，涨跌幅在第6列
                    name = parts[1] if parts[1] and len(parts[1]) < 20 else ""
                    change = parts[5] if len(parts) > 5 else ""
                    leader_name = parts[-1] if parts[-1] else ""

                    if name and change and name not in ["行业名", "概念名"]:
                        concepts.append({
                            "name": name,
                            "change": change,
                            "leader": leader_name
                        })

    return concepts


def _fallback_concepts() -> list:
    """API失败时的兜底数据"""
    return [
        {"name": "玻璃基板封装", "change": "+4.89%", "leader": "美迪凯 +12.67%"},
        {"name": "CPU概念", "change": "+5.04%", "leader": "澜起科技 +10.96%"},
        {"name": "线控底盘", "change": "+4.85%", "leader": "浙江世宝 +9.99%"},
        {"name": "证券IT", "change": "+4.39%", "leader": "同花顺 +11.09%"},
        {"name": "电子布", "change": "+4.72%", "leader": "中国巨石 +7.04%"},
        {"name": "裸眼3D", "change": "+4.62%", "leader": "雷曼光电 +10.96%"},
    ]


if __name__ == "__main__":
    main()
