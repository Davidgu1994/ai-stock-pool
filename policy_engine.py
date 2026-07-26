"""Build the live Trump Policy Pressure Index payload.

Fast-moving market inputs refresh from Yahoo Finance. Slower political and
inflation inputs retain their native publication cadence and expose freshness
metadata so the UI never presents them as intraday data.
"""

from __future__ import annotations

import html
import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from urllib.parse import quote

from curl_cffi import requests as curl_requests


BASE_DIR = Path(__file__).resolve().parent
FALLBACK_FILE = BASE_DIR / "tpi-latest.json"
POLICY_CACHE_SECONDS = 300

MARKET_SOURCES = {
    "ust10y": ("^TNX", "10年期美债", 0.15),
    "move": ("^MOVE", "债券波动率", 0.15),
    "spx": ("^GSPC", "标普500", 0.20),
    "vix": ("^VIX", "股市恐慌", 0.15),
}

SOURCE_URLS = {
    "approval": "https://pollfinity.com/averages",
    "inflation": "https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting",
    "ust10y": "https://finance.yahoo.com/quote/%5ETNX/",
    "move": "https://finance.yahoo.com/quote/%5EMOVE/",
    "spx": "https://finance.yahoo.com/quote/%5EGSPC/",
    "vix": "https://finance.yahoo.com/quote/%5EVIX/",
}

INDUSTRY_MAPPING = [
    {
        "sector": "本土制造与关税链",
        "stance": "观察",
        "signal": "等待政策确认",
        "text": "指数高位会增加延期与豁免的可能性，但只有正式政策文本才能确认。先看订单、补贴与本土产能兑现。",
        "poolCategories": ["半导体设备", "半导体与设备", "半导体材料", "电子特气"],
    },
    {
        "sector": "长久期成长",
        "stance": "等回踩",
        "signal": "利率与波动率约束",
        "text": "政策压力上升常伴随利率和波动率抬升，估值可能先于基本面承压。等待风险溢价与利率回落。",
        "poolCategories": ["云与软件", "互联网平台", "加密与区块链"],
    },
    {
        "sector": "国防与能源",
        "stance": "观察",
        "signal": "事件脉冲与降级并存",
        "text": "地缘事件带来交易脉冲，高压力又可能推动谈判与降级。优先区分真实订单和纯主题交易。",
        "poolCategories": ["太空与国防", "国防军工", "能源", "能源与核电", "核能"],
    },
    {
        "sector": "AI基础设施",
        "stance": "能下手",
        "signal": "基本面优先",
        "text": "政策噪音中，优先选择需求、资本开支和订单证据更强的基础设施环节，并结合行情位置分批处理。",
        "poolCategories": ["数据中心基础设施", "AI算力与服务器", "数据存储", "光子学与光通信", "光通信"],
    },
]

_cache_lock = threading.Lock()
_cache: dict[str, object] = {"timestamp": 0.0, "payload": None}


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return min(upper, max(lower, value))


def finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def percentile_rank(values: list[float], current: float) -> float:
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        return 50.0
    below = sum(value < current for value in clean)
    equal = sum(value == current for value in clean)
    return clamp((below + equal * 0.5) / len(clean) * 100)


def iso_from_timestamp(timestamp: int | float | None) -> str | None:
    if not timestamp:
        return None
    return datetime.fromtimestamp(float(timestamp), timezone.utc).isoformat()


def freshness(updated_at: str | None, fast: bool = False) -> tuple[str, str]:
    if not updated_at:
        return "unknown", "更新时间未知"
    try:
        updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (datetime.now(timezone.utc) - updated).total_seconds() / 3600)
    except ValueError:
        return "unknown", updated_at
    if fast:
        if age_hours <= 24:
            return "live", "最新交易时点"
        if age_hours <= 96:
            return "delayed", "最近交易日"
        return "stale", "数据偏旧"
    if age_hours <= 24 * 7:
        return "current", "跟随源站更新"
    if age_hours <= 24 * 35:
        return "delayed", "低频数据"
    return "stale", "数据偏旧"


def fetch_market_series(driver_id: str, symbol: str) -> dict[str, object]:
    response = curl_requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}",
        params={"range": "1y", "interval": "1d", "includePrePost": "false", "events": "div,splits"},
        impersonate="chrome",
        timeout=14,
    )
    response.raise_for_status()
    chart = response.json().get("chart", {})
    result_rows = chart.get("result") or []
    if chart.get("error") or not result_rows:
        raise ValueError(str(chart.get("error") or f"{symbol} empty response"))
    result = result_rows[0]
    meta = result.get("meta", {})
    timestamps = result.get("timestamp") or []
    quote_rows = result.get("indicators", {}).get("quote") or []
    closes = quote_rows[0].get("close") if quote_rows else []
    points = [
        (int(timestamp), float(close))
        for timestamp, close in zip(timestamps, closes)
        if finite_number(close) is not None
    ]
    if len(points) < 25:
        raise ValueError(f"{symbol} insufficient history")
    regular_price = finite_number(meta.get("regularMarketPrice"))
    current = regular_price if regular_price is not None else points[-1][1]
    prior_index = max(0, len(points) - 6)
    prior = points[prior_index][1]
    updated_at = iso_from_timestamp(meta.get("regularMarketTime") or points[-1][0])
    return {
        "id": driver_id,
        "symbol": symbol,
        "current": current,
        "prior5d": prior,
        "updatedAt": updated_at,
        "points": points,
        "closes": [point[1] for point in points],
    }


def fetch_approval() -> dict[str, object]:
    response = curl_requests.get("https://pollfinity.com/averages.json", impersonate="chrome", timeout=14)
    response.raise_for_status()
    track = response.json().get("tracks", {}).get("trump_approval", {})
    polls = track.get("polls_used") or []
    valid_polls = []
    for poll in polls:
        approve = finite_number(poll.get("approve"))
        disapprove = finite_number(poll.get("disapprove"))
        weight = finite_number(poll.get("weight"))
        if approve is None or disapprove is None or weight is None or weight <= 0:
            continue
        if not (25 <= approve <= 75 and 25 <= disapprove <= 75 and approve + disapprove >= 80):
            continue
        valid_polls.append((approve, disapprove, weight))
    if not valid_polls:
        current = track.get("current") or {}
        approve = finite_number(current.get("approve"))
        disapprove = finite_number(current.get("disapprove"))
        if approve is None or disapprove is None:
            raise ValueError("approval average unavailable")
        valid_polls = [(approve, disapprove, 1.0)]
    total_weight = sum(item[2] for item in valid_polls)
    approve = sum(item[0] * item[2] for item in valid_polls) / total_weight
    disapprove = sum(item[1] * item[2] for item in valid_polls) / total_weight
    net = approve - disapprove
    history = []
    for item in track.get("history") or []:
        hist_approve = finite_number(item.get("approve"))
        hist_disapprove = finite_number(item.get("disapprove"))
        if hist_approve is None or hist_disapprove is None:
            continue
        if 25 <= hist_approve <= 75 and 25 <= hist_disapprove <= 75 and hist_approve + hist_disapprove >= 80:
            history.append({"date": item.get("date"), "net": hist_approve - hist_disapprove})
    updated = track.get("last_updated")
    updated_at = f"{updated}T12:00:00+00:00" if updated else None
    return {
        "approve": approve,
        "disapprove": disapprove,
        "net": net,
        "updatedAt": updated_at,
        "pollCount": len(valid_polls),
        "history": history,
    }


def strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def fetch_inflation_nowcast() -> dict[str, object]:
    response = curl_requests.get(SOURCE_URLS["inflation"], impersonate="chrome", timeout=18)
    response.raise_for_status()
    match = re.search(
        r"<caption>\s*Inflation,\s*year-over-year percent change\s*</caption>.*?<tbody>\s*<tr>(.*?)</tr>",
        response.text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise ValueError("inflation nowcast table unavailable")
    cells = [strip_tags(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", match.group(1), flags=re.DOTALL)]
    if len(cells) < 6:
        raise ValueError("inflation nowcast row incomplete")
    cpi_yoy = finite_number(cells[1])
    if cpi_yoy is None:
        raise ValueError("CPI nowcast unavailable")
    month_match = re.search(r"(\d{4})", cells[0])
    year = int(month_match.group(1)) if month_match else datetime.now(timezone.utc).year
    updated_at = None
    date_match = re.match(r"(\d{1,2})/(\d{1,2})", cells[5])
    if date_match:
        updated_at = datetime(year, int(date_match.group(1)), int(date_match.group(2)), 12, tzinfo=timezone.utc).isoformat()
    return {
        "period": cells[0],
        "cpiYoY": cpi_yoy,
        "coreCpiYoY": finite_number(cells[2]),
        "updatedAt": updated_at,
    }


def market_driver_payload(driver_id: str, raw: dict[str, object]) -> dict[str, object]:
    current = float(raw["current"])
    prior = float(raw["prior5d"])
    closes = list(raw["closes"])
    updated_at = raw.get("updatedAt")
    freshness_code, freshness_label = freshness(str(updated_at) if updated_at else None, fast=True)
    weight = MARKET_SOURCES[driver_id][2]

    if driver_id == "spx":
        change = (current / prior - 1) * 100 if prior else 0.0
        historical_returns = [-(closes[index] / closes[index - 5] - 1) * 100 for index in range(5, len(closes))]
        score = percentile_rank(historical_returns, -change)
        value = f"{current:,.1f}"
        change_label = f"近5日 {change:+.2f}%"
        pressure_direction = "下跌增加压力"
        interpretation = "股市回撤会强化政策反馈；上涨则释放压力。"
    elif driver_id == "ust10y":
        change = current - prior
        score = 0.75 * percentile_rank(closes, current) + 0.25 * clamp(50 + change * 180)
        value = f"{current:.3f}%"
        change_label = f"近5日 {change * 100:+.0f}bp"
        pressure_direction = "收益率上升增加压力"
        interpretation = "融资成本越高，财政与市场承受力越弱。"
    else:
        change = current - prior
        multiplier = 3.0 if driver_id == "vix" else 1.0
        score = 0.78 * percentile_rank(closes, current) + 0.22 * clamp(50 + change * multiplier)
        value = f"{current:.2f}"
        change_label = f"近5日 {change:+.2f}"
        pressure_direction = "指数上升增加压力"
        interpretation = "波动率抬升意味着政策冲击更难被市场消化。"

    return {
        "id": driver_id,
        "name": MARKET_SOURCES[driver_id][1],
        "weight": weight,
        "pressureScore": round(clamp(score), 1),
        "value": value,
        "changeLabel": change_label,
        "direction": pressure_direction,
        "interpretation": interpretation,
        "updatedAt": updated_at,
        "freshness": freshness_code,
        "freshnessLabel": freshness_label,
        "sourceName": "Yahoo Finance 市场数据",
        "sourceTier": "market",
        "sourceUrl": SOURCE_URLS[driver_id],
    }


def approval_driver_payload(raw: dict[str, object]) -> dict[str, object]:
    net = float(raw["net"])
    history = raw.get("history") or []
    prior_net = None
    if history:
        prior_net = finite_number(history[max(0, len(history) - 11)].get("net"))
    change = net - prior_net if prior_net is not None else None
    score = clamp(50 + (-net - 5) * 1.8)
    updated_at = raw.get("updatedAt")
    freshness_code, freshness_label = freshness(str(updated_at) if updated_at else None)
    return {
        "id": "approval",
        "name": "净支持率",
        "weight": 0.25,
        "pressureScore": round(score, 1),
        "value": f"{net:+.1f}pt",
        "changeLabel": f"较约30日前 {change:+.1f}pt" if change is not None else f"{raw.get('pollCount', 0)}项有效民调",
        "direction": "净支持率下降增加压力",
        "interpretation": "民调越弱，强硬政策的政治承受空间越小。",
        "updatedAt": updated_at,
        "freshness": freshness_code,
        "freshnessLabel": freshness_label,
        "sourceName": f"Pollfinity 聚合 · {raw.get('pollCount', 0)}项有效民调",
        "sourceTier": "aggregator",
        "sourceUrl": SOURCE_URLS["approval"],
    }


def inflation_driver_payload(raw: dict[str, object]) -> dict[str, object]:
    cpi_yoy = float(raw["cpiYoY"])
    score = clamp(50 + (cpi_yoy - 2.0) * 20)
    updated_at = raw.get("updatedAt")
    freshness_code, freshness_label = freshness(str(updated_at) if updated_at else None)
    return {
        "id": "inflation",
        "name": "CPI Nowcast",
        "weight": 0.10,
        "pressureScore": round(score, 1),
        "value": f"{cpi_yoy:.2f}%",
        "changeLabel": f"{raw.get('period', '')} 同比预测",
        "direction": "通胀预期上升增加压力",
        "interpretation": "输入性通胀越高，关税和财政政策的民意成本越大。",
        "updatedAt": updated_at,
        "freshness": freshness_code,
        "freshnessLabel": freshness_label,
        "sourceName": "克利夫兰联储 Inflation Nowcasting",
        "sourceTier": "official",
        "sourceUrl": SOURCE_URLS["inflation"],
    }


def load_fallback() -> dict[str, object]:
    with FALLBACK_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fallback_driver(driver_id: str, fallback: dict[str, object], reason: str) -> dict[str, object]:
    for item in fallback.get("drivers", []):
        if item.get("id") != driver_id:
            continue
        return {
            "id": driver_id,
            "name": item.get("nameZh") or item.get("name") or driver_id,
            "weight": float(item.get("weight") or 0),
            "pressureScore": float(item.get("pressureScore") or 50),
            "value": item.get("value") or "—",
            "changeLabel": item.get("changeLabel") or "使用上次快照",
            "direction": item.get("direction") or "等待恢复",
            "interpretation": "实时源暂不可用，当前显示上次有效快照。",
            "updatedAt": fallback.get("asOf"),
            "freshness": "fallback",
            "freshnessLabel": "降级快照",
            "sourceName": f"本地回退 · {reason}",
            "sourceTier": "fallback",
            "sourceUrl": SOURCE_URLS.get(driver_id, ""),
        }
    raise ValueError(f"missing fallback driver {driver_id}")


def build_history(
    market_raw: dict[str, dict[str, object]],
    approval_score: float,
    inflation_score: float,
) -> list[dict[str, object]]:
    if not all(driver_id in market_raw for driver_id in MARKET_SOURCES):
        return []
    spx_points = list(market_raw["spx"]["points"])
    sampled = spx_points[-41::5]
    market_maps = {
        driver_id: {
            datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat(): value
            for timestamp, value in raw["points"]
        }
        for driver_id, raw in market_raw.items()
    }
    histories = {driver_id: list(raw["closes"]) for driver_id, raw in market_raw.items()}
    output = []
    for timestamp, spx_value in sampled[-8:]:
        date_key = datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
        scores: dict[str, float] = {}
        for driver_id in ("ust10y", "move", "vix"):
            value = market_maps[driver_id].get(date_key)
            if value is None:
                scores[driver_id] = 50.0
            else:
                scores[driver_id] = percentile_rank(histories[driver_id], value)
        spx_index = next((index for index, point in enumerate(spx_points) if point[0] == timestamp), None)
        if spx_index is None or spx_index < 5:
            scores["spx"] = 50.0
        else:
            prior = spx_points[spx_index - 5][1]
            return_5d = (spx_value / prior - 1) * 100
            all_returns = [-(spx_points[index][1] / spx_points[index - 5][1] - 1) * 100 for index in range(5, len(spx_points))]
            scores["spx"] = percentile_rank(all_returns, -return_5d)
        total = (
            approval_score * 0.25
            + scores["ust10y"] * 0.15
            + scores["move"] * 0.15
            + scores["spx"] * 0.20
            + scores["vix"] * 0.15
            + inflation_score * 0.10
        )
        output.append({"date": date_key, "label": date_key[5:].replace("-", "."), "value": round(total, 1)})
    return output


def build_policy_payload() -> dict[str, object]:
    fallback = load_fallback()
    tasks = {
        "approval": fetch_approval,
        "inflation": fetch_inflation_nowcast,
        **{
            driver_id: (lambda identifier=driver_id, ticker=symbol: fetch_market_series(identifier, ticker))
            for driver_id, (symbol, _, _) in MARKET_SOURCES.items()
        },
    }
    results: dict[str, dict[str, object]] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_ids = {executor.submit(task): driver_id for driver_id, task in tasks.items()}
        for future in as_completed(future_ids):
            driver_id = future_ids[future]
            try:
                results[driver_id] = future.result()
            except Exception as error:
                errors[driver_id] = str(error)

    drivers = []
    if "approval" in results:
        drivers.append(approval_driver_payload(results["approval"]))
    else:
        drivers.append(fallback_driver("approval", fallback, errors.get("approval", "source unavailable")))
    for driver_id in ("ust10y", "move", "spx", "vix"):
        if driver_id in results:
            drivers.append(market_driver_payload(driver_id, results[driver_id]))
        else:
            drivers.append(fallback_driver(driver_id, fallback, errors.get(driver_id, "source unavailable")))
    if "inflation" in results:
        drivers.append(inflation_driver_payload(results["inflation"]))
    else:
        drivers.append(fallback_driver("inflation", fallback, errors.get("inflation", "source unavailable")))

    weighted_total = sum(float(item["pressureScore"]) * float(item["weight"]) for item in drivers)
    total_weight = sum(float(item["weight"]) for item in drivers) or 1.0
    index_value = round(weighted_total / total_weight, 1)
    zone = (
        "low_pressure"
        if index_value < 40
        else "neutral"
        if index_value < 60
        else "high_pressure"
        if index_value < 75
        else "extreme_pressure"
    )
    fallback_history = fallback.get("history") or []
    history = build_history(
        {key: value for key, value in results.items() if key in MARKET_SOURCES},
        float(drivers[0]["pressureScore"]),
        float(drivers[-1]["pressureScore"]),
    ) or fallback_history
    prior = finite_number(history[-2].get("value")) if len(history) > 1 else None
    change_5d = round(index_value - prior, 1) if prior is not None else 0.0
    source_health = [
        {
            "id": item["id"],
            "name": item["name"],
            "freshness": item["freshness"],
            "freshnessLabel": item["freshnessLabel"],
            "updatedAt": item["updatedAt"],
            "sourceName": item["sourceName"],
            "sourceUrl": item["sourceUrl"],
        }
        for item in drivers
    ]
    fallback_count = sum(item["freshness"] == "fallback" for item in drivers)
    return {
        "asOf": datetime.now(timezone.utc).isoformat(),
        "version": "0.2-live",
        "status": "live" if fallback_count == 0 else "partial",
        "cacheSeconds": POLICY_CACHE_SECONDS,
        "summary": (
            "压力处于高位，重点观察政策是否出现延期、豁免或谈判措辞软化。"
            if index_value >= 60
            else "压力尚未进入高位，政策转向仍缺少足够的市场与政治约束。"
        ),
        "index": {"value": index_value, "zone": zone, "change5d": change_5d},
        "drivers": drivers,
        "history": history,
        "industryMapping": INDUSTRY_MAPPING,
        "sourceHealth": source_health,
        "errors": errors,
        "method": {
            "weights": "民调25% / 标普20% / 美债15% / MOVE15% / VIX15% / CPI Nowcast10%",
            "marketRefresh": "5分钟缓存，跟随最近交易时点",
            "slowRefresh": "民调和通胀跟随源站发布频率",
        },
        "disclaimer": "政策压力情景监测，不预测个体决策，不构成投资建议。",
    }


def get_policy_payload(force: bool = False) -> dict[str, object]:
    now = time.time()
    with _cache_lock:
        cached = _cache.get("payload")
        cached_at = float(_cache.get("timestamp") or 0)
        if not force and cached and now - cached_at < POLICY_CACHE_SECONDS:
            return cached  # type: ignore[return-value]
    payload = build_policy_payload()
    with _cache_lock:
        _cache["payload"] = payload
        _cache["timestamp"] = now
    return payload


if __name__ == "__main__":
    print(json.dumps(get_policy_payload(force=True), ensure_ascii=False, indent=2))
