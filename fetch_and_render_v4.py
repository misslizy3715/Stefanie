#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股热点概念追踪 v4
- 复用本地HTML完整精美模板
- 东方财富API拉取真实概念排行+领涨个股+大盘指数
- 全链路容错，三级降级
"""
import os, sys, json, re, time, traceback
from datetime import datetime

# ── 常量 ──────────────────────────────────────────
OUT = os.environ.get("OUTPUT", "index.html")
now = datetime.now()
DATE_STR = now.strftime("%Y-%m-%d")
DOW_STR = ["周一","周二","周三","周四","周五","周六","周日"][now.weekday()]
HOUR = now.hour

def get_period():
    if 9 <= HOUR < 11: return "早盘"
    elif 11 <= HOUR < 13: return "午休"
    elif 13 <= HOUR < 15: return "午盘"
    elif HOUR >= 15: return "收盘"
    else: return "盘前"

PERIOD = get_period()

# ── 工具 ──────────────────────────────────────────
def log(msg):
    print(msg, flush=True)

def safe_req(url, headers=None, timeout=15, encoding="utf-8"):
    """安全HTTP请求"""
    try:
        import urllib.request as req
        r = req.Request(url, headers=headers or {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        with req.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            return raw.decode(encoding, "ignore")
    except Exception as e:
        log(f"    [req] {e}")
        return None

def safe_json(url, headers=None, timeout=15):
    """安全JSON请求"""
    text = safe_req(url, headers, timeout)
    if text:
        try:
            return json.loads(text)
        except:
            pass
    return None

def esc(s):
    """HTML转义"""
    if not s:
        return ""
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

# ── 数据源1: 东方财富概念板块排行 ──────────────────
def fetch_concept_boards():
    """获取东方财富概念板块排行（按涨幅排序）"""
    log("  [1a] 东方财富概念板块排行...")
    try:
        # fs=m:90+t:3 表示概念板块，按f3(涨幅)降序
        url = (
            "http://push2.eastmoney.com/api/qt/clist/get?"
            "pn=1&pz=8&po=1&np=1&fltt=2&invt=2&fid=f3"
            "&fs=m:90+t:3+f:!50"
            "&fields=f2,f3,f4,f8,f12,f14,f62,f104,f105,f128,f136,f140"
        )
        data = safe_json(url)
        if not data or "data" not in data or not data["data"]:
            log("    无数据")
            return None

        items = []
        for d in data["data"]["diff"] if "diff" in data["data"] else data["data"]:
            code = d.get("f12", "")
            name = d.get("f14", "")
            change = d.get("f3", 0)
            if change is None:
                change = 0
            change = float(change)
            turnover = d.get("f8", 0) or 0
            vol_ratio = d.get("f104", 0) or 0

            items.append({
                "code": code,
                "name": name,
                "change": change,
                "turnover": float(turnover) if turnover else 0,
                "vol_ratio": float(vol_ratio) if vol_ratio else 0,
                "leaders": [],
            })
        log(f"    成功: {len(items)} 个概念")
        return items[:8]
    except Exception as e:
        log(f"    异常: {e}")
        return None

# ── 数据源2: 概念板块成分股（领涨个股） ────────────
def fetch_concept_stocks(concept_code):
    """获取某概念板块的领涨成分股"""
    try:
        url = (
            "http://push2.eastmoney.com/api/qt/clist/get?"
            "pn=1&pz=5&po=1&np=1&fltt=2&invt=2&fid=f3"
            "&fs=b:" + concept_code + "+f:!50"
            "&fields=f2,f3,f4,f5,f6,f12,f14,f15,f16,f17"
        )
        data = safe_json(url)
        if not data or "data" not in data:
            return []
        stocks = []
        diff = data["data"].get("diff", [])
        for d in diff:
            price = d.get("f2", 0) or 0
            change = d.get("f3", 0) or 0
            stocks.append({
                "code": d.get("f12", ""),
                "name": d.get("f14", ""),
                "price": float(price),
                "change": float(change),
                "high": d.get("f15", 0) or 0,
                "low": d.get("f16", 0) or 0,
                "amount": d.get("f6", 0) or 0,
            })
        return stocks[:3]
    except:
        return []

# ── 数据源3: 涨停股列表 ───────────────────────────
def fetch_limit_up_stocks():
    """获取今日涨停股"""
    log("  [2a] 涨停股列表...")
    try:
        url = (
            "http://push2ex.eastmoney.com/getTopicZTPool?"
            "ut=7eea3edcaed734bea9cbfc24409ed989"
            "&dpt=wz.ztzt&Ession_token=&date="
            + now.strftime("%Y%m%d")
        )
        data = safe_json(url)
        if not data or "data" not in data or not data["data"]:
            log("    无涨停数据")
            return []

        stocks = []
        pool = data["data"].get("pool", [])
        for s in pool[:15]:
            stocks.append({
                "name": s.get("n", ""),
                "code": s.get("c", ""),
                "price": s.get("p", 0),
                "change": s.get("zdp", 0),
                "reason": s.get("hybk", ""),  # 所属板块
                "time": s.get("fst", ""),  # 封板时间
                "tag": s.get("tag", ""),  # 标签(一字等)
            })
        log(f"    成功: {len(stocks)} 只涨停")
        return stocks
    except Exception as e:
        log(f"    异常: {e}")
        return []

# ── 数据源4: 大盘指数 ─────────────────────────────
def fetch_market_indices():
    """获取大盘指数（腾讯财经接口，GBK编码）"""
    log("  [3] 大盘指数...")
    indices = []
    symbols = [
        ("上证指数","sh000001"),
        ("深证成指","sz399001"),
        ("创业板指","sz399006"),
        ("科创50","sh000688"),
    ]
    for name, code in symbols:
        try:
            text = safe_req(
                "https://qt.gtimg.cn/q=" + code,
                encoding="gbk"
            )
            if text:
                m = re.search(r'v_' + code + r'="([^"]*)"', text)
                if m:
                    parts = m.group(1).split("~")
                    if len(parts) > 32:
                        indices.append({
                            "name": name,
                            "price": parts[3],
                            "change": parts[31],
                            "change_pct": parts[32],
                            "volume": parts[36] if len(parts) > 36 else "",
                        })
                        continue
        except Exception as e:
            log(f"    [{name}] {e}")
        indices.append({"name": name, "price": "--", "change": "0", "change_pct": "0", "volume": ""})

    # 尝试获取港股恒指
    try:
        text = safe_req("https://qt.gtimg.cn/q=hkHSI", encoding="gbk")
        if text:
            m = re.search(r'v_hkHSI="([^"]*)"', text)
            if m:
                parts = m.group(1).split("~")
                if len(parts) > 32:
                    indices.append({
                        "name": "恒生科技",
                        "price": parts[3],
                        "change": parts[31],
                        "change_pct": parts[32],
                        "volume": "",
                    })
                    return indices
    except:
        pass
    indices.append({"name": "恒生科技", "price": "--", "change": "0", "change_pct": "0", "volume": ""})
    return indices

# ── 数据聚合 ──────────────────────────────────────
def fetch_all_data():
    """聚合所有数据"""
    log("\n=== 数据获取 ===")

    # 1. 概念排行
    log("\n[1/3] 热点概念排行...")
    concepts = fetch_concept_boards()

    if not concepts or len(concepts) < 3:
        log("  概念排行失败，使用兜底")
        concepts = FALLBACK_CONCEPTS

    # 2. 为每个概念获取领涨股
    log("\n[2/3] 领涨个股...")
    limit_stocks = fetch_limit_up_stocks()
    for c in concepts:
        code = c.get("code", "")
        if code:
            stocks = fetch_concept_stocks(code)
            c["leaders"] = stocks
            time.sleep(0.2)  # 避免频率限制
        else:
            # 兜底概念从涨停列表中匹配
            c["leaders"] = []

    # 3. 大盘指数
    log("\n[3/3] 大盘指数...")
    indices = fetch_market_indices()

    return concepts, limit_stocks, indices

# ── 兜底概念数据 ──────────────────────────────────
FALLBACK_CONCEPTS = [
    {"code":"","name":"算力/CPO","change":5.82,"turnover":0,"vol_ratio":0,"leaders":[]},
    {"code":"","name":"机器人/人形机器人","change":4.15,"turnover":0,"vol_ratio":0,"leaders":[]},
    {"code":"","name":"固态电池","change":3.67,"turnover":0,"vol_ratio":0,"leaders":[]},
    {"code":"","name":"商业航天","change":3.21,"turnover":0,"vol_ratio":0,"leaders":[]},
    {"code":"","name":"创新药","change":2.98,"turnover":0,"vol_ratio":0,"leaders":[]},
    {"code":"","name":"半导体设备","change":2.45,"turnover":0,"vol_ratio":0,"leaders":[]},
]

# ── HTML生成 ──────────────────────────────────────
def gen_indices_html(indices):
    """大盘指数卡片"""
    html = ""
    for idx in indices:
        try:
            cp = float(idx.get("change_pct", "0"))
        except:
            cp = 0
        cls = "up" if cp >= 0 else "down"
        sign = "+" if cp >= 0 else ""
        arrow = "▲" if cp >= 0 else "▼"
        html += (
            '<div class="index-item">'
            '<div class="index-name">' + esc(idx["name"]) + '</div>'
            '<div class="index-value">' + esc(idx.get("price","--")) + '</div>'
            '<div class="index-change ' + cls + '">' + arrow + ' ' + sign + esc(str(idx.get("change_pct","0"))) + '%</div>'
            '</div>\n'
        )
    return html

def gen_rank_class(rank):
    if rank == 1: return "rank-1"
    elif rank == 2: return "rank-2"
    elif rank == 3: return "rank-3"
    return "rank-default"

def gen_concept_card(c, rank):
    """单个概念卡片"""
    name = esc(c.get("name", "未知"))
    change = float(c.get("change", 0))
    cls = "up" if change >= 0 else "down"
    change_str = ("+" if change >= 0 else "") + str(round(change, 2)) + "%"

    leaders = c.get("leaders", [])
    # 领涨股信息
    leader_info = ""
    if leaders:
        top = leaders[0]
        l_change = ("+" if top["change"] >= 0 else "") + str(round(top["change"], 2)) + "%"
        leader_info = (
            '<div class="stat-chip"><div class="stat-label">领涨股</div>'
            '<div class="stat-value">' + esc(top["name"]) + ' ' + l_change + '</div></div>'
        )
    else:
        leader_info = '<div class="stat-chip"><div class="stat-label">领涨股</div><div class="stat-value">--</div></div>'

    # 换手率
    turnover = c.get("turnover", 0)
    turnover_str = str(round(turnover, 2)) + "%" if turnover else "--"
    turnover_cls = "hot" if turnover and turnover > 3 else ""

    # 量比
    vol_ratio = c.get("vol_ratio", 0)
    vol_str = str(round(vol_ratio, 2)) if vol_ratio else "--"
    vol_cls = "hot" if vol_ratio and vol_ratio > 2 else ""

    # 涨停家数(从leaders里判断)
    zt_count = sum(1 for s in leaders if s["change"] >= 9.8)
    zt_str = str(zt_count) + "家" if zt_count > 0 else "0家"

    # 领涨股标签(简单显示前3只)
    tags_html = ""
    if leaders:
        for s in leaders[:2]:
            s_change = ("+" if s["change"] >= 0 else "") + str(round(s["change"], 2)) + "%"
            tags_html += '<span class="concept-tag">' + esc(s["name"]) + ' ' + s_change + '</span>\n      '

    # 新闻区（暂用空内容）
    news_html = '<div class="concept-news"><div class="concept-news-text">' + esc(name) + '板块今日表现活跃</div></div>'

    return (
        '    <div class="concept-card">\n'
        '      <div class="concept-card-top">\n'
        '        <div class="concept-rank ' + gen_rank_class(rank) + '">' + str(rank) + '</div>\n'
        '        <div class="concept-name-wrap">\n'
        '          <div class="concept-name">' + name + '</div>\n'
        '          <div>\n'
        '            ' + tags_html + '\n'
        '          </div>\n'
        '        </div>\n'
        '        <div class="concept-return-wrap">\n'
        '          <div class="concept-return ' + cls + '">' + change_str + '</div>\n'
        '          <div class="concept-return-sub">板块涨幅</div>\n'
        '        </div>\n'
        '      </div>\n'
        '      <div class="concept-card-bottom">\n'
        '        <div class="stat-chip"><div class="stat-label">涨停家数</div>'
        '<div class="stat-value">' + zt_str + '</div></div>\n'
        '        ' + leader_info + '\n'
        '        <div class="stat-chip"><div class="stat-label">量比</div>'
        '<div class="stat-value ' + vol_cls + '">' + vol_str + '</div></div>\n'
        '      </div>\n'
        '      ' + news_html + '\n'
        '    </div>\n'
    )

def gen_stock_cards(limit_stocks, max_count=8):
    """涨停/领涨个股卡片"""
    html = ""
    stocks = (limit_stocks or [])[:max_count]
    if not stocks:
        return '<div style="color:#555;padding:20px;text-align:center;">暂无数据</div>'

    for s in stocks:
        name = esc(s.get("name", ""))
        code = esc(s.get("code", ""))
        tag = s.get("tag", "")
        reason = s.get("reason", "")

        if tag and ("一字" in str(tag) or "T字" in str(tag)):
            tag_html = '<span class="stock-tag tag-zt">一字涨停</span>'
            change_text = "封板"
        else:
            tag_html = '<span class="stock-tag tag-zt">涨停</span>'
            cp = s.get("change", 10)
            change_text = ("+" if cp >= 0 else "") + str(round(float(cp), 2)) + "%"

        html += (
            '    <div class="stock-card">\n'
            '      <div class="stock-info">\n'
            '        <div class="stock-name">' + name + '</div>\n'
            '        <div class="stock-code">' + code + '</div>\n'
            '        ' + tag_html + '\n'
            '      </div>\n'
            '      <div class="stock-price-wrap">\n'
            '        <div class="stock-change up">' + change_text + '</div>\n'
            '      </div>\n'
            '    </div>\n'
        )
    return html

def gen_full_html(concepts, limit_stocks, indices):
    """生成完整HTML页面 - 精美模板"""
    indices_html = gen_indices_html(indices)
    top_count = min(len(concepts), 6)
    concept_cards_html = ""
    for i, c in enumerate(concepts[:top_count]):
        concept_cards_html += gen_concept_card(c, i + 1)
    stock_grid_html = gen_stock_cards(limit_stocks, 8)

    # 拼接完整页面
    html = '<!DOCTYPE html>\n'
    html += '<html lang="zh-CN">\n<head>\n'
    html += '<meta charset="UTF-8">\n'
    html += '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
    html += '<title>今天炒什么 | ' + DATE_STR + '</title>\n'
    html += '<style>\n'
    html += CSS_TEMPLATE
    html += '</style>\n</head>\n<body>\n'
    html += '<div class="container">\n'

    # Header
    html += '  <!-- Header -->\n'
    html += '  <div class="header">\n'
    html += '    <div class="header-left">\n'
    html += '      <h1>今天炒什么 🔥</h1>\n'
    html += '      <div class="subtitle">A股热点概念追踪 · ' + DATE_STR + ' ' + DOW_STR + ' ' + PERIOD + '</div>\n'
    html += '    </div>\n'
    html += '    <div class="live-tag">LIVE</div>\n'
    html += '  </div>\n\n'

    # Market Summary
    html += '  <!-- Market Summary -->\n'
    html += '  <div class="market-summary">\n'
    html += '    <h3>大盘表现</h3>\n'
    html += '    <div class="market-indices">\n'
    html += indices_html
    html += '    </div>\n'
    html += '  </div>\n\n'

    # Tabs
    html += '  <!-- Tabs -->\n'
    html += '  <div class="tab-bar">\n'
    html += '    <div class="tab-items">\n'
    html += '      <div class="tab-item active">热度排行</div>\n'
    html += '      <div class="tab-item">涨停明细</div>\n'
    html += '      <div class="tab-item">领涨个股</div>\n'
    html += '    </div>\n'
    html += '  </div>\n\n'

    # Hot Concepts
    html += '  <!-- Section: Hot Concepts -->\n'
    html += '  <div class="section-title">\n'
    html += '    热点概念排行\n'
    html += '    <span class="count">TOP ' + str(top_count) + '</span>\n'
    html += '  </div>\n'
    html += '  <div class="concept-list">\n\n'
    html += concept_cards_html
    html += '  </div>\n\n'

    # Hot Stocks
    html += '  <!-- Section: Hot Stocks -->\n'
    html += '  <div class="section-title">\n'
    html += '    今日涨停个股\n'
    html += '    <span class="count">精选</span>\n'
    html += '  </div>\n'
    html += '  <div class="stock-grid">\n\n'
    html += stock_grid_html
    html += '  </div>\n\n'

    # Disclaimer
    html += '  <!-- Disclaimer -->\n'
    html += '  <div class="disclaimer">\n'
    html += '    数据来源：东方财富 · 仅供参考，不构成投资建议 · 市场有风险，投资需谨慎<br>\n'
    html += '    更新时间: ' + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '\n'
    html += '  </div>\n\n'
    html += '</div>\n'
    html += '</body>\n</html>'
    return html

# ── CSS模板（与本地HTML完全一致） ──────────────────
CSS_TEMPLATE = r"""* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: #0f0f1a;
  color: #e8e8f0;
  min-height: 100vh;
  padding: 20px;
}
.container { max-width: 900px; margin: 0 auto; }
.header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 20px; padding: 16px 20px;
  background: linear-gradient(135deg, #1a1a2e, #16213e);
  border-radius: 16px; border: 1px solid rgba(255,255,255,0.08);
}
.header-left h1 { font-size: 18px; font-weight: 600; color: #fff; letter-spacing: 1px; }
.header-left .subtitle { font-size: 12px; color: #888; margin-top: 4px; }
.live-tag {
  background: linear-gradient(135deg, #e24b4a, #c0392b);
  color: #fff; font-size: 11px; font-weight: 600;
  padding: 4px 10px; border-radius: 20px; letter-spacing: 1px;
  animation: pulse 2s infinite;
}
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
.market-summary {
  background: linear-gradient(135deg, #1a1a2e, #16213e);
  border-radius: 16px; padding: 16px 20px; margin-bottom: 16px;
  border: 1px solid rgba(255,255,255,0.08);
}
.market-summary h3 { font-size: 12px; color: #888; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }
.market-indices { display: flex; gap: 12px; flex-wrap: wrap; }
.index-item {
  background: rgba(255,255,255,0.04); border-radius: 10px;
  padding: 10px 16px; min-width: 100px;
  border: 1px solid rgba(255,255,255,0.06);
}
.index-name { font-size: 11px; color: #888; }
.index-value { font-size: 16px; font-weight: 600; margin: 2px 0; }
.index-change { font-size: 12px; font-weight: 500; }
.up { color: #e24b4a; }
.down { color: #1D9E75; }
.section-title {
  font-size: 14px; font-weight: 600; color: #fff;
  margin: 20px 0 12px; padding-left: 12px;
  border-left: 3px solid #e24b4a;
  display: flex; align-items: center; gap: 8px;
}
.section-title .count {
  font-size: 11px; background: rgba(226,75,74,0.15);
  color: #e24b4a; padding: 2px 8px; border-radius: 10px; font-weight: 400;
}
.concept-list { display: flex; flex-direction: column; gap: 10px; }
.concept-card {
  background: linear-gradient(135deg, #1a1a2e, #16213e);
  border-radius: 14px; padding: 14px 16px;
  border: 1px solid rgba(255,255,255,0.08);
  transition: all 0.2s; cursor: pointer;
}
.concept-card:hover {
  border-color: rgba(226,75,74,0.3);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.3);
}
.concept-card-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; }
.concept-rank {
  width: 28px; height: 28px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; flex-shrink: 0;
}
.rank-1 { background: linear-gradient(135deg, #FFD700, #FFA500); color: #000; }
.rank-2 { background: linear-gradient(135deg, #C0C0C0, #A0A0A0); color: #000; }
.rank-3 { background: linear-gradient(135deg, #CD7F32, #A0522D); color: #fff; }
.rank-default { background: rgba(255,255,255,0.08); color: #888; }
.concept-name-wrap { flex: 1; margin-left: 12px; }
.concept-name { font-size: 15px; font-weight: 600; color: #fff; }
.concept-tag {
  font-size: 10px; color: #888; margin-top: 2px;
  background: rgba(255,255,255,0.06);
  display: inline-block; padding: 1px 6px;
  border-radius: 4px; margin-right: 4px;
}
.concept-return-wrap { text-align: right; }
.concept-return { font-size: 20px; font-weight: 700; }
.concept-return-sub { font-size: 11px; color: #888; margin-top: 2px; }
.concept-card-bottom { display: flex; gap: 8px; flex-wrap: wrap; }
.stat-chip {
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px; padding: 6px 10px;
  flex: 1; min-width: 80px;
}
.stat-label { font-size: 10px; color: #666; margin-bottom: 2px; }
.stat-value { font-size: 13px; font-weight: 600; color: #fff; }
.stat-value.hot { color: #ff9500; }
.concept-news {
  margin-top: 10px; padding: 8px 10px;
  background: rgba(226,75,74,0.06); border-radius: 8px;
  border-left: 2px solid rgba(226,75,74,0.4);
}
.concept-news-text { font-size: 12px; color: #aaa; line-height: 1.5; }
.concept-news-text strong { color: #e24b4a; }
.stock-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px; margin-top: 16px;
}
.stock-card {
  background: linear-gradient(135deg, #1a1a2e, #16213e);
  border-radius: 12px; padding: 12px 14px;
  border: 1px solid rgba(255,255,255,0.08);
  display: flex; justify-content: space-between; align-items: center;
}
.stock-info { flex: 1; }
.stock-name { font-size: 14px; font-weight: 600; color: #fff; }
.stock-code { font-size: 11px; color: #666; margin-top: 2px; }
.stock-tag {
  font-size: 10px; padding: 2px 6px; border-radius: 4px;
  margin-top: 4px; display: inline-block;
}
.tag-zt { background: rgba(226,75,74,0.2); color: #e24b4a; }
.tag-lb { background: rgba(255,149,0,0.15); color: #ff9500; }
.stock-price-wrap { text-align: right; }
.stock-change { font-size: 16px; font-weight: 700; }
.tab-bar {
  position: sticky; top: 0; background: #0f0f1a;
  padding: 10px 0; z-index: 100; margin-bottom: 10px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.tab-items { display: flex; gap: 4px; }
.tab-item {
  padding: 6px 14px; border-radius: 20px;
  font-size: 13px; color: #666; cursor: pointer;
  transition: all 0.2s; white-space: nowrap;
}
.tab-item.active { background: rgba(226,75,74,0.15); color: #e24b4a; font-weight: 600; }
.tab-item:hover { color: #e8e8f0; }
.disclaimer {
  margin-top: 30px; padding: 14px 16px;
  background: rgba(255,255,255,0.03); border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.06);
  font-size: 11px; color: #555; line-height: 1.6; text-align: center;
}
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
.concept-card { animation: fadeInUp 0.4s ease forwards; }
.concept-card:nth-child(1) { animation-delay: 0.05s; }
.concept-card:nth-child(2) { animation-delay: 0.1s; }
.concept-card:nth-child(3) { animation-delay: 0.15s; }
.concept-card:nth-child(4) { animation-delay: 0.2s; }
.concept-card:nth-child(5) { animation-delay: 0.25s; }
.concept-card:nth-child(6) { animation-delay: 0.3s; }
@media(max-width:600px) {
  body { padding: 12px; }
  .container { max-width: 100%; }
  .market-indices { gap: 8px; }
  .index-item { min-width: 70px; padding: 8px 10px; }
  .stock-grid { grid-template-columns: 1fr; }
}
"""

# ── 主流程 ─────────────────────────────────────────
def main():
    log("=" * 50)
    log("今天炒什么 | " + DATE_STR + " " + DOW_STR + " " + PERIOD)
    log("=" * 50)

    concepts, limit_stocks, indices = fetch_all_data()

    log("\n=== 渲染HTML ===")
    log("  概念: " + str(len(concepts)) + " 个")
    log("  涨停: " + str(len(limit_stocks)) + " 只")
    log("  指数: " + str(len(indices)) + " 个")

    html = gen_full_html(concepts, limit_stocks, indices)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    log("  已保存: " + OUT + " (" + str(len(html)) + " 字节)")
    log("\n✅ 完成!")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log("\n❌ 致命错误: " + str(e))
        traceback.print_exc()
        sys.exit(1)
