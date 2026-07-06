"""
基金匹配器 — Streamlit 网页版
手机 + 电脑都能用
"""

import streamlit as st
import sys, os

sys.path.insert(0, os.path.dirname(__file__))

from main import build_profile
from engine import run_matching as do_match, load_fund_list

st.set_page_config(
    page_title="基金匹配器",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---- 自定义 CSS ----
st.markdown("""
<style>
    .stApp { background: #1a1a2e; }
    .main-header {
        background: linear-gradient(135deg, #e8b86d, #d4924a);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 28px; font-weight: 800; text-align: center;
        padding: 16px 0 4px;
    }
    .sub-header { text-align: center; color: #8b8b9e; font-size: 14px; margin-bottom: 24px; }
    .brand-id { text-align: center; color: #e8b86d; font-size: 12px; font-weight: 600; letter-spacing: 2px; }
    .question-card {
        background: #252540; border-radius: 16px; padding: 28px;
        margin: 12px 0; border: 1px solid #2d2d50;
    }
    .question-text { color: #f0f0f0; font-size: 18px; font-weight: 600; margin-bottom: 20px; }
    .result-card {
        background: #252540; border-radius: 16px; padding: 24px;
        margin: 12px 0; border: 1px solid #2d2d50;
    }
    .score-badge {
        display: inline-block; background: linear-gradient(135deg, #e8b86d, #d4924a);
        color: #1a1a2e; font-weight: 800; font-size: 18px;
        padding: 4px 14px; border-radius: 24px;
    }
    .phase-tag { display: inline-block; padding: 2px 10px; border-radius: 4px; font-size: 11px; margin: 2px; }
    .phase-pass { background: rgba(92,219,139,0.15); color: #5cdb8b; }
    .phase-info { background: rgba(124,124,224,0.15); color: #7c7ce0; }
    .metric-pos { color: #5cdb8b; }
    .metric-neg { color: #e0556a; }
    .footer-text { text-align: center; color: #8b8b9e; font-size: 11px; padding: 32px 0 16px; }
    .stButton > button {
        background: linear-gradient(135deg, #e8b86d, #d4924a) !important;
        color: #1a1a2e !important; font-weight: 700 !important;
        border: none !important; border-radius: 24px !important;
        padding: 10px 32px !important; font-size: 16px !important;
        width: 100% !important;
    }
    div[data-testid="stRadio"] > div { flex-direction: column; gap: 4px; }
    div[data-testid="stRadio"] label {
        background: #1a1a2e; border: 1px solid #2d2d50; border-radius: 12px;
        padding: 12px 16px !important; color: #f0f0f0 !important; margin: 2px 0 !important;
    }
    div[data-testid="stRadio"] label:hover { border-color: #e8b86d; }
    .stProgress > div > div { background: linear-gradient(90deg, #e8b86d, #d4924a); }
    hr { border-color: #2d2d50; }
</style>
""", unsafe_allow_html=True)

# ---- 题目定义 ----
QUESTIONS = [
    # 第一部分
    ("第一部分：你是谁 + 这笔钱从哪来", None, None),
    ("Q1. 你现在处在什么阶段？", [
        "学生，没有稳定收入，但家庭能兜底",
        "刚工作 1~3 年，还在攒第一桶金",
        "工作稳定，每月有结余可以投资",
        "自由职业 / 创业，收入起伏比较大",
        "中年，有家庭负担但收入较高",
        "临近退休或已经退休，靠积蓄生活",
    ], "life_stage"),
    ("Q2. 这笔钱是从哪来的？", [
        "父母或家人给的",
        "工资攒下来的，之后还会每月定投",
        "多年的积蓄，一次性投进来",
        "年终奖 / 红包 / 一笔意外之财",
        "卖掉了其他投资转过来的",
        "借的 / 有杠杆成本的",
    ], "money_source"),
    ("Q3. 你的财务安全垫有多厚？", [
        "几乎没有，这笔钱就是全部家当",
        "有 1~3 个月生活费在活期",
        "有 3~6 个月生活费 + 基础保险",
        "有半年以上备用金 + 保险 + 家人能兜底",
        "很厚，这笔钱亏完也不影响生活",
    ], "safety_cushion"),
    ("Q4. 这笔钱的使命是什么？（可多选）", [
        "纯增值，没有具体目标",
        "为买房凑首付",
        "子女教育 / 未来学费",
        "养老储备，几十年后才用",
        "试试水，想学投资",
        "还没想好，先放着",
    ], "money_mission"),
    ("Q5. 你打算持有多久？", [
        "说不好，随时可能要拿出来（< 1 年）",
        "1 ~ 2 年",
        "2 ~ 3 年",
        "3 ~ 5 年",
        "5 年以上，能穿越一轮牛熊",
    ], "time_horizon"),
    ("Q6. 如果碰到意外，期限弹性多大？", [
        "必须按原计划，提前取出后果严重",
        "勉强能往后延半年到一年",
        "如果赔太多宁愿多等几年也不割肉",
        "很灵活，时间不是问题",
    ], "horizon_flex"),

    # 第二部分
    ("第二部分：几个真实场景，你怎么做", None, None),
    ("Q7. 投了一万块，一个月后变八千五。第一反应？", [
        "睡不着，立刻全部卖掉",
        "很焦虑，但先忍住不动",
        "还好，几个月后再看",
        "有点兴奋，觉得跌出机会了",
        "已经在想怎么凑钱加仓了",
    ], "scene_dd_1m"),
    ("Q8. 六个月还在跌，亏了 30%。怎么做？", [
        "后悔当初没割，现在赶紧卖",
        "不看了，删 App，装死",
        "不动，按原计划继续定投",
        "这时候才是真正该买的时候，加仓",
    ], "scene_dd_6m"),
    ("Q9. 两年不涨。朋友买的涨了 40%。你怎么想？", [
        "受不了，换到朋友那只",
        "有点怀疑自己的选择，但再看看",
        "无所谓，选的时候就清楚为什么选它",
        "朋友运气好而已，我的逻辑没问题",
    ], "scene_fomo"),
    ("Q10. 看到一只基金去年涨了 80%，你会？", [
        "赶紧研究，想买",
        "羡慕，但先看看为什么涨",
        "去年涨这么多，今年可能够呛，避开",
        "没感觉，不看排行榜",
    ], "scene_chase"),
    ("Q11. 大盘跌 5%，新闻全是坏消息。看账户频率？", [
        "不停地刷，手心出汗",
        "每天看一次净值",
        "每周看一次就够了",
        "不怎么看，反正长期持有",
        "忘了还有账户这回事",
    ], "watch_freq"),
    ("Q12. 选这只基金的最主要依据？", [
        "排行榜上收益率高",
        "朋友 / 大 V / 群里的推荐",
        "自己研究过持仓和基金经理",
        "跟着指数买的，没怎么挑",
        "平台推荐的",
        "还没买过，说不上来",
    ], "select_basis"),

    # 第三部分
    ("第三部分：投资这件事，你真实的样子", None, None),
    ("Q13. 你以前投过什么？", [
        "只存过银行存款 / 余额宝",
        "买过理财 / 保险，没碰过基金",
        "买过基金，定投为主",
        "基金 + 股票都碰过",
        "各种都试过，包括加密货币 / 期货",
    ], "past_invest"),
    ("Q14. 亏损最多那次，你实际做了什么？", [
        "恐慌卖出，割在地板上",
        "什么都不做，装作没看见",
        "按原计划定投，没动",
        "加仓了",
        "没亏过 / 没投过",
    ], "past_loss"),
    ("Q15. 你平时从哪获取投资信息？最信谁的？", [
        "抖音 / B站 / 小红书的博主",
        "微信群 / QQ群里的朋友",
        "天天基金 / 支付宝的推荐",
        "基金经理的季报 / 年报",
        "自己看数据，不太听别人的",
        "基本不看，被动买",
    ], "info_source"),

    # 第四部分
    ("第四部分：你怎么看投资这件事", None, None),
    ("Q16. 你的基金突然换基金经理了。怎么做？", [
        "立刻卖掉，买它就是买这个人",
        "观察一个季度，不行再换",
        "换不换人无所谓，看持仓和数据",
        "我买的是指数型，不影响",
    ], "manager_change"),
    ("Q17. 你觉得能判断什么时候买卖吗？", [
        "我觉得我大概能判断",
        "感觉有把握的时候买卖过，结果不太好",
        "不太能，所以尽量少操作",
        "完全不认为有人能择时，我也不行",
    ], "timing_confidence"),
    ("Q18. 哪个更让你睡不着觉？", [
        "亏了 20%，还没涨回来",
        "没亏，但别人赚 30% 我踏空了",
        "两个都会",
        "两个都不会，我睡得挺好",
    ], "sleep_issue"),

    # 第五部分
    ("第五部分：你的偏好", None, None),
    ("Q19. 有没有比较看好的方向？（可多选）", [
        "科技 / 互联网 / AI",
        "消费 / 白酒 / 医药",
        "新能源 / 制造 / 汽车",
        "金融 / 地产 / 红利",
        "港股 / 海外市场",
        "没有特别方向，广撒网",
    ], "preferred_sectors"),
    ("Q20. 有没有不想碰的？（可多选）", [
        "军工",
        "石油 / 煤炭等传统能源",
        "高杠杆 / 衍生品",
        "房地产相关",
    ], "excludes"),
]

MULTI_SELECT_KEYS = {"money_mission", "preferred_sectors", "excludes"}


def run():
    # ---- 头部 ----
    st.markdown('<div class="brand-id">一入向北</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-header">基金匹配器</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">没有最好的基金，只有最适合自己需求的</div>', unsafe_allow_html=True)

    # ---- 状态初始化 ----
    if "step" not in st.session_state:
        st.session_state.step = 0
        st.session_state.answers = {}
        st.session_state.results = None
        st.session_state.stats = None

    # ---- 问卷阶段 ----
    if st.session_state.results is None:
        total_real = sum(1 for _, _, k in QUESTIONS if k is not None)
        current = st.session_state.step

        if current >= len(QUESTIONS):
            # 完成问卷 → 运行匹配
            try:
                with st.spinner("正在全市场匹配（首次约需 1 分钟）..."):
                    raw = st.session_state.answers
                    profile = build_profile(raw)
                    warnings = profile.pop("_warnings", [])

                    results, stats = do_match(profile, limit=10)

                    st.session_state.results = results
                    st.session_state.stats = stats
                    st.session_state.profile = profile
                    st.session_state.warnings = warnings
                st.rerun()
            except Exception as e:
                st.error(f"匹配过程出错：{e}")
                st.info("可能是网络不稳定或数据源暂时不可用，请稍后重试。")
                if st.button("🔄 重试"):
                    st.rerun()

        q_text, q_options, q_key = QUESTIONS[current]

        if q_key is None:
            # 章节标题
            st.markdown(f"### {q_text}")
            st.button("继续 →", key=f"section_{current}", on_click=lambda: st.session_state.update({"step": current + 1}))
        else:
            # 题目
            progress = sum(1 for _, _, k in QUESTIONS[:current] if k is not None) / total_real
            st.progress(progress)
            st.caption(f"进度 {sum(1 for _,_,k in QUESTIONS[:current] if k is not None)}/{total_real}")

            st.markdown(f'<div class="question-card"><div class="question-text">{q_text}</div>', unsafe_allow_html=True)

            is_multi = q_key in MULTI_SELECT_KEYS
            default_val = st.session_state.answers.get(q_key, [] if is_multi else None)

            if is_multi:
                selected = []
                for i, opt in enumerate(q_options):
                    key = f"{q_key}_{i}"
                    default_checked = i in (default_val if isinstance(default_val, list) else [])
                    if st.checkbox(opt, value=default_checked, key=key):
                        selected.append(i)
                st.markdown('</div>', unsafe_allow_html=True)

                if st.button("继续 →", key=f"btn_{current}"):
                    st.session_state.answers[q_key] = selected
                    st.session_state.step = current + 1
                    st.rerun()
            else:
                choice = st.radio("", q_options, index=default_val if default_val is not None else 0,
                                  key=f"radio_{current}", label_visibility="collapsed")
                st.markdown('</div>', unsafe_allow_html=True)

                if st.button("继续 →", key=f"btn_{current}"):
                    st.session_state.answers[q_key] = q_options.index(choice) if choice in q_options else 0
                    st.session_state.step = current + 1
                    st.rerun()

    else:
        # ---- 报告阶段 ----
        results = st.session_state.results
        profile = st.session_state.profile
        warnings = st.session_state.warnings
        stats_dict = st.session_state.stats

        st.markdown("---")

        # 画像摘要
        horizon_label = {"short": "偏短期", "medium": "中期", "long": "长期"}
        risk_label = {"conservative": "稳健优先", "moderate": "平衡", "aggressive": "愿意进取"}
        style_label = {"active": "倾向主动型", "passive": "倾向被动型", "both": "不限风格"}

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("投资期限", horizon_label.get(profile.get("time_horizon", ""), "?"))
        with col2:
            st.metric("回撤容忍", f'{profile.get("max_dd_tolerance", 0):.0%}')
        with col3:
            st.metric("风险偏好", risk_label.get(profile.get("return_preference", ""), "?"))
        with col4:
            st.metric("风格", style_label.get(profile.get("style_preference", ""), "?"))

        if profile.get("preferred_sectors"):
            st.caption(f"偏好方向：{' · '.join(profile['preferred_sectors'])}")

        if warnings:
            with st.expander(f"⚠️ 发现 {len(warnings)} 个提醒"):
                for w in warnings:
                    st.markdown(f"- {w}")

        st.markdown("---")

        if not results:
            st.warning("没有找到匹配的基金，试试放宽条件。")
            if st.button("🔁 重新测评"):
                for k in list(st.session_state.keys()):
                    del st.session_state[k]
                st.rerun()
            return

        st.markdown(f"### 🎯 匹配结果（{len(results)} 只）")

        for rank, r in enumerate(results, 1):
            f = r["fund"]
            m = r["metrics"]
            p = r["phases"]
            score = r["final_score"]

            score_color = "#5cdb8b" if score >= 80 else "#e8b86d" if score >= 60 else "#e0556a"

            mgr_years = f.get("manager_days", 0) / 365
            fund_years = len(f.get("nav_list", [])) // 250 if f.get("nav_list") else "?"

            pos = lambda v: "metric-pos" if (v or 0) > 0 else "metric-neg"

            st.markdown(f"""
            <div class="result-card">
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
                    <span style="font-size:20px;font-weight:700;color:#7c7ce0;">#{rank}</span>
                    <span style="font-size:17px;font-weight:600;color:#f0f0f0;flex:1;">{f['name']}</span>
                    <span style="font-size:12px;color:#8b8b9e;">{f['code']}</span>
                    <span class="score-badge">{score:.0f}%</span>
                </div>
            """, unsafe_allow_html=True)

            c1, c2, c3 = st.columns(3)
            with c1:
                st.caption("📊 收益表现")
                s = f["syl"]
                st.markdown(f'近1月 <span class="{pos(s.get("近1月"))}">{_pct(s.get("近1月"))}</span>', unsafe_allow_html=True)
                st.markdown(f'近3月 <span class="{pos(s.get("近3月"))}">{_pct(s.get("近3月"))}</span>', unsafe_allow_html=True)
                st.markdown(f'近6月 <span class="{pos(s.get("近6月"))}">{_pct(s.get("近6月"))}</span>', unsafe_allow_html=True)
                st.markdown(f'近1年 <span class="{pos(s.get("近1年"))}">{_pct(s.get("近1年"))}</span>', unsafe_allow_html=True)
            with c2:
                st.caption("⚠️ 风险指标")
                st.markdown(f'最大回撤 <span class="metric-neg">-{m["max_drawdown"]*100:.1f}%</span>', unsafe_allow_html=True)
                st.markdown(f'年化波动率 {m["annual_volatility"]*100:.1f}%')
                st.markdown(f'下行波动率 {m["downside_volatility"]*100:.1f}%')
                st.markdown(f'回撤恢复 {m["recovery_days"]}天')
            with c3:
                st.caption("💰 效率指标")
                st.markdown(f'夏普比率 {m["sharpe"]:.2f}')
                st.markdown(f'卡玛比率 {m["calmar"]:.2f}')
                st.markdown(f'索提诺比率 {m["sortino"]:.2f}')
                st.markdown(f'月度胜率 {m["win_rate_monthly"]*100:.0f}%')

            st.caption(f"👤 {f.get('manager', '?')} · 从业{mgr_years:.0f}年 · 📋 {f.get('type', '?')} · 💵 申购费率 {f.get('current_rate') or f.get('source_rate') or '?'}% · 📅 成立约{fund_years}年")

            tags = ""
            tags += f'<span class="phase-tag phase-pass">P1:{p["p1"]["score"]:.0f}</span> '
            tags += f'<span class="phase-tag phase-pass">P2:{p["p2"]["score"]:.0f}</span> '
            tags += f'<span class="phase-tag phase-pass">P3:{p["p3"]["score"]:.0f}</span> '
            tags += f'<span class="phase-tag phase-info">P4:{p["p4"]["score"]:.0f}</span> '
            st.markdown(tags, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # 预筛统计
        if stats_dict:
            with st.expander("📋 候选范围说明"):
                total = stats_dict.get("total", 0)
                exc_type = stats_dict.get("excluded_type", 0)
                exc_share = stats_dict.get("excluded_share", 0)
                exc_struct = stats_dict.get("excluded_structure", 0)
                remaining = total - exc_type - exc_share - exc_struct
                st.markdown(f"""
                全市场 **{total}** 只基金 →
                排除低风险类型 **{exc_type}** 只 +
                非主流份额 **{exc_share}** 只 +
                结构不适合 **{exc_struct}** 只 =
                进入匹配 **{remaining}** 只
                """)

        # 底部
        st.markdown("---")
        st.markdown('<div class="footer-text">', unsafe_allow_html=True)
        st.markdown('**一入向北** · 没有最好的基金，只有最适合自己需求的', unsafe_allow_html=True)
        st.markdown('数据来源：天天基金 (fund.eastmoney.com)', unsafe_allow_html=True)
        st.markdown('⚠️ 本报告仅基于公开历史数据的量化匹配，不构成投资建议', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # 重置按钮
        if st.button("🔁 重新测评"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


def _pct(val):
    if val is None:
        return "N/A"
    return f"{val:+.2f}%"


if __name__ == "__main__":
    run()
