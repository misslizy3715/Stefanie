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
EASTMONEY_TOPIC_API = "https://push2ex.eastmoney.com/getTopicZDF"
REPORT_DATE = datetime.now().strftime("%Y-%m-%d")
REPORT_DOW = ["周一","周二","周三","周四","周五","周六","周日"][datetime.now().weekday()]

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

    print("  [Token] 未找到 neodata 凭证")
    return None


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
    try:
        resp = requests.post(NEODATA_API, json=payload, headers=headers, timeout=30)
        data = resp.json()
        if data.get("code") == "200" and data.get("suc"):
            return data.get("data", {})
    except Exception as e:
        print(f"  [neodata] 调用失败: {e}")
    return {}


def fetch_from_eastmoney():
    """从东方财富获取概念板块涨幅排行（备选数据源）"""
    try:
        url = (
            f"{EASTMONEY_TOPIC_API}"
            f"?ut=7eea3edcaed734bea9cbfc24409ed989"
            f"&dpt=wz.ztzt&Pageindex=0&pagesize=20"
            f"&sort=fbt:asc&date={datetime.now().strftime('%Y%m%d')}"
        )
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        data = resp.json()
        topics = data.get("data", {}).get("topic", [])
        concepts = []
        for t in topics[:10]:
            name = t.get("f14", "")
            change = t.get("f3", "")
            leader = t.get("f20", "")  # 领涨股
            if name and change:
                # 格式化涨跌幅
                try:
                    change_val = float(change)
                    change_str = f"{change_val:+.2f}%"
                except:
                    change_str = str(change)
                concepts.append({
                    "name": name,
                    "change": change_str,
                    "leader": leader if leader else "—"
                })
        return concepts
    except Exception as e:
        print(f"  [eastmoney] 调用失败: {e}")
        return []


# ===================== 数据抓取 =====================
def fetch_hot_concepts():
    """抓取今日热点概念排行，先尝试neodata，失败用东方财富"""
    token = get_token()
    if token:
        print("[1/2] 尝试 neodata 数据源...")
        result = call_neodata(
            "今日A股最热门的概念板块/题材排行，按涨幅从高到低排序，"
            "列出前10个热点概念，包含概念名称、涨跌幅、领涨股名称和涨跌幅",
            token
        )
        concepts = _parse_concepts(result)
        if concepts:
            print(f"  从 neodata 获取到 {len(concepts)} 个概念")
            return concepts
        print("  neodata 无数据，尝试备选数据源...")
    else:
        print("[1/2] 无 neodata token，使用备选数据源...")

    print("  尝试东方财富概念排行...")
    concepts = fetch_from_eastmoney()
    if concepts:
        print(f"  从东方财富获取到 {len(concepts)} 个概念")
        return concepts

    print("  所有数据源均失败，使用兜底数据")
    return _fallback_concepts()


def fetch_news_for_concepts(concept_names: list):
    """为各概念抓取关联新闻"""
    token = get_token()
    if not token:
        return {}

    news_map = {}
    for concept in concept_names[:5]:
        try:
            result = call_neodata(
                f"{concept}概念今日最新新闻摘要，一句话总结",
                token
            )
            doc_data = result.get("docData", {}).get("docRecall", [])
            if doc_data:
                docs = doc_data[0].get("docList", [])
                if docs:
                    news_map[concept] = docs[0].get("title", "")
        except Exception:
            pass
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
        color = "#888"
        arrow = ""
        try:
            val = float(change_str.replace("%", "").replace("+", ""))
            if val > 0:
                color = "#e24b4a"
                arrow = "▲"
            elif val < 0:
                color = "#1D9E75"
                arrow = "▼"
        except:
            pass

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
        <div class="concept-name-wrap">
          <div class="concept-name">{name}</div>
          <div>{tags}</div>
        </div>
        <div class="concept-return-wrap">
          <div class="concept-return" style="color:{color}">{arrow}{change}</div>
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
        "铜缆": "高速连接", "稀土": "稀土永磁", "黄金": "贵金属",
    }
    for kw, tag in tag_map.items():
        if kw in name:
            return f'<span class="concept-tag">{tag}</span>'
    return '<span class="concept-tag">市场热点</span>'


def _render_market_indices(market: dict) -> str:
    """渲染大盘指数"""
    # 尝试从东方财富获取大盘实时数据
    indices_data = []
    try:
        url = "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688,hkHSTECH"
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        text = resp.text
        # 解析腾讯行情数据格式
        matches = re.findall(r'v_\w+="([^"]+)"', text)
        names = ["上证指数", "深证成指", "创业板指", "科创50", "恒生科技"]
        for i, match in enumerate(matches[:5]):
            parts = match.split("~")
            if len(parts) >= 5:
                name = names[i] if i < len(names) else parts[1]
                value = parts[3]
                change_pct = parts[5]
                indices_data.append((name, value, change_pct))
    except Exception as e:
        print(f"  [大盘] 获取失败: {e}")

    # 兜底默认值
    if not indices_data:
        indices_data = [
            ("上证指数", "—", "—"),
            ("深证成指", "—", "—"),
            ("创业板指", "—", "—"),
            ("科创50", "—", "—"),
            ("恒生科技", "—", "—"),
        ]

    items = []
    for name, value, change in indices_data:
        color = "#888"
        arrow = ""
        try:
            v = float(str(change).replace("%", ""))
            if v > 0:
                color = "#e24b4a"
                arrow = "▲ "
            elif v < 0:
                color = "#1D9E75"
                arrow = "▼ "
        except:
            pass

        items.append(f'''
      <div class="index-item">
        <div class="index-name">{name}</div>
        <div class="index-value">{value}</div>
        <div class="index-change" style="color:{color}">{arrow}{change}</div>
      </div>''')

    return "\n".join(items)


def _load_template(name: str) -> str:
    """加载HTML模板：优先使用带占位符的template.html，否则用内联模板"""
    path = Path(__file__).parent / name
    if path.exists():
        content = path.read_text(encoding="utf-8")
        # 检查是否包含关键占位符
        if "{CONCEPT_CARDS}" in content and "{DATE}" in content:
            print("  [模板] 使用 template.html（含占位符）")
            return content
        # template.html 没有占位符（是静态页面），忽略它
        print("  [模板] template.html 不含占位符，使用内联模板")
    else:
        print("  [模板] template.html 不存在，使用内联模板")
    return _inline_template()


def _inline_template() -> str:
    """内联完整模板（兜底）"""
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>今日热点概念追踪 | {REPORT_DATE}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
  background:#0a0a1a;color:#e8e8f0;min-height:100vh;padding:16px}}
.container{{max-width:720px;margin:0 auto}}
.header{{display:flex;justify-content:space-between;align-items:center;
  margin-bottom:16px;padding:14px 18px;background:linear-gradient(135deg,#141428,#0f1a2e);
  border-radius:14px;border:1px solid rgba(255,255,255,.06)}}
.header h1{{font-size:18px;font-weight:700;color:#fff;letter-spacing:1px}}
.header .subtitle{{font-size:12px;color:#888;margin-top:3px}}
.live-tag{{background:linear-gradient(135deg,#e24b4a,#c0392b);color:#fff;
  font-size:11px;font-weight:600;padding:4px 10px;border-radius:20px;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.6}}}}
.market-summary{{background:linear-gradient(135deg,#141428,#0f1a2e);border-radius:14px;
  padding:14px 18px;margin-bottom:14px;border:1px solid rgba(255,255,255,.06)}}
.market-summary h3{{font-size:12px;color:#888;margin-bottom:8px;letter-spacing:1px}}
.market-indices{{display:flex;gap:10px;flex-wrap:wrap}}
.index-item{{background:rgba(255,255,255,.04);border-radius:10px;padding:10px 14px;
  flex:1;min-width:90px;border:1px solid rgba(255,255,255,.06);text-align:center}}
.index-name{{font-size:11px;color:#888}}
.index-value{{font-size:16px;font-weight:600;margin:2px 0;color:#fff}}
.index-change{{font-size:12px;font-weight:500}}
.section-title{{font-size:15px;font-weight:700;color:#fff;margin:18px 0 10px;
  padding-left:12px;border-left:3px solid #e24b4a;display:flex;align-items:center;gap:8px}}
.top-badge{{font-size:11px;background:rgba(226,75,74,.15);color:#e24b4a;
  padding:2px 8px;border-radius:10px;font-weight:500}}
.concept-list{{display:flex;flex-direction:column;gap:10px}}
.concept-card{{background:linear-gradient(135deg,#141428,#0f1a2e);border-radius:14px;
  padding:14px 16px;border:1px solid rgba(255,255,255,.06);transition:transform .2s}}
.concept-card:hover{{transform:translateY(-2px)}}
.concept-card-top{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}}
.concept-rank{{width:30px;height:30px;border-radius:8px;display:flex;
  align-items:center;justify-content:center;font-size:13px;font-weight:700;flex-shrink:0}}
.rank-1{{background:linear-gradient(135deg,#FFD700,#FFA500);color:#000}}
.rank-2{{background:linear-gradient(135deg,#C0C0C0,#A0A0A0);color:#000}}
.rank-3{{background:linear-gradient(135deg,#CD7F32,#A0522D);color:#fff}}
.rank-default{{background:rgba(255,255,255,.08);color:#888}}
.concept-name-wrap{{flex:1;margin-left:12px}}
.concept-name{{font-size:15px;font-weight:600;color:#fff}}
.concept-tag{{font-size:10px;color:#aaa;margin-top:3px;
  background:rgba(255,255,255,.06);display:inline-block;padding:2px 8px;border-radius:4px;margin-right:4px}}
.concept-return-wrap{{text-align:right}}
.concept-return{{font-size:20px;font-weight:700}}
.concept-return-sub{{font-size:11px;color:#888;margin-top:2px}}
.concept-card-bottom{{display:flex;gap:8px;flex-wrap:wrap}}
.stat-chip{{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);
  border-radius:8px;padding:6px 10px;flex:1;min-width:80px}}
.stat-label{{font-size:10px;color:#666;margin-bottom:2px}}
.stat-value{{font-size:13px;font-weight:600;color:#fff}}
.concept-news{{margin-top:10px;padding:8px 12px;background:rgba(226,75,74,.06);
  border-radius:8px;border-left:2px solid rgba(226,75,74,.4)}}
.concept-news-text{{font-size:12px;color:#aaa;line-height:1.5}}
.disclaimer{{margin-top:24px;padding:12px 16px;background:rgba(255,255,255,.03);
  border-radius:10px;border:1px solid rgba(255,255,255,.06);font-size:11px;
  color:#555;line-height:1.6;text-align:center}}
.update-time{{text-align:center;font-size:11px;color:#555;margin-top:8px}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>今天炒什么</h1>
      <div class="subtitle">A股热点概念追踪 · {DATE} {DOW}</div>
    </div>
    <div class="live-tag">LIVE · {DATETIME}</div>
  </div>
  <div class="market-summary">
    <h3>大盘表现</h3>
    <div class="market-indices">{MARKET_INDICES}</div>
  </div>
  <div class="section-title">
    热点概念排行 <span class="top-badge">TOP 6</span>
  </div>
  <div class="concept-list">{CONCEPT_CARDS}</div>
  <div class="disclaimer">
    数据来源：财联社、东方财富、华尔街见闻 · 仅供参考，不构成投资建议 · 市场有风险，投资需谨慎
  </div>
  <div class="update-time">更新时间：{DATETIME}</div>
</div>
</body></html>'''


# ===================== 数据解析 =====================
def _parse_concepts(data: dict) -> list:
    """从API返回解析概念列表"""
    concepts = []
    if not data:
        return concepts

    # 优先从 apiRecall 中提取板块涨幅排行
    api_data = data.get("apiData", {})
    for recall in api_data.get("apiRecall", []):
        recall_type = recall.get("type", "")
        if "板块" in recall_type or "排行" in recall_type or "涨幅" in recall_type:
            content = recall.get("content", "")
            lines = content.strip().split("\n")
            for line in lines:
                if "|" not in line or "排行" in line or "类型" in line or "---" in line:
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 7:
                    name = parts[1] if parts[1] and len(parts[1]) < 20 else ""
                    change = parts[5] if len(parts) > 5 else ""
                    leader_name = parts[-1] if parts[-1] else ""
                    if name and change and name not in ["行业名", "概念名", ""]:
                        concepts.append({
                            "name": name,
                            "change": change,
                            "leader": leader_name
                        })

    # 备选：从 docRecall 中解析
    if not concepts:
        for recall in api_data.get("docRecall", []):
            docs = recall.get("docList", [])
            for doc in docs[:6]:
                title = doc.get("title", "")
                # 尝试从标题中提取概念和涨幅
                match = re.search(r'(.+?)\s*([\+\-]?\d+\.?\d*)%', title)
                if match:
                    concepts.append({
                        "name": match.group(1).strip(),
                        "change": f"{match.group(2)}%",
                        "leader": "—"
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


# ===================== 主程序 =====================
def main():
    print(f"\n{'='*50}")
    print(f"热点概念追踪 | {REPORT_DATE} {REPORT_DOW}")
    print(f"{'='*50}\n")

    # 1. 抓取热点概念
    concepts = fetch_hot_concepts()
    print(f"  最终获取到 {len(concepts)} 个热点概念\n")

    # 2. 抓取关联新闻（neodata可用时）
    print("[2/2] 抓取关联新闻...")
    concept_names = [c.get("name","") for c in concepts]
    news_map = fetch_news_for_concepts(concept_names)
    print(f"  获取到 {len(news_map)} 条关联新闻\n")

    # 3. 渲染HTML
    print("[渲染] 生成 index.html...")
    html = render_index(concepts, news_map)
    Path(OUTPUT_HTML).write_text(html, encoding="utf-8")
    print(f"  已保存至: {OUTPUT_HTML}")

    # 不再覆盖！删除之前的 shutil.copy 逻辑
    print(f"\n✅ 完成！生成文件：{OUTPUT_HTML}")


if __name__ == "__main__":
    main()
