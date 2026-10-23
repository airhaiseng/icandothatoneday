#!/usr/bin/env python3
"""Build a self-contained dashboard.html from the latest cached review data.

Run after review.py (run_review.ps1 does this automatically).
No external CDN, fonts, or JS packages are used, so the page works from file://.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import review  # noqa: E402

TEMPLATE = BASE / "dashboard_template.html"
OUTPUT = BASE / "dashboard.html"
STATE = BASE / "state" / "auto_review.json"
OFFLINE = "--offline" in sys.argv
BEIJING = timezone(timedelta(hours=8))

# Curated universe. Add rows here to expose more symbols in the picker.
UNIVERSE = [
    ("sh600519", "贵州茅台", "ashare", "CNY"),
    ("sz000001", "平安银行", "ashare", "CNY"),
    ("sz300750", "宁德时代", "ashare", "CNY"),
    ("sh601318", "中国平安", "ashare", "CNY"),
    ("sz000858", "五粮液", "ashare", "CNY"),
    ("sh600036", "招商银行", "ashare", "CNY"),
    ("sz002594", "比亚迪", "ashare", "CNY"),
    ("sh688981", "中芯国际", "ashare", "CNY"),
    ("sh600900", "长江电力", "ashare", "CNY"),
    ("sh601899", "紫金矿业", "ashare", "CNY"),
    ("AAPL", "苹果", "us", "USD"),
    ("MSFT", "微软", "us", "USD"),
    ("NVDA", "英伟达", "us", "USD"),
    ("TSLA", "特斯拉", "us", "USD"),
    ("BABA", "阿里巴巴", "us", "USD"),
    ("JPM", "摩根大通", "us", "USD"),
    ("BTCUSDT", "比特币", "crypto", "USDT"),
    ("ETHUSDT", "以太坊", "crypto", "USDT"),
    ("SOLUSDT", "Solana", "crypto", "USDT"),
    ("BNBUSDT", "BNB", "crypto", "USDT"),
]


def load_cache(symbol: str) -> dict:
    path = review.cache_path(symbol)
    if not path.exists():
        return {
            "symbol": symbol,
            "bars": [],
            "source": "未找到缓存",
            "current_price": None,
            "fetched_at": "",
            "stale": True,
            "error": f"missing {path}",
        }
    obj = json.loads(path.read_text(encoding="utf-8"))
    obj["stale"] = False
    obj["error"] = ""
    try:
        fetched = datetime.fromisoformat(obj.get("fetched_at", ""))
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - fetched > timedelta(hours=36):
            obj["stale"] = True
            obj["error"] = "缓存超过 36 小时"
    except Exception:
        obj["stale"] = True
        obj["error"] = "缓存时间不可读"
    return obj


def build_universe_item(symbol: str, name: str, market: str, currency: str) -> dict | None:
    # Online build refreshes the universe; --offline only repaints from caches
    # (used by pause/resume so the status badge updates without a network call).
    if OFFLINE:
        md = load_cache(symbol)
    else:
        md = review.load_market({"symbol": symbol, "market": market}, 320, save=False)
        time.sleep(0.15)
    if len(md.get("bars") or []) < 60:
        md = load_cache(symbol)
    bars = (md.get("bars") or [])[-320:]
    if len(bars) < 60:
        print(f"[dashboard] skip {symbol}: only {len(bars)} bars", file=sys.stderr)
        return None

    dates = [b["date"] for b in bars]
    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    volumes = [b["volume"] for b in bars]

    ma5 = review.sma(closes, 5)
    ma20 = review.sma(closes, 20)
    ma60 = review.sma(closes, 60)
    rsi = review.rsi_wilder(closes, 14)

    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]]
    ann = 365 if market == "crypto" else 252
    vol20 = statistics.pstdev(rets[-20:]) * (ann ** 0.5) if len(rets) >= 2 else 0.0
    last = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else last
    stats = {
        "last": last,
        "dayChange": last / prev - 1 if prev else 0.0,
        "ret20": last / closes[-21] - 1 if len(closes) >= 21 else None,
        "ret60": last / closes[-61] - 1 if len(closes) >= 61 else None,
        "vol20": vol20,
        "high52": max(closes[-252:]),
        "low52": min(closes[-252:]),
        "avgVol20": statistics.fmean(volumes[-20:]) if volumes else 0.0,
        "rsi": rsi[-1],
        "ma5": ma5[-1],
        "ma20": ma20[-1],
        "ma60": ma60[-1],
    }

    def r4(v):
        return None if v is None else round(v, 4)

    return {
        "symbol": symbol,
        "name": name,
        "market": market,
        "currency": currency,
        "dates": dates,
        "open": [r4(v) for v in opens],
        "high": [r4(v) for v in highs],
        "low": [r4(v) for v in lows],
        "close": [r4(v) for v in closes],
        "volume": [round(v or 0, 0) for v in volumes],
        "ma5": [r4(v) for v in ma5],
        "ma20": [r4(v) for v in ma20],
        "ma60": [r4(v) for v in ma60],
        "rsi": [r4(v) for v in rsi],
        "stats": stats,
        "data": {
            "source": md.get("source", ""),
            "bars": len(bars),
            "lastDate": dates[-1],
            "fetchedAt": md.get("fetched_at", ""),
            "stale": bool(md.get("stale")),
            "error": md.get("error", ""),
        },
    }


def main() -> int:
    config = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    initial = float(config.get("initial_capital", 100000))
    start_date = config.get("start_date") or None

    strategies = []
    warnings = []
    for s in config.get("strategies", []):
        md = load_cache(s["symbol"])
        if not md.get("bars"):
            warnings.append(f"{s['id']} {s['symbol']} 无行情缓存")
            continue
        result = review.compute(s, md, initial, start_date)
        if not result.get("ok"):
            warnings.append(f"{s['id']} {s['symbol']} 计算失败: {result.get('error')}")
            continue

        last_change = None
        if result.get("last_change_idx") is not None:
            idx = result["last_change_idx"]
            last_change = {
                "date": result["dates"][idx],
                "action": "买入/继续持有" if result["positions"][idx] else "卖出/保持空仓",
                "position": result["positions"][idx],
            }

        strategies.append({
            "id": s["id"],
            "name": s["name"],
            "symbol": s["symbol"],
            "market": s.get("market", ""),
            "type": s.get("type", ""),
            "currency": s.get("currency", ""),
            "feeRate": float(s.get("fee_rate", 0)),
            "params": s.get("params", {}),
            "position": result["position_now"],
            "positionText": "多头" if result["position_now"] else "空仓",
            "latestDayPnl": round(result["latest_day_pnl"], 2),
            "latestDayReturn": result["latest_day_return"],
            "floatPnl": round(result["float_pnl"], 2),
            "equityNow": round(result["equity_now"], 2),
            "totalReturn": result["total_return"],
            "maxDrawdown": result["max_drawdown"],
            "sharpe": result["sharpe"],
            "tradeCount": result["trade_count"],
            "close": result["closes"][-1],
            "currentPrice": result["current_price"],
            "underlyingReturn": result["underlying_return"],
            "contribution": result["contribution"],
            "trend20": result["trend20"],
            "vol20": result["vol20"],
            "changedToday": result["changed_today"],
            "lastChange": last_change,
            "indicators": {
                "maFast": result["latest"].get("ma_fast"),
                "maSlow": result["latest"].get("ma_slow"),
                "rsi": result["latest"].get("rsi"),
                "rsiPrev": result["latest"].get("rsi_prev"),
                "momentum": result["latest"].get("momentum"),
                "momentumPrev": result["latest"].get("momentum_prev"),
            },
            "series": {
                "dates": result["dates"],
                "equity": [round(v, 2) for v in result["equity"]],
                "close": [round(v, 6) for v in result["closes"]],
                "position": result["positions"],
            },
            "data": {
                "source": md.get("source", ""),
                "bars": len(md.get("bars") or []),
                "lastDate": md["bars"][-1]["date"],
                "fetchedAt": md.get("fetched_at", ""),
                "stale": bool(md.get("stale")),
                "error": md.get("error", ""),
            },
        })

    universe = []
    for symbol, name, market, currency in UNIVERSE:
        print(f"[dashboard] universe {symbol} {name} ...", flush=True)
        item = build_universe_item(symbol, name, market, currency)
        if item:
            universe.append(item)
        else:
            warnings.append(f"{symbol} 无可用行情，已跳过")

    auto_paused = False
    auto_updated = ""
    if STATE.exists():
        try:
            state_obj = json.loads(STATE.read_text(encoding="utf-8-sig"))
            auto_paused = bool(state_obj.get("paused"))
            auto_updated = str(state_obj.get("updatedAt", ""))
        except Exception:
            pass

    report_date = max(
        [x["data"]["lastDate"] for x in strategies] +
        [x["data"]["lastDate"] for x in universe],
        default="",
    )
    default_symbol = "sh600519" if any(x["symbol"] == "sh600519" for x in universe) else (universe[0]["symbol"] if universe else "")
    payload = {
        "generatedAt": datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S"),
        "reportDate": report_date,
        "initialCapital": initial,
        "strategies": strategies,
        "universe": universe,
        "defaultSymbol": default_symbol,
        "autoPaused": auto_paused,
        "autoPauseUpdatedAt": auto_updated,
        "warnings": warnings,
        "config": {
            "historyDays": config.get("history_days", 300),
            "startDate": config.get("start_date", ""),
            "strategies": config.get("strategies", []),
        },
    }

    if not TEMPLATE.exists():
        print(f"template not found: {TEMPLATE}", file=sys.stderr)
        return 2
    template = TEMPLATE.read_text(encoding="utf-8")
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</script", "<\\/script")
    html = template.replace("__DASHBOARD_DATA__", blob)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"[dashboard] {OUTPUT}")
    print(f"[dashboard] strategies={len(strategies)} universe={len(universe)} date={report_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
