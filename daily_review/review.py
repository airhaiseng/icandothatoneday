#!/usr/bin/env python3
"""Read-only nightly strategy review.

Fetches free daily bars (Binance market-data mirror for crypto, Sina/Tencent/
Eastmoney for A-shares), runs three rule-based strategies, and writes a Chinese
Markdown report under reports/.

No third-party Python packages are required. No orders are placed.
"""

from __future__ import annotations

import csv
import json
import math
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.json"
DATA_DIR = BASE / "data"
REPORT_DIR = BASE / "reports"
BEIJING = timezone(timedelta(hours=8))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DSH-Daily-Review/1.0",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://finance.sina.com.cn/",
}


# --------------------------------------------------------------------------
# utilities
# --------------------------------------------------------------------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat(timespec="seconds")


def http_text(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return raw.decode("utf-8", "replace")


def http_json(url: str, timeout: int = 25):
    return json.loads(http_text(url, timeout))


def fnum(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_symbol(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", symbol)


def fmt_pct(value, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value * 100:+.{digits}f}%"


def fmt_money(value, currency: str) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f} {currency}"


def fmt_num(value, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def pct_change(new, old) -> float | None:
    if new is None or old in (None, 0):
        return None
    return new / old - 1


# --------------------------------------------------------------------------
# data providers
# --------------------------------------------------------------------------

def parse_binance_rows(rows, now_ms: int):
    bars = []
    for row in rows:
        try:
            open_time = int(row[0])
            close_time = int(row[6])
            if close_time > now_ms:
                continue
            bars.append({
                "date": datetime.fromtimestamp(open_time / 1000, tz=timezone.utc).date().isoformat(),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            })
        except (TypeError, ValueError, IndexError):
            continue
    bars.sort(key=lambda b: b["date"])
    return bars


def fetch_crypto(symbol: str, limit: int):
    errors = []
    now_ms = int(time.time() * 1000)
    for base in ("https://data-api.binance.vision", "https://api.binance.com"):
        try:
            rows = http_json(f"{base}/api/v3/klines?symbol={symbol}&interval=1d&limit={limit}")
            bars = parse_binance_rows(rows, now_ms)
            if len(bars) < 40:
                raise RuntimeError(f"only {len(bars)} completed daily bars")
            price = None
            try:
                price = fnum(http_json(f"{base}/api/v3/ticker/price?symbol={symbol}").get("price"))
            except Exception:
                price = bars[-1]["close"]
            return {
                "symbol": symbol,
                "market": "crypto",
                "bars": bars,
                "source": "Binance market-data (" + base.replace("https://", "") + ")",
                "current_price": price or bars[-1]["close"],
                "fetched_at": iso_now(),
                "stale": False,
                "error": "",
            }
        except Exception as exc:
            errors.append(f"{base}: {type(exc).__name__}: {exc}")
    raise RuntimeError("crypto fetch failed; " + " | ".join(errors))


def parse_sina(text: str):
    rows = json.loads(text)
    bars = []
    for row in rows:
        bars.append({
            "date": str(row["day"])[:10],
            "open": fnum(row.get("open")),
            "high": fnum(row.get("high")),
            "low": fnum(row.get("low")),
            "close": fnum(row.get("close")),
            "volume": fnum(row.get("volume"), 0.0) or 0.0,
        })
    bars = [b for b in bars if b["close"] is not None]
    bars.sort(key=lambda b: b["date"])
    return bars


def parse_tencent(text: str, symbol: str):
    obj = json.loads(text)
    node = (obj.get("data") or {}).get(symbol) or {}
    rows = node.get("qfqday") or node.get("day") or []
    bars = []
    for row in rows:
        # Tencent: [date, open, close, high, low, volume]
        if len(row) < 6:
            continue
        bars.append({
            "date": str(row[0])[:10],
            "open": fnum(row[1]),
            "close": fnum(row[2]),
            "high": fnum(row[3]),
            "low": fnum(row[4]),
            "volume": fnum(row[5], 0.0) or 0.0,
        })
    bars = [b for b in bars if b["close"] is not None]
    bars.sort(key=lambda b: b["date"])
    return bars


def parse_eastmoney(text: str):
    obj = json.loads(text)
    node = obj.get("data") or {}
    rows = node.get("klines") or []
    bars = []
    for row in rows:
        # Eastmoney: date,open,close,high,low,volume,amount,...
        parts = str(row).split(",")
        if len(parts) < 6:
            continue
        bars.append({
            "date": parts[0][:10],
            "open": fnum(parts[1]),
            "close": fnum(parts[2]),
            "high": fnum(parts[3]),
            "low": fnum(parts[4]),
            "volume": fnum(parts[5], 0.0) or 0.0,
        })
    bars = [b for b in bars if b["close"] is not None]
    bars.sort(key=lambda b: b["date"])
    return bars


def fetch_ashare(symbol: str, limit: int):
    """symbol like sh600519 / sz000001."""
    errors = []
    now = datetime.now(BEIJING)
    # Sina
    try:
        url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
               f"CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={limit}")
        bars = parse_sina(http_text(url))
        if len(bars) < 40:
            raise RuntimeError(f"only {len(bars)} bars")
        # At 22:00 the A-share day bar is complete. Drop it only before close.
        if bars and bars[-1]["date"] == now.date().isoformat() and now.hour < 15:
            bars.pop()
        return {
            "symbol": symbol,
            "market": "ashare",
            "bars": bars,
            "source": "Sina finance daily K-line",
            "current_price": bars[-1]["close"],
            "fetched_at": iso_now(),
            "stale": False,
            "error": "",
        }
    except Exception as exc:
        errors.append(f"Sina: {type(exc).__name__}: {exc}")

    # Tencent
    try:
        url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
               f"param={symbol},day,,,{limit},qfq")
        bars = parse_tencent(http_text(url), symbol)
        if len(bars) < 40:
            raise RuntimeError(f"only {len(bars)} bars")
        if bars and bars[-1]["date"] == now.date().isoformat() and now.hour < 15:
            bars.pop()
        return {
            "symbol": symbol,
            "market": "ashare",
            "bars": bars,
            "source": "Tencent finance qfq daily K-line",
            "current_price": bars[-1]["close"],
            "fetched_at": iso_now(),
            "stale": False,
            "error": "",
        }
    except Exception as exc:
        errors.append(f"Tencent: {type(exc).__name__}: {exc}")

    # Eastmoney
    try:
        code = symbol[2:] if symbol[:2] in ("sh", "sz") else symbol
        secid = ("1." if symbol.startswith("sh") else "0.") + code
        url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?"
               f"secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56"
               f"&klt=101&fqt=1&end=20500101&lmt={limit}")
        bars = parse_eastmoney(http_text(url))
        if len(bars) < 40:
            raise RuntimeError(f"only {len(bars)} bars")
        if bars and bars[-1]["date"] == now.date().isoformat() and now.hour < 15:
            bars.pop()
        return {
            "symbol": symbol,
            "market": "ashare",
            "bars": bars,
            "source": "Eastmoney push2his daily K-line (qfq)",
            "current_price": bars[-1]["close"],
            "fetched_at": iso_now(),
            "stale": False,
            "error": "",
        }
    except Exception as exc:
        errors.append(f"Eastmoney: {type(exc).__name__}: {exc}")

    raise RuntimeError("A-share fetch failed; " + " | ".join(errors))


def cache_path(symbol: str) -> Path:
    return DATA_DIR / f"{safe_symbol(symbol)}.json"


def save_cache(md: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(md)
    payload["fetched_at"] = iso_now()
    cache_path(md["symbol"]).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cache(symbol: str):
    path = cache_path(symbol)
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not obj.get("bars"):
            return None
        obj["stale"] = True
        obj["error"] = obj.get("error") or "network failed, using local cache"
        return obj
    except Exception:
        return None


def load_market(strategy: dict, limit: int) -> dict:
    symbol = strategy["symbol"]
    market = strategy["market"]
    try:
        if market == "crypto":
            md = fetch_crypto(symbol, limit)
        else:
            md = fetch_ashare(symbol, limit)
        save_cache(md)
        return md
    except Exception as exc:
        cached = load_cache(symbol)
        if cached:
            cached["stale"] = True
            cached["error"] = f"{type(exc).__name__}: {exc}"
            return cached
        return {
            "symbol": symbol,
            "market": market,
            "bars": [],
            "source": "unavailable",
            "current_price": None,
            "fetched_at": iso_now(),
            "stale": True,
            "error": f"{type(exc).__name__}: {exc}",
        }


# --------------------------------------------------------------------------
# indicators and strategies
# --------------------------------------------------------------------------

def sma(values, window: int):
    out = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= window:
            total -= values[i - window]
        if i >= window - 1:
            out[i] = total / window
    return out


def rsi_wilder(values, period: int = 14):
    out = [None] * len(values)
    if len(values) <= period:
        return out
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    def rsi_value(gain, loss):
        if gain == 0 and loss == 0:
            return 50.0
        if loss == 0:
            return 100.0
        rs = gain / loss
        return 100.0 - 100.0 / (1.0 + rs)

    out[period] = rsi_value(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        diff = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(diff, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-diff, 0.0)) / period
        out[i] = rsi_value(avg_gain, avg_loss)
    return out


def momentum(values, lookback: int):
    out = [None] * len(values)
    for i in range(lookback, len(values)):
        if values[i - lookback] != 0:
            out[i] = values[i] / values[i - lookback] - 1.0
    return out


def build_positions(strategy: dict, closes):
    typ = strategy["type"]
    params = strategy.get("params") or {}
    n = len(closes)
    indicators = {}

    if typ == "ma":
        fast = int(params.get("fast", 5))
        slow = int(params.get("slow", 20))
        fast_ma = sma(closes, fast)
        slow_ma = sma(closes, slow)
        positions = []
        for i in range(n):
            if fast_ma[i] is None or slow_ma[i] is None:
                positions.append(0)
            else:
                positions.append(1 if fast_ma[i] > slow_ma[i] else 0)
        indicators.update({"ma_fast": fast_ma, "ma_slow": slow_ma, "fast": fast, "slow": slow})
        return positions, indicators

    if typ == "rsi":
        period = int(params.get("period", 14))
        oversold = float(params.get("oversold", 30))
        overbought = float(params.get("overbought", 70))
        rsi = rsi_wilder(closes, period)
        positions = [0] * n
        state = 0
        for i in range(1, n):
            prev, cur = rsi[i - 1], rsi[i]
            if state == 0 and prev is not None and cur is not None and prev <= oversold < cur:
                state = 1
            elif state == 1 and prev is not None and cur is not None and prev >= overbought > cur:
                state = 0
            positions[i] = state
        indicators.update({"rsi": rsi, "period": period, "oversold": oversold, "overbought": overbought})
        return positions, indicators

    if typ == "momentum":
        lookback = int(params.get("lookback", 20))
        threshold = float(params.get("threshold", 0.05))
        mom = momentum(closes, lookback)
        positions = [1 if (mom[i] is not None and mom[i] > threshold) else 0 for i in range(n)]
        indicators.update({"momentum": mom, "lookback": lookback, "threshold": threshold})
        return positions, indicators

    raise ValueError(f"unknown strategy type: {typ}")


def compute(strategy: dict, market_data: dict, initial: float) -> dict:
    bars = market_data.get("bars") or []
    if len(bars) < 30:
        return {"ok": False, "error": market_data.get("error") or "not enough bars", "market": market_data}

    closes = [b["close"] for b in bars]
    dates = [b["date"] for b in bars]
    positions, indicators = build_positions(strategy, closes)
    fee_rate = float(strategy.get("fee_rate", 0.0))
    n = len(bars)

    equity = [float(initial)]
    fees = []
    for i in range(1, n):
        day_return = closes[i] / closes[i - 1] - 1.0
        pnl = equity[-1] * positions[i - 1] * day_return
        fee = 0.0
        if positions[i] != positions[i - 1]:
            fee = equity[-1] * fee_rate * abs(positions[i] - positions[i - 1])
        equity.append(max(0.0, equity[-1] + pnl - fee))
        fees.append(fee)

    eq_prev = equity[-2] if len(equity) >= 2 else equity[-1]
    latest_day_pnl = equity[-1] - eq_prev
    latest_day_return = latest_day_pnl / eq_prev if eq_prev else 0.0
    underlying_return = closes[-1] / closes[-2] - 1.0 if n >= 2 else 0.0
    contribution = positions[-2] * underlying_return if n >= 2 else 0.0

    current_price = market_data.get("current_price") or closes[-1]
    float_pnl = equity[-1] * positions[-1] * (current_price / closes[-1] - 1.0)
    equity_now = equity[-1] + float_pnl

    curve = equity + ([equity_now] if abs(float_pnl) > 1e-12 else [])
    peak = curve[0]
    max_dd = 0.0
    for value in curve:
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)

    daily_returns = []
    for i in range(1, len(equity)):
        if equity[i - 1] > 0:
            daily_returns.append(equity[i] / equity[i - 1] - 1.0)
    ann = 365 if strategy.get("market") == "crypto" else 252
    if len(daily_returns) >= 2:
        mean = statistics.fmean(daily_returns)
        std = statistics.pstdev(daily_returns)
        sharpe = (mean / std * math.sqrt(ann)) if std > 1e-12 else 0.0
    else:
        sharpe = 0.0

    trade_count = sum(1 for i in range(1, n) if positions[i] != positions[i - 1])
    last_change_idx = None
    for i in range(n - 1, 0, -1):
        if positions[i] != positions[i - 1]:
            last_change_idx = i
            break

    closes20 = closes[-21:] if len(closes) >= 21 else closes
    rets20 = [closes20[i] / closes20[i - 1] - 1.0 for i in range(1, len(closes20))]
    vol20 = statistics.pstdev(rets20) * math.sqrt(ann) if len(rets20) >= 2 else 0.0
    trend20 = closes[-1] / closes[-21] - 1.0 if len(closes) >= 21 else None

    latest = {}
    for key in ("ma_fast", "ma_slow", "rsi", "momentum"):
        series = indicators.get(key)
        latest[key] = series[-1] if series else None
    latest["rsi_prev"] = indicators.get("rsi", [None] * n)[-2] if n >= 2 else None
    latest["ma_fast_prev"] = indicators.get("ma_fast", [None] * n)[-2] if n >= 2 else None
    latest["ma_slow_prev"] = indicators.get("ma_slow", [None] * n)[-2] if n >= 2 else None
    latest["momentum_prev"] = indicators.get("momentum", [None] * n)[-2] if n >= 2 else None

    return {
        "ok": True,
        "market": market_data,
        "strategy": strategy,
        "bars": bars,
        "dates": dates,
        "closes": closes,
        "positions": positions,
        "indicators": indicators,
        "latest": latest,
        "equity": equity,
        "equity_now": equity_now,
        "latest_day_pnl": latest_day_pnl,
        "latest_day_return": latest_day_return,
        "underlying_return": underlying_return,
        "contribution": contribution,
        "float_pnl": float_pnl,
        "total_return": equity_now / initial - 1.0,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "trade_count": trade_count,
        "last_change_idx": last_change_idx,
        "vol20": vol20,
        "trend20": trend20,
        "current_price": current_price,
        "position_now": positions[-1],
        "position_during_last": positions[-2] if n >= 2 else 0,
        "changed_today": n >= 2 and positions[-1] != positions[-2],
    }


# --------------------------------------------------------------------------
# Chinese narrative
# --------------------------------------------------------------------------

def position_text(pos: int) -> str:
    return "多头" if pos else "空仓"


def action_text(pos: int) -> str:
    return "买入/继续持有" if pos else "卖出/保持空仓"


def reason_text(result: dict) -> str:
    s = result["strategy"]
    typ = s["type"]
    latest = result["latest"]
    pos = result["position_now"]
    underlying = result["underlying_return"]
    contribution = result["contribution"]
    trend20 = result["trend20"]
    vol20 = result["vol20"]

    parts = []
    if typ == "ma":
        p = s.get("params") or {}
        fast_n = int(p.get("fast", 5))
        slow_n = int(p.get("slow", 20))
        fast, slow = latest.get("ma_fast"), latest.get("ma_slow")
        gap = (fast / slow - 1.0) if (fast and slow) else None
        if pos:
            parts.append(f"MA{fast_n} 位于 MA{slow_n} 上方"
                         f"（乖离 {fmt_pct(gap)}），趋势跟踪模型维持多头。")
        else:
            parts.append(f"MA{fast_n} 位于 MA{slow_n} 下方"
                         f"（乖离 {fmt_pct(gap)}），模型保持空仓、规避下行。")
        if result["changed_today"]:
            parts.append(f"最新一根日线发生{'金叉' if pos else '死叉'}，按收盘信号调仓。")
    elif typ == "rsi":
        cur, prev = latest.get("rsi"), latest.get("rsi_prev")
        over_sold = (s.get("params") or {}).get("oversold", 30)
        over_bought = (s.get("params") or {}).get("overbought", 70)
        if result["changed_today"] and pos:
            parts.append(f"RSI 从超卖区（≤{over_sold}）回升至 {fmt_num(cur, 1)}，触发均值回归买入。")
        elif result["changed_today"] and not pos:
            parts.append(f"RSI 从超买区（≥{over_bought}）回落至 {fmt_num(cur, 1)}，触发止盈离场。")
        elif pos:
            parts.append(f"RSI={fmt_num(cur, 1)}，仍在持仓区，等待超买信号（≥{over_bought}）。")
        else:
            parts.append(f"RSI={fmt_num(cur, 1)}，尚未出现“超卖后回升”信号，保持空仓。")
        if prev is not None and cur is not None:
            parts.append(f"RSI 较前一日变化 {cur - prev:+.1f}。")
    elif typ == "momentum":
        mom = latest.get("momentum")
        threshold = (s.get("params") or {}).get("threshold", 0.05)
        if pos:
            parts.append(f"20 日动量 {fmt_pct(mom)}，高于 {fmt_pct(threshold)} 阈值，动量模型持仓。")
        else:
            parts.append(f"20 日动量 {fmt_pct(mom)}，未达到 {fmt_pct(threshold)} 阈值，模型空仓。")
    else:
        parts.append("按规则信号执行。")

    parts.append(f"最新日标的涨跌 {fmt_pct(underlying)}，按上一收盘持仓计算策略贡献 {fmt_pct(contribution)}。")
    if trend20 is not None:
        parts.append(f"近 20 日标的累计 {fmt_pct(trend20)}，年化波动约 {vol20 * 100:.2f}%。")
    return " ".join(parts)


def advice_text(result: dict) -> str:
    s = result["strategy"]
    typ = s["type"]
    if typ == "ma":
        return ("若近期反复穿越、假突破较多，可加入 ADX 或成交量过滤，并比较 EMA 与不同周期；"
                "当前为收盘信号、收盘成交，未计滑点与冲击成本。")
    if typ == "rsi":
        return ("单边趋势中 RSI 可能长期钝化，可加“价格在 MA60 上方才做多”的趋势过滤；"
                "建议用 25/75、20/80 两组阈值做参数敏感性测试，避免只优化一段行情。")
    if typ == "momentum":
        return ("5% 阈值对 600519 可能偏松或偏紧，建议测试 3%/5%/8% 与不同回看期；"
                "A 股 T+1、涨跌停和停牌未模拟，实盘前需补上这些约束，并加止损/波动率目标。")
    return "建议做样本外验证，并记录每次信号与成交假设。"


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def render_report(results, errors, generated_at: datetime, initial: float) -> str:
    ok_results = [r for r in results if r.get("ok")]
    dates = [r["bars"][-1]["date"] for r in ok_results]
    report_date = max(dates) if dates else generated_at.date().isoformat()
    lines = []
    lines.append(f"# 每晚策略复盘 · {report_date}")
    lines.append("")
    lines.append(f"- 生成时间：{generated_at.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    lines.append(f"- 初始资金：每个策略独立 100,000（crypto 为 USDT，A 股为 CNY）")
    lines.append("- 数据口径：日线收盘；信号在收盘确认，按收盘价成交；不构成投资建议。")
    lines.append("")
    lines.append("## 一、结论")
    lines.append("")
    if ok_results:
        for r in ok_results:
            s = r["strategy"]
            lines.append(
                f"- **{s['id']} {s['name']}（{s['symbol']}）**：当前{position_text(r['position_now'])}，"
                f"最新日盈亏 {fmt_money(r['latest_day_pnl'], s['currency'])}"
                f"（{fmt_pct(r['latest_day_return'])}），累计 {fmt_pct(r['total_return'])}。"
            )
        avg_day = statistics.fmean([r["latest_day_return"] for r in ok_results])
        avg_total = statistics.fmean([r["total_return"] for r in ok_results])
        lines.append(f"- **等权参考组合**：最新日平均 {fmt_pct(avg_day)}，平均累计 {fmt_pct(avg_total)}。"
                     "（仅三策略等权平均，不是真实组合净值。）")
    else:
        lines.append("- 本次没有取得可用行情，详见“数据质量”。")
    lines.append("")

    lines.append("## 二、策略明细")
    lines.append("")
    for r in ok_results:
        s = r["strategy"]
        cur = s["currency"]
        lines.append(f"### {s['id']} · {s['name']}（{s['symbol']}）")
        lines.append("")
        lines.append(f"- 最新完整日线：**{r['bars'][-1]['date']}**，收盘 **{fmt_num(r['closes'][-1], 4)}**，"
                     f"当前价 **{fmt_num(r['current_price'], 4)}**")
        lines.append(f"- 当前仓位：**{position_text(r['position_now'])}**；最新日盈亏 "
                     f"**{fmt_money(r['latest_day_pnl'], cur)}**（{fmt_pct(r['latest_day_return'])}）；"
                     f"当前浮动 **{fmt_money(r['float_pnl'], cur)}**")
        lines.append(f"- 账户权益：**{fmt_money(r['equity_now'], cur)}**；累计 **{fmt_pct(r['total_return'])}**；"
                     f"最大回撤 **{r['max_drawdown'] * 100:.2f}%**；Sharpe **{r['sharpe']:.2f}**；"
                     f"调仓次数 **{r['trade_count']}**")
        if s["type"] == "ma":
            lines.append(f"- 指标：MA{ r['latest'].get('fast', 5) }="
                         f"{fmt_num(r['latest'].get('ma_fast'), 4)}，MA{ r['latest'].get('slow', 20) }="
                         f"{fmt_num(r['latest'].get('ma_slow'), 4)}")
        elif s["type"] == "rsi":
            lines.append(f"- 指标：RSI(14)={fmt_num(r['latest'].get('rsi'), 2)}"
                         f"（前值 {fmt_num(r['latest'].get('rsi_prev'), 2)}）")
        elif s["type"] == "momentum":
            lines.append(f"- 指标：20 日动量={fmt_pct(r['latest'].get('momentum'))}"
                         f"（前值 {fmt_pct(r['latest'].get('momentum_prev'))}）")
        if r["last_change_idx"] is not None:
            idx = r["last_change_idx"]
            lines.append(f"- 最近调仓：{r['dates'][idx]}，{action_text(r['positions'][idx])}")
        lines.append("")
        lines.append(f"**原因分析**：{reason_text(r)}")
        lines.append("")
        lines.append(f"**改进建议**：{advice_text(r)}")
        lines.append("")

    lines.append("## 三、汇总表")
    lines.append("")
    lines.append("| 策略 | 标的 | 最新日线 | 标的涨跌 | 当前仓位 | 最新日盈亏 | 当前浮动 | 累计收益 | 最大回撤 | Sharpe | 调仓次数 |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in ok_results:
        s = r["strategy"]
        lines.append(
            f"| {s['id']} {s['name']} | {s['symbol']} | {r['bars'][-1]['date']} | "
            f"{fmt_pct(r['underlying_return'])} | {position_text(r['position_now'])} | "
            f"{fmt_money(r['latest_day_pnl'], s['currency'])} | "
            f"{fmt_money(r['float_pnl'], s['currency'])} | {fmt_pct(r['total_return'])} | "
            f"{r['max_drawdown'] * 100:.2f}% | {r['sharpe']:.2f} | {r['trade_count']} |"
        )
    lines.append("")

    lines.append("## 四、数据质量")
    lines.append("")
    lines.append("| 策略 | 标的 | 数据源 | 日线条数 | 最新日线 | 抓取时间 | 状态 |")
    lines.append("|---|---|---|---:|---|---|---|")
    for r in ok_results:
        md = r["market"]
        status = "缓存回退" if md.get("stale") else "实时拉取"
        lines.append(
            f"| {r['strategy']['id']} | {md['symbol']} | {md.get('source', '')} | {len(md.get('bars') or [])} | "
            f"{md['bars'][-1]['date']} | {md.get('fetched_at', '')} | {status} |"
        )
    for err in errors:
        lines.append(f"| - | {err.get('symbol', '')} | - | 0 | - | - | {err.get('error', '失败')} |")
    lines.append("")

    lines.append("## 五、方法与假设")
    lines.append("")
    lines.append("- 数据：Binance 公开行情镜像（crypto 日线，UTC 0 点切日）与新浪/腾讯/东方财富 A 股日线；免费源可能延迟或限流。")
    lines.append("- 信号：双均线按 MA5/MA20 多空；RSI 在“上穿 30”买入、“下穿 70”卖出；动量在 20 日涨幅 >5% 时持有。")
    lines.append("- 成交：信号在收盘确认，按同一收盘价成交；每边收取配置中的手续费；未计滑点、冲击成本、税费。")
    lines.append("- A 股：未模拟 T+1、涨跌停、停牌；crypto：UTC 日线，22:00 复盘时最新完整日线通常为前一日 UTC。")
    lines.append("- 本报告是规则化回测/复盘，不是实盘交易建议；历史表现不代表未来收益。")
    lines.append("")
    lines.append("## 六、风险提示")
    lines.append("")
    lines.append("- 单一策略、单一参数在特定行情下可能失效；请做样本外与多市场验证。")
    lines.append("- 免费数据源可能中断或返回延迟数据；报告会标注“缓存回退”。")
    lines.append("- 如需接入真实模拟盘/实盘，需要额外的账户、风控、成交与合规系统，本脚本不下单。")
    lines.append("")
    return "\n".join(lines)


def append_metrics(results, report_date: str) -> None:
    path = REPORT_DIR / "metrics.csv"
    fields = ["date", "strategy_id", "strategy", "symbol", "position", "latest_day_pnl",
              "latest_day_return", "float_pnl", "total_return", "max_drawdown",
              "sharpe", "trade_count", "close", "current_price", "source", "stale"]
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        if new_file:
            writer.writeheader()
        for r in results:
            if not r.get("ok"):
                continue
            s = r["strategy"]
            writer.writerow({
                "date": report_date,
                "strategy_id": s["id"],
                "strategy": s["name"],
                "symbol": s["symbol"],
                "position": r["position_now"],
                "latest_day_pnl": round(r["latest_day_pnl"], 4),
                "latest_day_return": round(r["latest_day_return"], 8),
                "float_pnl": round(r["float_pnl"], 4),
                "total_return": round(r["total_return"], 8),
                "max_drawdown": round(r["max_drawdown"], 8),
                "sharpe": round(r["sharpe"], 4),
                "trade_count": r["trade_count"],
                "close": r["closes"][-1],
                "current_price": r["current_price"],
                "source": r["market"].get("source", ""),
                "stale": bool(r["market"].get("stale")),
            })


def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"config not found: {CONFIG_PATH}", file=sys.stderr)
        return 2
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    initial = float(config.get("initial_capital", 100000))
    limit = int(config.get("history_days", 300))

    results = []
    errors = []
    for strategy in config.get("strategies", []):
        print(f"[review] {strategy['id']} {strategy['name']} {strategy['symbol']} ...", flush=True)
        md = load_market(strategy, limit)
        if not md.get("bars"):
            err = {"symbol": strategy["symbol"], "error": md.get("error") or "no data"}
            errors.append(err)
            print(f"[review]   FAILED: {err['error']}", flush=True)
            continue
        try:
            result = compute(strategy, md, initial)
            if not result.get("ok"):
                errors.append({"symbol": strategy["symbol"], "error": result.get("error", "compute failed")})
                print(f"[review]   FAILED: {result.get('error')}", flush=True)
                continue
            results.append(result)
            print(f"[review]   OK  bars={len(result['bars'])} last={result['bars'][-1]['date']} "
                  f"pos={result['position_now']} ret={result['total_return']:.4%}", flush=True)
        except Exception as exc:
            errors.append({"symbol": strategy["symbol"], "error": f"{type(exc).__name__}: {exc}"})
            print(f"[review]   FAILED: {type(exc).__name__}: {exc}", flush=True)

    if not results:
        print("[review] no strategy produced a result", file=sys.stderr)
        return 1

    generated_at = datetime.now(BEIJING)
    report_date = max(r["bars"][-1]["date"] for r in results)
    report = render_report(results, errors, generated_at, initial)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"{report_date}.md"
    report_path.write_text(report, encoding="utf-8")
    (REPORT_DIR / "latest.md").write_text(report, encoding="utf-8")
    append_metrics(results, report_date)

    print(f"[review] report: {report_path}")
    print(f"[review] latest: {REPORT_DIR / 'latest.md'}")
    if errors:
        print(f"[review] warnings: {len(errors)} strategy/data issue(s)", file=sys.stderr)
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
