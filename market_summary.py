#!/usr/bin/env python3
"""
US市場まとめ → Discord通知
yfinance で主要指数・セクター騰落率を取得し、関連日本株とともに送信
"""

import os
import sys
import yfinance as yf
import requests
from datetime import datetime
import pytz

DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1507586341331013653/"
    "FytNRovQCQPRF4uYCOS8COvWFPdh9mzPAcJKTFBmiXyoYl8KANvYMdHmQLhmhT1Eg95I"
)

INDICES = {
    "S&P 500":      "^GSPC",
    "Nasdaq":       "^IXIC",
    "Dow Jones":    "^DJI",
    "Russell 2000": "^RUT",
}

# (ETFティッカー, 絵文字)
SECTORS = {
    "テクノロジー":  ("XLK",  "💻"),
    "金融":          ("XLF",  "🏦"),
    "エネルギー":    ("XLE",  "⛽"),
    "ヘルスケア":    ("XLV",  "💊"),
    "一般消費財":    ("XLY",  "🛍️"),
    "生活必需品":    ("XLP",  "🛒"),
    "資本財":        ("XLI",  "🏭"),
    "素材":          ("XLB",  "⚗️"),
    "公益事業":      ("XLU",  "💡"),
    "不動産":        ("XLRE", "🏠"),
    "通信サービス":  ("XLC",  "📡"),
}

# セクター → 注目日本株 (コード, 社名)
JP_STOCKS: dict[str, list[tuple[str, str]]] = {
    "テクノロジー":  [("6758.T","ソニーG"),("6861.T","キーエンス"),("7974.T","任天堂"),
                      ("9984.T","ソフトバンクG"),("6098.T","リクルートHD")],
    "金融":          [("8306.T","三菱UFJ"),("8411.T","みずほFG"),("8316.T","三井住友FG"),
                      ("8591.T","オリックス"),("8604.T","野村HD")],
    "エネルギー":    [("5020.T","ENEOS"),("1605.T","INPEX")],
    "ヘルスケア":    [("4502.T","武田薬品"),("4519.T","中外製薬"),("4568.T","第一三共"),
                      ("4543.T","テルモ")],
    "一般消費財":    [("7203.T","トヨタ"),("7267.T","本田技研"),("6902.T","デンソー"),
                      ("7201.T","日産")],
    "生活必需品":    [("2914.T","JT"),("2802.T","味の素"),("4452.T","花王"),("2503.T","キリンHD")],
    "資本財":        [("6301.T","コマツ"),("6326.T","クボタ"),("7011.T","三菱重工"),("7013.T","IHI")],
    "素材":          [("5401.T","日本製鉄"),("4063.T","信越化学"),("3407.T","旭化成")],
    "公益事業":      [("9503.T","関西電力"),("9531.T","東京ガス"),("9501.T","東京電力HD")],
    "不動産":        [("8801.T","三井不動産"),("8802.T","三菱地所"),("8830.T","住友不動産")],
    "通信サービス":  [("9432.T","NTT"),("9433.T","KDDI"),("9434.T","ソフトバンク")],
}


def get_pct_change(ticker: str) -> float | None:
    """直近2営業日の騰落率(%)を返す。データなし・休場時は None"""
    try:
        df = yf.download(ticker, period="5d", interval="1d", progress=False, auto_adjust=True)
        if df.empty:
            return None
        closes = df["Close"].squeeze().dropna()
        if len(closes) < 2:
            return None
        return float((closes.iloc[-1] / closes.iloc[-2] - 1) * 100)
    except Exception:
        return None


def sector_reason(sector: str, ret: float, mkt_ret: float, vix: float) -> str:
    """マクロ環境からセクターの強弱理由を推測"""
    outperformed = ret > mkt_ret + 0.3
    risk_on  = mkt_ret >  0.3
    risk_off = mkt_ret < -0.3
    hi_vix   = vix > 22

    table: dict[str, tuple[str, str]] = {
        "テクノロジー": (
            "AI・半導体関連への旺盛な資金流入" if outperformed else "グロース株全般の買い戻し",
            "金利上昇懸念でバリュエーション調整圧力"
        ),
        "金融": (
            "長期金利上昇が利ざや拡大期待を後押し" if outperformed else "景気拡大期待で与信コスト低下を先読み",
            "景気後退懸念で不良債権リスクが意識される"
        ),
        "エネルギー": (
            "原油・天然ガス価格の上昇が業績を直撃",
            "原油安・需要鈍化懸念で利益確定売り"
        ),
        "ヘルスケア": (
            "リスクオフでディフェンシブ需要が高まる" if (risk_off or hi_vix) else "医薬品・医療機器の好決算が支援材料",
            "薬価規制リスクや決算失望が売り材料に"
        ),
        "一般消費財": (
            "個人消費の底堅さと雇用改善を好感" if risk_on else "EC・小売大手の好決算が牽引",
            "消費者マインド悪化・インフレ長期化を懸念"
        ),
        "生活必需品": (
            "リスクオフでディフェンシブ株に資金シフト" if (risk_off or hi_vix) else "価格転嫁進展で収益改善を評価",
            "リスクオン相場で高成長セクターへ資金流出"
        ),
        "資本財": (
            "景気サイクル改善期待とインフラ投資需要の高まり" if risk_on else "防衛・航空宇宙関連の受注増が支援",
            "製造業PMI低下で景気敏感株に慎重姿勢"
        ),
        "素材": (
            "インフレ再燃・中国需要回復期待でコモディティ高",
            "中国景気鈍化・ドル高でコモディティ軟調"
        ),
        "公益事業": (
            "リスクオフ＋金利低下期待でディフェンシブ買い" if (risk_off or hi_vix) else "AI電力需要増による長期需要拡大を先読み",
            "金利上昇で高利回りセクターの相対妙味が低下"
        ),
        "不動産": (
            "金利低下期待でREITのバリュエーション改善",
            "長期金利上昇でキャップレート上昇・資産価値に下押し"
        ),
        "通信サービス": (
            "メガキャップ・広告収入の好調が全体を牽引" if risk_on else "ストリーミング・クラウド関連の強い決算",
            "広告市場の鈍化や規制強化リスクが重し"
        ),
    }

    up_reason, down_reason = table.get(sector, ("セクター固有の好材料", "セクター固有の悪材料"))
    return up_reason if ret >= 0 else down_reason


def fmt(pct: float) -> str:
    arrow = "▲" if pct >= 0 else "▼"
    return f"{arrow}{abs(pct):.2f}%"


def main() -> None:
    jst = pytz.timezone("Asia/Tokyo")
    now_jst = datetime.now(jst)

    # ── 主要指数 ─────────────────────────────────────────────
    index_rets: dict[str, float] = {}
    for name, ticker in INDICES.items():
        r = get_pct_change(ticker)
        if r is not None:
            index_rets[name] = r

    if not index_rets:
        print("市場データなし（休場の可能性）。送信スキップ。")
        return

    sp500 = index_rets.get("S&P 500", 0.0)

    # ── VIX ──────────────────────────────────────────────────
    vix_df = yf.download("^VIX", period="5d", interval="1d", progress=False, auto_adjust=True)
    vix_closes = vix_df["Close"].squeeze().dropna() if not vix_df.empty else []
    vix_now  = float(vix_closes.iloc[-1]) if len(vix_closes) > 0 else 18.0
    vix_chg  = float((vix_closes.iloc[-1] / vix_closes.iloc[-2] - 1) * 100) if len(vix_closes) >= 2 else 0.0

    # ── セクター ─────────────────────────────────────────────
    sector_rets: dict[str, float] = {}
    for name, (ticker, _) in SECTORS.items():
        r = get_pct_change(ticker)
        if r is not None:
            sector_rets[name] = r

    ranked = sorted(sector_rets.items(), key=lambda x: x[1], reverse=True)
    top3    = ranked[:3]
    bottom3 = ranked[-3:]

    # ── 全体環境 ──────────────────────────────────────────────
    if sp500 > 0.5:
        mood = "🟢 リスクオン"
    elif sp500 < -0.5:
        mood = "🔴 リスクオフ"
    else:
        mood = "🟡 方向感なし"

    trade_date = now_jst.strftime("%Y/%m/%d")

    # ── 指数フィールド ────────────────────────────────────────
    idx_lines = [
        f"{'🟢' if r >= 0 else '🔴'} **{n}** {fmt(r)}"
        for n, r in index_rets.items()
    ]
    idx_lines.append(
        f"{'🔴' if vix_chg > 0 else '🟢'} **VIX** {vix_now:.1f} ({fmt(vix_chg)})"
    )

    # ── 強いセクター TOP3（理由＋日本株付き）────────────────
    strong_lines: list[str] = []
    for sector, ret in top3:
        emoji  = SECTORS[sector][1]
        reason = sector_reason(sector, ret, sp500, vix_now)
        jp_str = "・".join(name for _, name in JP_STOCKS.get(sector, [])[:3])
        strong_lines.append(
            f"{emoji} **{sector}** {fmt(ret)}\n"
            f"　💬 {reason}\n"
            f"　🇯🇵 注目: {jp_str}"
        )

    # ── 弱いセクター BOTTOM3（理由付き）─────────────────────
    weak_lines: list[str] = []
    for sector, ret in bottom3:
        emoji  = SECTORS[sector][1]
        reason = sector_reason(sector, ret, sp500, vix_now)
        weak_lines.append(f"{emoji} **{sector}** {fmt(ret)} — {reason}")

    # ── 全セクター一覧 ────────────────────────────────────────
    all_lines = [
        f"{'🟢' if r >= 0 else '🔴'} {sec:<8} `{'▲' if r >= 0 else '▼'}{abs(r):.2f}%`"
        for sec, r in ranked
    ]

    embed_color = 0x00C853 if sp500 >= 0 else 0xD50000

    embeds = [
        {
            "title": f"🌙 米国市場まとめ — {trade_date}",
            "description": f"**{mood}**　｜　VIX: {vix_now:.1f}（{fmt(vix_chg)}）",
            "color": embed_color,
            "fields": [
                {"name": "📊 主要指数",
                 "value": "\n".join(idx_lines),
                 "inline": False},
                {"name": "🔥 強かったセクター TOP3",
                 "value": "\n\n".join(strong_lines),
                 "inline": False},
                {"name": "❄️ 弱かったセクター BOTTOM3",
                 "value": "\n".join(weak_lines),
                 "inline": False},
                {"name": "📋 全セクター",
                 "value": "\n".join(all_lines),
                 "inline": False},
            ],
            "footer": {
                "text": f"データ: Yahoo Finance  |  {now_jst.strftime('%H:%M JST')} 配信"
            },
        }
    ]

    resp = requests.post(DISCORD_WEBHOOK_URL, json={"embeds": embeds}, timeout=15)
    if resp.status_code in (200, 204):
        print(f"[{now_jst.strftime('%Y-%m-%d %H:%M JST')}] Discord送信完了")
    else:
        print(f"Discord送信失敗: {resp.status_code} {resp.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
