"""
基金匹配器 — 引导式问答 → 四相筛选 → 匹配报告

用法:
    python main.py          → 交互问答模式
    python main.py --update → 仅更新数据缓存

数据来源: 天天基金 (fund.eastmoney.com)
"""

import sys, os, json, time, webbrowser

# 修复 exe 版在 Windows CMD 下的乱码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        os.system("chcp 65001 > nul")

from engine import run_matching, load_fund_list, DATA_DIR
from datetime import datetime

REPORT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(REPORT_DIR, exist_ok=True)


# ============ 引导式问答 ============

def ask_one(question, options, tip=None):
    """单选题"""
    print(f"\n  {question}")
    print()
    for i, opt in enumerate(options, 1):
        print(f"    [{i}]  {opt}")
    if tip:
        print(f"\n  💡 {tip}")
    print()
    while True:
        try:
            choice = input("  → ").strip()
            if not choice:
                continue
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return idx
            print(f"  输入 1~{len(options)} 就好")
        except ValueError:
            print("  输入数字就好")


def ask_multi(question, options, tip=None):
    """多选题，返回索引列表"""
    print(f"\n  {question}（可多选，用空格分隔，如：1 3 5）")
    print()
    for i, opt in enumerate(options, 1):
        print(f"    [{i}]  {opt}")
    if tip:
        print(f"\n  💡 {tip}")
    print()
    while True:
        try:
            choice = input("  → ").strip()
            if not choice:
                return []
            idxs = [int(x) - 1 for x in choice.split()]
            if all(0 <= i < len(options) for i in idxs):
                return idxs
            print(f"  每个数字要在 1~{len(options)} 之间")
        except ValueError:
            print("  输入数字，多个用空格分开（如：1 3 5）")


def guided_qa():
    """20 题引导式问卷 + 交叉验证"""

    print("""
  ╔══════════════════════════════════════╗
  ║                                    ║
  ║         基金匹配器                  ║
  ║   没有最好的基金                    ║
  ║   只有最适合自己需求的              ║
  ║                                    ║
  ║              —— 一入向北            ║
  ╚══════════════════════════════════════╝

  一共 20 个问题，5 分钟左右。
""")

    raw = {}  # 原始答案

    # ═══════════════════════════════════
    # 第一部分：你是谁（Q1-Q6）
    # ═══════════════════════════════════
    print("─" * 45)
    print("  第一部分：你是谁 + 这笔钱从哪来")
    print()

    raw["life_stage"] = ask_one("你现在处在什么阶段？", [
        "学生，没有稳定收入，但家庭能兜底",
        "刚工作 1~3 年，还在攒第一桶金",
        "工作稳定，每月有结余可以投资",
        "自由职业 / 创业，收入起伏比较大",
        "中年，有家庭负担但收入较高",
        "临近退休或已经退休，靠积蓄生活",
    ])

    raw["money_source"] = ask_one("这笔钱是从哪来的？", [
        "父母或家人给的",
        "工资攒下来的，之后还会每月定投",
        "多年的积蓄，一次性投进来",
        "年终奖 / 红包 / 一笔意外之财",
        "卖掉了其他投资转过来的",
        "借的 / 有杠杆成本的",
    ])

    raw["safety_cushion"] = ask_one("你的财务安全垫有多厚？", [
        "几乎没有，这笔钱就是全部家当",
        "有 1~3 个月生活费在活期",
        "有 3~6 个月生活费 + 基础保险",
        "有半年以上备用金 + 保险 + 家人能兜底",
        "很厚，这笔钱亏完也不影响生活",
    ])

    raw["money_mission"] = ask_multi("这笔钱的使命是什么？", [
        "纯增值，没有具体目标",
        "为买房凑首付",
        "子女教育 / 未来学费",
        "养老储备，几十年后才用",
        "试试水，想学投资",
        "还没想好，先放着",
    ])

    raw["time_horizon"] = ask_one("你打算持有多久？", [
        "说不好，随时可能要拿出来（< 1 年）",
        "1 ~ 2 年",
        "2 ~ 3 年",
        "3 ~ 5 年",
        "5 年以上，能穿越一轮牛熊",
    ])

    raw["horizon_flex"] = ask_one("如果碰到意外，期限弹性多大？", [
        "必须按原计划，提前取出后果严重",
        "勉强能往后延半年到一年",
        "如果赔太多宁愿多等几年也不割肉",
        "很灵活，时间不是问题",
    ])

    # ═══════════════════════════════════
    # 第二部分：真实场景测试（Q7-Q12）
    # ═══════════════════════════════════
    print("\n" + "─" * 45)
    print("  第二部分：几个真实场景，你怎么做")
    print()

    raw["scene_dd_1m"] = ask_one("你投了一万块。一个月后变成八千五。你第一反应？", [
        "睡不着，立刻全部卖掉",
        "很焦虑，但先忍住不动",
        "还好，几个月后再看",
        "有点兴奋，觉得跌出机会了",
        "已经在想怎么凑钱加仓了",
    ])

    raw["scene_dd_6m"] = ask_one("六个月过去了还在跌，亏了 30%。你怎么做？", [
        "后悔当初没割，现在赶紧卖",
        "不看了，删 App，装死",
        "不动，按原计划继续定投",
        "这时候才是真正该买的时候，加仓",
    ])

    raw["scene_fomo"] = ask_one("两年不涨不跌。朋友买的同期涨了 40%。你怎么想？", [
        "受不了，换到朋友那只",
        "有点怀疑自己的选择，但再看看",
        "无所谓，选的时候就清楚为什么选它",
        "朋友运气好而已，我的逻辑没问题",
    ])

    raw["scene_chase"] = ask_one("看到一只基金去年涨了 80%，你会？", [
        "赶紧研究，想买",
        "羡慕，但先看看为什么涨",
        "去年涨这么多，今年可能够呛，避开",
        "没感觉，不看排行榜",
    ])

    raw["watch_freq"] = ask_one("某天大盘跌 5%，新闻全是坏消息。你看账户的频率？", [
        "不停地刷，手心出汗",
        "每天看一次净值",
        "每周看一次就够了",
        "不怎么看，反正长期持有",
        "忘了还有账户这回事",
    ])

    raw["select_basis"] = ask_one("你当初选这只基金，最主要依据是什么？", [
        "排行榜上收益率高",
        "朋友 / 大 V / 群里的推荐",
        "自己研究过持仓和基金经理",
        "跟着指数买的，没怎么挑",
        "平台推荐的",
        "还没买过，说不上来",
    ])

    # ═══════════════════════════════════
    # 第三部分：真实的你（Q13-Q15）
    # ═══════════════════════════════════
    print("\n" + "─" * 45)
    print("  第三部分：投资这件事，你真实的样子")
    print()

    raw["past_invest"] = ask_one("你以前投过什么？", [
        "只存过银行存款 / 余额宝",
        "买过理财 / 保险，没碰过基金",
        "买过基金，定投为主",
        "基金 + 股票都碰过",
        "各种都试过，包括加密货币 / 期货",
    ])

    raw["past_loss"] = ask_one('亏损最多那次，你实际做了什么？不是说「会做」，是「真的做了」。', [
        "恐慌卖出，割在地板上",
        "什么都不做，装作没看见",
        "按原计划定投，没动",
        "加仓了",
        "没亏过 / 没投过",
    ])

    raw["info_source"] = ask_one("你平时从哪获取投资信息？最信谁的？", [
        "抖音 / B站 / 小红书的博主",
        "微信群 / QQ群里的朋友",
        "天天基金 / 支付宝的推荐",
        "基金经理的季报 / 年报",
        "自己看数据，不太听别人的",
        "基本不看，被动买",
    ])

    # ═══════════════════════════════════
    # 第四部分：投资观念（Q16-Q18）
    # ═══════════════════════════════════
    print("\n" + "─" * 45)
    print("  第四部分：你怎么看投资这件事")
    print()

    raw["manager_change"] = ask_one("你的基金突然换了基金经理。你怎么做？", [
        "立刻卖掉，买它就是买这个人",
        "观察一个季度，不行再换",
        "换不换人无所谓，看持仓和数据",
        "我买的是指数型，不影响",
    ])

    raw["timing_confidence"] = ask_one("你觉得你能判断什么时候该买、该卖吗？", [
        "我觉得我大概能判断",
        "感觉有把握的时候买卖过，结果不太好",
        "不太能，所以尽量少操作",
        "完全不认为有人能择时，我也不行",
    ])

    raw["sleep_issue"] = ask_one("哪个更让你睡不着觉？", [
        "亏了 20%，还没涨回来",
        "没亏，但别人赚 30% 我踏空了",
        "两个都会",
        "两个都不会，我睡得挺好",
    ])

    # ═══════════════════════════════════
    # 第五部分：偏好（Q19-Q20）
    # ═══════════════════════════════════
    print("\n" + "─" * 45)
    print("  第五部分：你的偏好")
    print()

    raw["preferred_sectors"] = ask_multi("有没有你比较看好的方向？", [
        "科技 / 互联网 / AI",
        "消费 / 白酒 / 医药",
        "新能源 / 制造 / 汽车",
        "金融 / 地产 / 红利",
        "港股 / 海外市场",
        "没有特别方向，广撒网",
    ])

    raw["excludes"] = ask_multi("有没有你不想碰的？", [
        "军工",
        "石油 / 煤炭等传统能源",
        "高杠杆 / 衍生品",
        "房地产相关",
    ], "可以多选，也可以直接回车跳过")

    # ═══════════════════════════════════
    # 交叉验证 + 画像合成
    # ═══════════════════════════════════
    profile = build_profile(raw)

    # 总结
    print("\n" + "=" * 45)
    horizon_label = {"short": "偏短期", "medium": "中期", "long": "长期"}
    risk_label = {"conservative": "稳健优先", "moderate": "平衡", "aggressive": "愿意进取"}
    style_label = {"active": "倾向主动型", "passive": "倾向被动型", "both": "不限风格"}

    dd_pct = profile["max_dd_tolerance"]

    print(f"""
  这是你目前的画像：

    钱大概能放 {horizon_label[profile['time_horizon']]}
    亏 {-dd_pct:.0%} 以内还能接受
    心态偏 {risk_label[profile['return_preference']]}
    {style_label[profile['style_preference']]}
""")
    if profile["preferred_sectors"]:
        print(f"    偏好方向: {', '.join(profile['preferred_sectors'])}")
    if profile["excludes"]:
        print(f"    避开: {', '.join(profile['excludes'])}")

    warnings = profile.pop("_warnings", [])
    if warnings:
        print(f"\n  ⚠️ 发现 {len(warnings)} 个矛盾点：")
        for w in warnings:
            print(f"    · {w}")

    print("─" * 45)
    confirm = input("\n  没问题敲回车开始匹配（n 重来）: ").strip().lower()
    if confirm == "n":
        return guided_qa()

    return profile


# ═══════════════════════════════════
# 交叉验证 + 画像合成
# ═══════════════════════════════════

def build_profile(raw):
    """将 20 个原始答案映射为引擎所需的 profile"""
    profile = {}
    warnings = []

    # ── 期限：Q5 理想期限 + Q6 弹性 ──
    horizon_map = {0: "short", 1: "short", 2: "medium", 3: "medium", 4: "long"}
    ideal = horizon_map[raw["time_horizon"]]
    flex = raw["horizon_flex"]

    # 理想长期但弹性为 0 → 降级
    if ideal == "long" and flex == 0:
        profile["time_horizon"] = "medium"
        warnings.append("你说可以投 5 年以上，但弹性为零。实际按中期处理更安全。")
    elif ideal == "medium" and flex == 0:
        profile["time_horizon"] = "short"
        warnings.append("期限目标和弹性冲突，已按保守方向调整。")
    else:
        profile["time_horizon"] = ideal

    # ── 风险重要性：Q3 安全垫 + Q1 人生阶段 ──
    cushion = raw["safety_cushion"]
    life = raw["life_stage"]

    if cushion <= 1 or life == 0:  # 学生或没安全垫
        profile["risk_importance"] = "high"
    elif cushion <= 2:
        profile["risk_importance"] = "medium"
    else:
        profile["risk_importance"] = "low"

    # ── 回撤容忍：Q7 短期 + Q8 长期 + Q11 盯盘频率 ──
    dd_short_map = {0: -0.05, 1: -0.08, 2: -0.15, 3: -0.22, 4: -0.30}
    dd_long_map = {0: -0.05, 1: -0.08, 2: -0.15, 3: -0.25}
    dd_from_short = dd_short_map[raw["scene_dd_1m"]]
    dd_from_long = dd_long_map[raw["scene_dd_6m"]]
    watch = raw["watch_freq"]

    # 取最保守的
    dd_candidates = [dd_from_short, dd_from_long]
    if watch == 0:  # 不停刷 → 加个保守值
        dd_candidates.append(-0.05)
    elif watch == 1:
        dd_candidates.append(-0.08)

    profile["max_dd_tolerance"] = max(dd_candidates)  # 最大（最保守，因为都是负数）

    # 矛盾检测
    if dd_from_short >= -0.05 and dd_from_long <= -0.25:
        warnings.append("你说短期亏 15% 还行，但长期亏 30% 会装死。前后不太一致，已取保守方向。")

    if raw["scene_chase"] == 0:
        warnings.append("看到去年涨 80% 的基金会想追。注意追涨是新手最容易亏钱的方式。")

    # ── 收益偏好：Q9 踏空焦虑 + Q18 睡不着 + 回撤 ──
    fomo = raw["scene_fomo"]
    sleep = raw["sleep_issue"]

    if sleep == 1 or fomo == 0:  # 踏空更睡不着 → conservative
        pref = "conservative"
    elif sleep == 3 or dd_from_short <= -0.25:
        pref = "aggressive"
    elif sleep == 0:  # 亏钱睡不着
        pref = "conservative"
    else:
        pref = "moderate"
    profile["return_preference"] = pref

    # ── 经验：Q13 + Q14 真实行为 ──
    past = raw["past_invest"]
    loss = raw["past_loss"]

    if past <= 1:
        profile["experience"] = "novice"
    elif past == 2 or loss == 4:
        profile["experience"] = "burned"
    else:
        profile["experience"] = "experienced"

    # 新手保护
    if profile["experience"] == "novice":
        profile["max_dd_tolerance"] = max(profile["max_dd_tolerance"], -0.08)
        warnings.append("刚开始投资，已自动将风险上限调低。等你更熟悉了可以重新评估。")

    # 行为校准：说能承受 -25% 但历史上割过地板 → 下调
    if loss == 0 and dd_from_short <= -0.22:
        profile["max_dd_tolerance"] = max(profile["max_dd_tolerance"], -0.12)
        warnings.append("你觉得自己能扛 25% 回撤，但历史真实行为显示你在更小的亏损时就割了。已按真实行为校准。")

    # ── 主动/被动：Q16 经理变动 + Q17 择时自信 ──
    mgr = raw["manager_change"]
    timing = raw["timing_confidence"]

    if mgr == 0 or timing == 0:
        profile["style_preference"] = "active"
    elif mgr == 3 or timing >= 2:
        profile["style_preference"] = "passive"
    else:
        profile["style_preference"] = "both"

    # ── 偏好板块 ──
    sector_list = raw.get("preferred_sectors", [])
    sector_map = {0: "科技", 1: "消费", 2: "新能源", 3: "金融", 4: "港股"}
    has_broad = 5 in sector_list
    profile["preferred_sectors"] = [sector_map[i] for i in sector_list if i in sector_map]
    if has_broad and not profile["preferred_sectors"]:
        profile["preferred_sectors"] = []

    # ── 排除项 ──
    exclude_list = raw.get("excludes", [])
    exclude_map = {0: "军工", 1: "石油", 2: "衍生品", 3: "房地产"}
    profile["excludes"] = [exclude_map[i] for i in exclude_list if i in exclude_map]

    # ── 信息茧房提醒 ──
    info = raw.get("info_source", 5)
    basis = raw.get("select_basis", 5)
    if info <= 1 or basis <= 1:
        warnings.append("你的投资信息主要来自博主和推荐，建议多看看基金的季报和原始数据。")

    profile["_warnings"] = warnings
    return profile


# ============ HTML 报告 ============

def generate_html(results, profile, stats=None, output_path=None):
    """生成自包含 HTML 报告"""
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(REPORT_DIR, f"fund_match_{timestamp}.html")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 用户画像简述
    horizon_label = {"short": "短期", "medium": "中期", "long": "长期"}
    dd = profile.get("max_dd_tolerance", -0.15)
    sectors = profile.get("preferred_sectors", [])
    style = profile.get("style_preference", "both")

    # 生成基金卡片
    cards_html = ""
    for rank, r in enumerate(results, 1):
        f = r["fund"]
        m = r["metrics"]
        p = r["phases"]
        score = r["final_score"]

        # 星级
        stars = "⭐" * min(5, max(1, int(score / 20 + 1)))

        # 匹配度颜色
        if score >= 80:
            score_color = "#00b894"
        elif score >= 60:
            score_color = "#fdcb6e"
        else:
            score_color = "#e17055"

        # 基金经理任期
        mgr_years = f.get("manager_days", 0) / 365

        # 计算收益率 CSS 类名
        def css_class(val):
            return "positive" if (val or 0) > 0 else "negative"

        m1_cls = css_class(f["syl"].get("近1月"))
        m3_cls = css_class(f["syl"].get("近3月"))
        m6_cls = css_class(f["syl"].get("近6月"))
        y1_cls = css_class(f["syl"].get("近1年"))

        # 相位状态 & A/C 标注
        p1_cls = "pass" if p["p1"]["pass"] else "fail"
        p2_cls = "pass" if p["p2"]["pass"] else "fail"
        p3_cls = "pass" if p["p3"]["pass"] else "fail"

        # 份额信息
        share_note = ""
        share_class = r.get("share_class", "")
        if share_class:
            horizon = profile.get("time_horizon", "")
            share_labels = {
                "short": "（短期优选C类，免申购费）",
                "medium": "（中期可选A或C，详见费率对比）",
                "long": "（长期优选A类，持有成本更低）",
            }
            share_note = f'<span class="share-note">{share_labels.get(horizon, "")}</span>'

        cards_html += f"""
        <div class="card">
            <div class="card-header">
                <span class="rank">#{rank}</span>
                <span class="name">{f['name']}</span>
                <span class="code">{f['code']}</span>
                <span class="score" style="color:{score_color}">{score:.0f}%</span>
            </div>
            {share_note}
            <div class="card-body">
                <div class="col">
                    <h4>📊 收益表现</h4>
                    <table>
                        <tr><td>近1月</td><td class="{m1_cls}">{_pct(f['syl'].get('近1月'))}</td></tr>
                        <tr><td>近3月</td><td class="{m3_cls}">{_pct(f['syl'].get('近3月'))}</td></tr>
                        <tr><td>近6月</td><td class="{m6_cls}">{_pct(f['syl'].get('近6月'))}</td></tr>
                        <tr><td>近1年</td><td class="{y1_cls}">{_pct(f['syl'].get('近1年'))}</td></tr>
                    </table>
                </div>
                <div class="col">
                    <h4>⚠️ 风险指标</h4>
                    <table>
                        <tr><td>最大回撤</td><td class="negative">-{m['max_drawdown']*100:.1f}%</td></tr>
                        <tr><td>年化波动率</td><td>{m['annual_volatility']*100:.1f}%</td></tr>
                        <tr><td>下行波动率</td><td>{m['downside_volatility']*100:.1f}%</td></tr>
                        <tr><td>回撤恢复</td><td>{m['recovery_days']}天</td></tr>
                    </table>
                </div>
                <div class="col">
                    <h4>💰 效率指标</h4>
                    <table>
                        <tr><td>夏普比率</td><td>{m['sharpe']:.2f}</td></tr>
                        <tr><td>卡玛比率</td><td>{m['calmar']:.2f}</td></tr>
                        <tr><td>索提诺比率</td><td>{m['sortino']:.2f}</td></tr>
                        <tr><td>月度胜率</td><td>{m['win_rate_monthly']*100:.0f}%</td></tr>
                    </table>
                </div>
            </div>
            <div class="card-footer">
                <span>👤 经理: {f.get('manager', '?')}（从业{mgr_years:.0f}年）</span>
                <span>📋 类型: {f.get('type', '?')}</span>
                <span>💵 申购费率: {f.get('current_rate') or f.get('source_rate') or '?'}%</span>
                <span>📅 成立约{f.get('nav_list') and len(f['nav_list'])//250 or '?'}年</span>
            </div>
            <div class="phases">
                <span class="phase {p1_cls}">P1: 生存 {p['p1']['score']:.0f} (5项)</span>
                <span class="phase {p2_cls}">P2: 风险 {p['p2']['score']:.0f} (3项)</span>
                <span class="phase {p3_cls}">P3: 效率 {p['p3']['score']:.0f} (3项)</span>
                <span class="phase info">P4: 偏好 {p['p4']['score']:.0f}</span>
            </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>基金匹配报告</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; background: #f5f6fa; color: #2d3436; line-height: 1.6; }}
.container {{ max-width: 960px; margin: 0 auto; padding: 24px; }}
.header {{ background: linear-gradient(135deg, #6c5ce7, #a29bfe); color: white; padding: 32px; border-radius: 16px; margin-bottom: 24px; }}
.header h1 {{ font-size: 28px; margin-bottom: 8px; }}
.header .profile {{ font-size: 14px; opacity: 0.9; }}
.card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
.card-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
.rank {{ font-size: 20px; font-weight: 700; color: #6c5ce7; min-width: 36px; }}
.name {{ font-size: 18px; font-weight: 600; flex: 1; }}
.code {{ font-size: 12px; color: #b2bec3; }}
.score {{ font-size: 24px; font-weight: 700; }}
.card-body {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 16px; }}
.col h4 {{ font-size: 13px; color: #636e72; margin-bottom: 8px; }}
.col table {{ width: 100%; font-size: 13px; }}
.col td {{ padding: 3px 0; }}
.col td:last-child {{ text-align: right; font-weight: 600; }}
.positive {{ color: #00b894; }}
.negative {{ color: #e17055; }}
.card-footer {{ display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: #636e72; border-top: 1px solid #eee; padding-top: 12px; }}
.phases {{ display: flex; gap: 8px; margin-top: 12px; }}
.phase {{ font-size: 11px; padding: 2px 8px; border-radius: 4px; }}
.phase.pass {{ background: #d4edda; color: #155724; }}
.phase.fail {{ background: #f8d7da; color: #721c24; }}
.phase.info {{ background: #d1ecf1; color: #0c5460; }}
.share-note {{ display: block; font-size: 12px; color: #6c5ce7; margin: -8px 0 8px 48px; }}
.stats-box {{ background: #f8f9fa; border-radius: 12px; padding: 20px; margin-bottom: 24px; font-size: 13px; }}
.stats-box h3 {{ font-size: 14px; margin-bottom: 12px; color: #2d3436; }}
.stats-table {{ width: 100%; }}
.stats-table td {{ padding: 4px 0; }}
.stats-table .num {{ text-align: right; font-weight: 600; }}
.stats-table .dim {{ color: #b2bec3; }}
.stats-table .detail {{ font-size: 11px; color: #636e72; padding-left: 16px; }}
.stats-table .total-row {{ border-top: 1px solid #dfe6e9; font-weight: 700; }}
.footer {{ text-align: center; font-size: 11px; color: #b2bec3; margin-top: 32px; padding: 16px; }}
@media (max-width: 640px) {{ .card-body {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">
<div class="header">
    <h1>🏦 基金匹配报告</h1>
    <div class="profile">
        期限: {horizon_label.get(profile.get('time_horizon',''), '?')} ·
        回撤容忍: {dd:.0%} ·
        风格: {style} ·
        偏好: {', '.join(sectors) if sectors else '不限'}<br>
        生成时间: {now}
    </div>
</div>

{_stats_html(stats)}

{cards_html}
<div class="footer">
    <p>数据来源: 天天基金 (fund.eastmoney.com) · 更新时间: {now}</p>
    <p>⚠️ 本报告仅基于公开历史数据的量化匹配，不构成投资建议。历史表现不代表未来收益。</p>
    <p>基金匹配器 v1.0 · 四相淘汰算法 · 数据驱动，不追热点</p>
</div>
</div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


def _stats_html(stats):
    """生成预筛统计 HTML"""
    if not stats:
        return ""

    excluded_type = stats.get("excluded_type", 0)
    excluded_share = stats.get("excluded_share", 0)
    excluded_struct = stats.get("excluded_structure", 0)
    total = stats.get("total", 0)

    type_detail = stats.get("excluded_type_detail", {})
    type_rows = ""
    for t, c in sorted(type_detail.items(), key=lambda x: -x[1])[:5]:
        type_rows += f"<tr><td>{t}</td><td>{c} 只</td></tr>"

    return f"""
<div class="stats-box">
    <h3>📋 候选范围</h3>
    <table class="stats-table">
        <tr><td>全市场基金</td><td class="num">{total} 只</td></tr>
        <tr><td class="dim">排除低风险类型</td><td class="num dim">-{excluded_type} 只</td></tr>
        <tr><td colspan="2" class="detail">（债券/货币/理财/FOF/养老/固收）</td></tr>
        <tr><td class="dim">排除非主流份额</td><td class="num dim">-{excluded_share} 只</td></tr>
        <tr><td colspan="2" class="detail">（B/D/E/H 等渠道专属份额，散户买不到）</td></tr>
        <tr><td class="dim">排除结构不适合</td><td class="num dim">-{excluded_struct} 只</td></tr>
        <tr><td colspan="2" class="detail">（分级/折算/清盘/联接/发起式/定期开放）</td></tr>
        <tr class="total-row"><td>进入匹配</td><td class="num">{total - excluded_type - excluded_share - excluded_struct} 只</td></tr>
    </table>
</div>"""


def _pct(val):
    if val is None:
        return "N/A"
    return f"{val:+.2f}%"


# ============ 入口 ============

def main():
    # 自动更新数据
    print("正在检查数据更新...")
    try:
        load_fund_list(force_refresh=True)
    except Exception as e:
        print(f"  数据更新失败: {e}")
        print("  将使用缓存数据继续...")

    # 问答
    profile = guided_qa()

    # 匹配
    print("\n正在运行四相匹配...")
    results, stats = run_matching(profile)

    if not results:
        print("\n😔 没有找到匹配的基金。")
        print("  可能原因: 筛选条件太严格，或网络不稳定。")
        print("  建议: 放宽风险偏好后重新尝试。")
        input("\n按回车退出...")
        return

    # 生成报告
    print("\n正在生成报告...")
    report_path = generate_html(results, profile, stats)

    print(f"\n✅ 报告已生成: {report_path}")
    print(f"   匹配到 {len(results)} 只基金")

    # 打开浏览器
    try:
        webbrowser.open(f"file:///{report_path}")
        print("   已在浏览器中打开")
    except Exception:
        pass

    # 终端摘要
    print("\n" + "=" * 50)
    print("  📊 匹配结果摘要")
    print("=" * 50)
    for i, r in enumerate(results, 1):
        f = r["fund"]
        s = r["final_score"]
        bar = "█" * int(s / 10) + "░" * (10 - int(s / 10))
        print(f"  {i}. [{bar}] {s:.0f}%  {f['name'][:20]:<22} {f['code']}")

    print("\n" + "─" * 50)
    print("  一入向北 · 没有最好的基金，只有最适合自己需求的")
    print("  数据来源: 天天基金 (fund.eastmoney.com)")
    print("─" * 50)

    input("\n按回车退出...")


if __name__ == "__main__":
    main()
