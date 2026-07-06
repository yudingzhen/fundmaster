"""
基金匹配引擎 — 四相淘汰 + 加权匹配
数据来源：天天基金（公开免费）
"""

import sys, os

import requests, json, re, os, math, time, random
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
FUND_CACHE = os.path.join(DATA_DIR, "fund_cache.json")
DETAIL_DIR = os.path.join(DATA_DIR, "details")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DETAIL_DIR, exist_ok=True)

# ============ 数据源 ============

def load_fund_list(force_refresh=False):
    """加载全市场基金列表，缓存 24h"""
    if not force_refresh and os.path.exists(FUND_CACHE):
        age = time.time() - os.path.getmtime(FUND_CACHE)
        if age < 86400:
            with open(FUND_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)

    print("  [数据] 更新基金列表...", end=" ")
    url = "http://fund.eastmoney.com/js/fundcode_search.js"
    r = requests.get(url, timeout=15)
    r.encoding = "utf-8"
    text = r.text
    start, end = text.find("["), text.rfind("]") + 1
    if start == -1:
        return {}

    data = json.loads(text[start:end])
    funds = {}
    for item in data:
        code, pinyin, name, ftype, full_pinyin = item
        funds[code] = {"name": name, "type": ftype}

    with open(FUND_CACHE, "w", encoding="utf-8") as f:
        json.dump(funds, f, ensure_ascii=False)
    print(f"{len(funds)} 只基金")
    return funds


def get_detail_path(code):
    return os.path.join(DETAIL_DIR, f"{code}.json")


def fetch_fund_detail(code):
    """拉取单只基金完整数据（带缓存，24h有效）"""
    cache_path = get_detail_path(code)

    # 检查缓存
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < 86400:  # 24h
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)

    # 从网络获取
    url = f"http://fund.eastmoney.com/pingzhongdata/{code}.js"
    headers = {"Referer": "http://fund.eastmoney.com/"}
    r = requests.get(url, headers=headers, timeout=15)
    r.encoding = "utf-8"
    text = r.text

    def _str(var_name):
        m = re.search(rf'var\s+{var_name}\s*=\s*"([^"]*)"', text)
        return m.group(1) if m else None

    def _json(var_name):
        m = re.search(rf'var\s+{var_name}\s*=\s*(.+?);\s*(?:\n|/\*|$)', text, re.DOTALL)
        if not m:
            return None
        raw = m.group(1).strip().rstrip(";")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    name = _str("fS_name")
    if not name:
        return None

    # 收益率
    syl = {}
    for key, label in [("syl_1y", "近1月"), ("syl_3y", "近3月"),
                        ("syl_6y", "近6月"), ("syl_1n", "近1年")]:
        v = _str(key)
        syl[label] = float(v) if v and v != "" else None

    # 净值
    nav_list = _json("Data_netWorthTrend")

    # 基金经理
    manager_data = _json("Data_currentFundManager")
    manager_name = ""
    manager_exp_years = 0
    manager_fund_size = ""
    if manager_data and isinstance(manager_data, list) and len(manager_data) > 0:
        mgr = manager_data[0]
        manager_name = mgr.get("name", "")
        # workTime: "13年又284天" → 解析年数
        work_time = mgr.get("workTime", "")
        if work_time:
            import re as _re
            y_match = _re.search(r'(\d+)年', work_time)
            if y_match:
                manager_exp_years = int(y_match.group(1))
        # fundSize: "416.72亿(4只基金)"
        manager_fund_size = mgr.get("fundSize", "")
    days_managed = manager_exp_years * 365  # 用总从业年限作为代理指标

    # 持仓代码
    stock_codes_raw = _str("stockCodes")
    stock_codes = [c for c in stock_codes_raw.split(",") if c] if stock_codes_raw else []

    # 费率
    source_rate = _str("fund_sourceRate")
    current_rate = _str("fund_Rate")

    # 申购状态（0=可申购）
    status = _str("fS_buyState") or ""

    result = {
        "code": code,
        "name": name,
        "nav_list": nav_list,
        "syl": syl,
        "manager": manager_name,
        "manager_days": days_managed,
        "manager_exp_years": manager_exp_years,
        "manager_fund_size": manager_fund_size,
        "stock_codes": stock_codes,
        "source_rate": float(source_rate) if source_rate else None,
        "current_rate": float(current_rate) if current_rate else None,
        "status": status,
    }

    # 写入缓存
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
    except Exception:
        pass

    return result


def calc_metrics(nav_list, syl):
    """从净值数据计算风险收益指标"""
    if not nav_list or len(nav_list) < 250:
        return None

    # 提取净值序列（最近3年或全部）
    recent = nav_list[-min(750, len(nav_list)):]
    values = [item["y"] for item in recent]

    if len(values) < 60:
        return None

    # ---- 收益 ----
    total_return = (values[-1] - values[0]) / values[0]

    # 年化收益
    years = len(values) / 250
    annual_return = ((1 + total_return) ** (1 / max(years, 0.1)) - 1) if years > 0 else None

    # ---- 最大回撤 ----
    peak = values[0]
    max_dd = 0
    dd_start, dd_end = 0, 0
    for i, v in enumerate(values):
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd

    # ---- 波动率（年化） ----
    daily_returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]
    avg_dr = sum(daily_returns) / len(daily_returns)
    variance = sum((r - avg_dr) ** 2 for r in daily_returns) / len(daily_returns)
    daily_vol = math.sqrt(variance)
    annual_vol = daily_vol * math.sqrt(250)

    # ---- 下行波动率 ----
    downside_returns = [min(r, 0) for r in daily_returns]
    avg_down = sum(downside_returns) / len(downside_returns)
    down_variance = sum((r - avg_down) ** 2 for r in downside_returns) / len(downside_returns)
    down_vol = math.sqrt(down_variance) * math.sqrt(250)

    # ---- 夏普比率（假设无风险利率 2%） ----
    rf = 0.02
    sharpe = (annual_return - rf) / annual_vol if annual_vol > 0 else 0

    # ---- 卡玛比率 ----
    calmar = annual_return / max_dd if max_dd > 0 else 0

    # ---- 索提诺比率 ----
    sortino = (annual_return - rf) / down_vol if down_vol > 0 else 0

    # ---- 回撤恢复时间 ----
    # 简化为：从最大回撤开始到净值新高所需天数
    peak_idx = 0
    max_dd_idx = 0
    for i, v in enumerate(values):
        if v > values[peak_idx]:
            peak_idx = i
        if (values[peak_idx] - v) / values[peak_idx] == max_dd:
            max_dd_idx = i

    recovery_days = 0
    for i in range(max_dd_idx, len(values)):
        if values[i] >= values[peak_idx]:
            recovery_days = i - max_dd_idx
            break
    else:
        recovery_days = len(values) - max_dd_idx  # 还没恢复

    # ---- 胜率（月度） ----
    monthly = []
    for i in range(20, len(values), 20):
        m_ret = (values[i] - values[i-20]) / values[i-20]
        monthly.append(m_ret)
    win_rate = sum(1 for r in monthly if r > 0) / len(monthly) if monthly else 0

    return {
        "annual_return": annual_return,
        "total_return_3y": total_return,
        "max_drawdown": max_dd,
        "annual_volatility": annual_vol,
        "downside_volatility": down_vol,
        "sharpe": sharpe,
        "calmar": calmar,
        "sortino": sortino,
        "recovery_days": recovery_days,
        "win_rate_monthly": win_rate,
    }


# ============ 预筛选层（0网络请求）============

# 非主流份额后缀（A/C 保留，其余排除）
NON_MAINSTREAM_SUFFIX = tuple("BDEFHIJKLMNOPQRSTUVWXYZ")

# 不适合散户的基金类型关键词
UNSUITABLE_KEYWORDS = [
    "分级", "折算", "清盘",              # 消亡中
    "联接",                              # 多一层费用
    "发起式",                            # 规模太小
    "定期开放", "定开", "封闭",          # 流动性锁死
    "保本", "避险",                      # 收益太低
]


def prefilter_by_name(code, info):
    """
    0 成本预筛（只用基金名称和类型，不拉网络）
    返回: (keep: bool, reason: str)
    """
    name = info.get("name", "")

    # 1. 检查名称末尾是否非主流份额
    # 格式: "XXX混合A" → 末尾字母是份额
    if name.endswith(NON_MAINSTREAM_SUFFIX):
        # 但有例外: "ETF" 这种是产品类型不是份额
        if not name.endswith(("ETF", "LOF")):
            return False, f"非主流份额({name[-1]}类)"

    # 2. 检查是否含不适合的关键词
    for kw in UNSUITABLE_KEYWORDS:
        if kw in name:
            return False, f"结构不适合({kw})"

    # 3. 检查基金类型是否含排除词（已有但作为兜底）
    ftype = info.get("type", "")
    for kw in ["债券", "货币", "理财", "FOF", "养老", "固收", "纯债"]:
        if kw in ftype:
            return False, f"低风险类型({kw})"

    return True, ""


# ============ 分相淘汰 ============

def infer_sector_tags(stock_codes):
    """从持仓代码推断板块标签（简化版——按代码前缀）"""
    # 这是简化实现，完整版需要查股票表
    # 00xxxx/30xxxx = 深市, 60xxxx = 沪市, 688xxx = 科创板
    # 港股: 数字前带字母后缀的模式（从stockCodesNew判断）
    # 这里先用空的，后续可以通过 AKShare 补充
    return set()


def phase1_survival(fund_detail):
    """相位1: 生存过滤 — 评分制，每项≥40% 且总分≥60%"""
    checks = []
    scores = []

    # 1. 成立时间
    nav = fund_detail.get("nav_list")
    nav_len = len(nav) if nav else 0
    fund_years = nav_len / 250  # 交易日换算
    if fund_years >= 5:
        scores.append(100)
        checks.append((f"成立{fund_years:.1f}年", 100))
    elif fund_years >= 3:
        scores.append(70)
        checks.append((f"成立{fund_years:.1f}年", 70))
    elif fund_years >= 2:
        scores.append(40)
        checks.append((f"成立{fund_years:.1f}年", 40))
    else:
        return {"pass": False, "score": 0, "checks": [("成立不足2年", 0)], "reason": "成立时间不足2年"}

    # 2. 基金经理从业年限
    mgr_years = fund_detail.get("manager_exp_years", 0)
    if mgr_years >= 5:
        scores.append(100)
        checks.append((f"经理从业{mgr_years}年", 100))
    elif mgr_years >= 3:
        scores.append(70)
        checks.append((f"经理从业{mgr_years}年", 70))
    elif mgr_years >= 1:
        scores.append(40)
        checks.append((f"经理从业{mgr_years}年", 40))
    else:
        return {"pass": False, "score": 0, "checks": [("经理从业不足1年", 0)], "reason": "基金经理从业不足1年"}

    # 3. 管理规模（从经理 total AUM 推断）
    size_str = fund_detail.get("manager_fund_size", "")
    size_score = 0
    if size_str:
        try:
            import re as _re
            m = _re.search(r'([\d.]+)亿', size_str)
            if m:
                size_val = float(m.group(1))
                if size_val >= 10:
                    size_score = 100
                elif size_val >= 1:
                    size_score = 70
                elif size_val >= 0.5:
                    size_score = 40
                else:
                    size_score = 30
            else:
                size_score = 50  # 有数据但解析不出
        except Exception:
            size_score = 50
    else:
        size_score = 50  # 无规模数据，中性
    scores.append(size_score)
    checks.append((f"管理规模评分", size_score))

    # 4. 申购状态
    status = fund_detail.get("status", "")
    if status == "":
        scores.append(100)
        checks.append(("申购开放", 100))
    elif "限制" in str(status):
        scores.append(40)
        checks.append(("申购限制", 40))
    else:
        return {"pass": False, "score": 0, "checks": [("暂停申购", 0)], "reason": "暂停申购"}

    # 5. 费率合理性
    fund_type = fund_detail.get("type", "")
    fee = fund_detail.get("current_rate") or fund_detail.get("source_rate") or 999
    is_index = "指数" in fund_type
    if is_index:
        if fee <= 0.15:     fee_score = 100
        elif fee <= 0.5:    fee_score = 70
        elif fee <= 1.0:    fee_score = 40
        else:               fee_score = 20
    else:
        if fee <= 1.0:      fee_score = 100
        elif fee <= 1.5:    fee_score = 70
        elif fee <= 2.0:    fee_score = 40
        else:               fee_score = 20
    scores.append(fee_score)
    checks.append((f"费率评分({fee}%)", fee_score))

    # 每项 ≥ 40% 才通过
    min_sub = min(scores)
    avg = sum(scores) / len(scores)

    if min_sub < 40:
        return {"pass": False, "score": avg, "checks": checks,
                "reason": f"子项最低{min_sub:.0f}% < 40%"}

    if avg < 60:
        return {"pass": False, "score": avg, "checks": checks,
                "reason": f"总分{avg:.0f}% < 60%"}

    return {"pass": True, "score": avg, "checks": checks}


def phase2_risk_match(metrics, user_profile):
    """相位2: 风险匹配 — 每个子指标≥40% 且加权≥40%"""
    if not metrics:
        return {"pass": False, "score": 0, "reason": "数据不足"}

    max_dd_tolerance = abs(user_profile.get("max_dd_tolerance", -0.15))
    time_horizon = user_profile.get("time_horizon", "medium")
    horizon_mult = {"short": 0.6, "medium": 1.0, "long": 1.5}
    effective_tolerance = max_dd_tolerance * horizon_mult.get(time_horizon, 1.0)

    fund_max_dd = metrics["max_drawdown"]

    # 回撤匹配分
    if fund_max_dd <= effective_tolerance:
        dd_score = 100
    elif fund_max_dd <= effective_tolerance * 1.5:
        dd_score = 60
    elif fund_max_dd <= effective_tolerance * 2:
        dd_score = 30
    else:
        dd_score = 0

    # 下行波动匹配分
    down_vol = metrics["downside_volatility"]
    if down_vol <= effective_tolerance:
        vol_score = 100
    elif down_vol <= effective_tolerance * 1.5:
        vol_score = 60
    elif down_vol <= effective_tolerance * 2:
        vol_score = 30
    else:
        vol_score = 0

    # 回撤恢复速度
    recovery = metrics["recovery_days"]
    if recovery <= 180:
        recovery_score = 100
    elif recovery <= 365:
        recovery_score = 60
    elif recovery <= 730:
        recovery_score = 40
    else:
        recovery_score = 0

    # 每项独立 ≥ 40%
    subs = {"dd": dd_score, "vol": vol_score, "recovery": recovery_score}
    min_sub = min(subs.values())

    total = dd_score * 0.6 + vol_score * 0.25 + recovery_score * 0.15

    if min_sub < 40:
        return {"pass": False, "score": total,
                "dd_score": dd_score, "vol_score": vol_score, "recovery_score": recovery_score,
                "reason": f"子项最低{min_sub}% < 40% (dd={dd_score} vol={vol_score} rec={recovery_score})",
                "details": {"fund_max_dd": fund_max_dd, "tolerance": effective_tolerance,
                            "down_vol": down_vol, "recovery_days": recovery}}

    return {"pass": total >= 40, "score": total,
            "dd_score": dd_score, "vol_score": vol_score, "recovery_score": recovery_score,
            "details": {"fund_max_dd": fund_max_dd, "tolerance": effective_tolerance,
                        "down_vol": down_vol, "recovery_days": recovery}}


def phase3_efficiency(metrics, fund_detail, user_profile):
    """相位3: 效率检验 — 每个子指标≥40%，主动/被动分流"""
    if not metrics:
        return {"pass": False, "score": 0, "reason": "数据不足"}

    fund_type = fund_detail.get("type", "")
    is_index = "指数" in fund_type
    user_prefers = user_profile.get("style_preference", "both")

    if is_index:
        fee = fund_detail.get("current_rate") or fund_detail.get("source_rate") or 1.5
        if fee <= 0.15:     fee_score = 100
        elif fee <= 0.5:    fee_score = 70
        elif fee <= 1.0:    fee_score = 40
        else:               fee_score = 10

        calmar = metrics["calmar"]
        if calmar >= 1.0:       calmar_score = 100
        elif calmar >= 0.5:     calmar_score = 70
        elif calmar >= 0:       calmar_score = 40
        else:                   calmar_score = 10

        wr = metrics["win_rate_monthly"]
        if wr >= 0.6:       wr_score = 100
        elif wr >= 0.5:     wr_score = 70
        elif wr >= 0.4:     wr_score = 40
        else:               wr_score = 10

        subs = {"fee": fee_score, "calmar": calmar_score, "wr": wr_score}
        total = fee_score * 0.5 + calmar_score * 0.3 + wr_score * 0.2

    else:
        sortino = metrics["sortino"]
        if sortino >= 1.5:      sortino_score = 100
        elif sortino >= 0.8:    sortino_score = 70
        elif sortino >= 0:      sortino_score = 40
        else:                   sortino_score = 10

        wr = metrics["win_rate_monthly"]
        if wr >= 0.6:       wr_score = 100
        elif wr >= 0.5:     wr_score = 70
        elif wr >= 0.4:     wr_score = 40
        else:               wr_score = 10

        calmar = metrics["calmar"]
        if calmar >= 1.0:       calmar_score = 100
        elif calmar >= 0.5:     calmar_score = 70
        elif calmar >= 0:       calmar_score = 40
        else:                   calmar_score = 10

        subs = {"sortino": sortino_score, "wr": wr_score, "calmar": calmar_score}
        total = sortino_score * 0.4 + wr_score * 0.3 + calmar_score * 0.3

    min_sub = min(subs.values())

    if min_sub < 40:
        return {"pass": False, "score": total, "is_index": is_index,
                "reason": f"子项最低{min_sub}% < 40%",
                "details": {"fee": fund_detail.get("current_rate") or fund_detail.get("source_rate"),
                            "calmar": metrics["calmar"], "sortino": metrics.get("sortino"),
                            "win_rate": metrics["win_rate_monthly"]}}

    return {"pass": total >= 40, "score": total, "is_index": is_index,
            "details": {"fee": fund_detail.get("current_rate") or fund_detail.get("source_rate"),
                        "calmar": metrics["calmar"], "sortino": metrics.get("sortino"),
                        "win_rate": metrics["win_rate_monthly"]}}


def dedup_ac_shares(results, time_horizon):
    """
    同源 A/C 份额去重 + 按期限选份额
    "易方达蓝筹精选混合A" 和 "易方达蓝筹精选混合C" → 按期限选一个
    """
    groups = {}  # base_name -> [(result, share_class)]
    standalone = []

    for r in results:
        name = r["fund"]["name"]
        # 检测 A/C/E 份额
        if name.endswith(("A", "C", "E")) and len(name) > 2:
            base = name[:-1]  # 去掉最后一个字母
            share = name[-1]
            if base not in groups:
                groups[base] = []
            groups[base].append((r, share))
        else:
            standalone.append(r)

    merged = list(standalone)

    for base, shares in groups.items():
        if len(shares) <= 1:
            merged.extend([s[0] for s in shares])
            continue

        # 按期限选份额
        a_share = next((s for s in shares if s[1] == "A"), None)
        c_share = next((s for s in shares if s[1] == "C"), None)
        e_share = next((s for s in shares if s[1] == "E"), None)

        if time_horizon == "short":
            # 短期：优先 C
            selected = [s[0] for s in shares if s[1] == "C"]
            if not selected:
                selected = [shares[0][0]]
        elif time_horizon == "medium":
            # 中期：A 和 C 都保留，标注差异
            selected = [s[0] for s in shares]
        else:
            # 长期：优先 A
            selected = [s[0] for s in shares if s[1] == "A"]
            if not selected:
                selected = [shares[0][0]]

        # 标注份额信息
        for r_item in selected:
            r_item["share_class"] = r_item["fund"]["name"][-1]
            r_item["share_group"] = base

        merged.extend(selected)

    return merged


def phase4_preference(fund_detail, user_profile):
    """相位4: 偏好命中 — 只加分不淘汰"""
    score = 0
    checks = []

    fund_type = fund_detail.get("type", "")
    user_sectors = user_profile.get("preferred_sectors", [])
    user_style = user_profile.get("style_preference", "both")

    # 风格匹配
    is_index = "指数" in fund_type
    if user_style == "both":
        score += 30
        checks.append(("风格不限", 30))
    elif user_style == "passive" and is_index:
        score += 40
        checks.append(("被动型偏好命中", 40))
    elif user_style == "active" and not is_index:
        score += 40
        checks.append(("主动型偏好命中", 40))
    else:
        checks.append(("风格偏好未命中", 0))

    # 板块匹配（按基金类型关键词粗匹配）
    sector_keywords = {
        "科技": ["科技", "信息", "TMT", "互联网", "5G", "芯片", "半导体", "电子", "AI", "人工智能"],
        "消费": ["消费", "白酒", "食品", "饮料", "零售", "家电"],
        "医药": ["医药", "医疗", "健康", "生物", "中药"],
        "新能源": ["新能源", "光伏", "锂电", "电池", "汽车", "碳中和"],
        "金融": ["金融", "银行", "证券", "保险", "地产"],
        "军工": ["军工", "国防", "航天"],
        "港股": ["港股", "沪港通", "深港通", "恒生"],
        "美股": ["美股", "纳斯达克", "标普", "全球"],
    }

    fund_name = fund_detail.get("name", "")
    sector_hits = 0
    for user_sector in user_sectors:
        keywords = sector_keywords.get(user_sector, [user_sector])
        if any(kw in fund_name for kw in keywords):
            sector_hits += 1

    if sector_hits > 0:
        bonus = min(sector_hits * 25, 50)  # 最多 50 分
        score += bonus
        checks.append((f"板块命中 {sector_hits} 个", bonus))

    # 避开项检查
    excludes = user_profile.get("excludes", [])
    hit_exclude = False
    for ex in excludes:
        if ex in fund_name:
            hit_exclude = True
            checks.append((f"命中避开的「{ex}」", -50))
            break
    if hit_exclude:
        score = max(0, score - 50)

    return {
        "score": min(score, 100),
        "checks": checks,
    }


# ============ 主流程 ============

def run_matching(user_profile, limit=15):
    """
    运行完整匹配流程
    user_profile: {
        time_horizon, max_dd_tolerance, preferred_sectors,
        style_preference, excludes, ...
    }
    返回: [fund_result, ...]  按匹配度降序
    """
    print("\n" + "=" * 50)
    print("  基金匹配引擎启动")
    print("=" * 50)

    # 加载基金列表
    all_funds = load_fund_list()
    if not all_funds:
        print("[错误] 无法加载基金列表，请检查网络")
        return [], {}

    total_all = len(all_funds)

    # ---- 预筛层 ----
    stats = {
        "total": total_all,
        "excluded_type": 0,
        "excluded_share": 0,
        "excluded_structure": 0,
        "excluded_type_detail": {},
    }

    eligible_types = ["混合型", "股票型", "指数型", "QDII"]
    candidates = {}
    for code, info in all_funds.items():
        ftype = info.get("type", "")
        keep = True
        reason = ""

        # 类型过滤
        if not any(t in ftype for t in eligible_types):
            keep = False
            reason = f"低风险类型({ftype})"
            stats["excluded_type"] += 1
            stats["excluded_type_detail"][ftype] = stats["excluded_type_detail"].get(ftype, 0) + 1

        if keep:
            # 名称预筛
            keep, reason = prefilter_by_name(code, info)
            if not keep:
                if "份额" in reason:
                    stats["excluded_share"] += 1
                else:
                    stats["excluded_structure"] += 1

        if keep:
            candidates[code] = info

    total_candidates = len(candidates)

    print(f"  全市场: {total_all} → 预筛后: {total_candidates} 只")
    print(f"  (排除: 类型{stats['excluded_type']} + 份额{stats['excluded_share']} + 结构{stats['excluded_structure']})")

    if not candidates:
        print("[错误] 预筛后无候选基金")
        return [], stats

    # ---- 两级拉取：缓存优先 ----
    codes = list(candidates.keys())
    cached_codes = []
    uncached_codes = []

    CACHE_DAYS = 3  # 净值缓存 3 天
    cache_seconds = CACHE_DAYS * 86400

    for code in codes:
        cache_path = get_detail_path(code)
        if os.path.exists(cache_path) and (time.time() - os.path.getmtime(cache_path)) < cache_seconds:
            cached_codes.append(code)
        else:
            uncached_codes.append(code)

    cache_pct = len(cached_codes) / total_candidates * 100
    print(f"  缓存命中: {len(cached_codes)} 只 ({cache_pct:.0f}%) | 需拉取: {len(uncached_codes)} 只")

    start_time = time.time()
    details = {}

    # ---- 第一遍：缓存数据直接评分 ----
    if cached_codes:
        print(f"  第一遍: 缓存评分 ({len(cached_codes)} 只)...")
        for code in cached_codes:
            try:
                with open(get_detail_path(code), "r", encoding="utf-8") as f:
                    detail = json.load(f)
                detail["type"] = candidates.get(code, {}).get("type", "未知")
                details[code] = detail
            except Exception:
                uncached_codes.append(code)  # 缓存坏了，丢去拉取

    # ---- 第二遍：拉取无缓存基金 ----
    if uncached_codes:
        print(f"  第二遍: 拉取+评分 ({len(uncached_codes)} 只)...")
        counters = {"success": 0, "fail": 0}
        completed = 0
        total_fetch = len(uncached_codes)

        def fetch_one(code):
            try:
                return code, fetch_fund_detail(code)
            except Exception:
                return code, None

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(fetch_one, code): code for code in uncached_codes}
            for future in as_completed(futures):
                completed += 1
                try:
                    code, detail = future.result()
                    if detail:
                        detail["type"] = candidates.get(code, {}).get("type", "未知")
                        details[code] = detail
                        counters["success"] += 1
                    else:
                        counters["fail"] += 1
                except Exception:
                    counters["fail"] += 1
                if completed % 500 == 0 or completed == total_fetch:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    eta = (total_fetch - completed) / rate if rate > 0 else 0
                    print(f"    拉取: {completed}/{total_fetch} | {elapsed:.0f}秒 | 剩余~{eta:.0f}秒", end="\r")

        print(f"\n    拉取完成: 成功 {counters['success']} + 失败 {counters['fail']} (代码不存在或已清盘)")

    # ---- 第二阶段：顺序评分 ----
    print(f"  正在评分...")
    results = []
    survived = {"p1": 0, "p2": 0, "p3": 0}
    score_start = time.time()

    for code, detail in details.items():
        try:
            p1 = phase1_survival(detail)
            if not p1["pass"]:
                continue
            survived["p1"] += 1

            metrics = calc_metrics(detail.get("nav_list"), detail.get("syl"))
            if not metrics:
                continue

            p2 = phase2_risk_match(metrics, user_profile)
            if not p2["pass"]:
                continue
            survived["p2"] += 1

            p3 = phase3_efficiency(metrics, detail, user_profile)
            if not p3["pass"]:
                continue
            survived["p3"] += 1

            p4 = phase4_preference(detail, user_profile)

            final_score = p2["score"] * 0.35 + p3["score"] * 0.35 + p4["score"] * 0.30

            if final_score < 40:
                continue

            results.append({
                "fund": detail,
                "metrics": metrics,
                "phases": {"p1": p1, "p2": p2, "p3": p3, "p4": p4},
                "final_score": final_score,
            })
        except Exception:
            continue

    score_time = time.time() - score_start
    total_time = time.time() - start_time
    match_rate = len(results) / len(details) * 100 if details else 0
    print(f"  总耗时 {total_time:.0f}秒 | 四相存活 {len(results)} 只 ({match_rate:.1f}%)")

    # A/C 份额去重
    time_horizon = user_profile.get("time_horizon", "medium")
    results = dedup_ac_shares(results, time_horizon)

    # 按匹配度排序
    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results[:limit], stats
