#!/usr/bin/env python3
"""Normalize the US and A-share source pools into the dashboard CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


WEB_DIR = Path(__file__).resolve().parent
ROOT_DIR = WEB_DIR.parent
DEFAULT_OUTPUT_FILE = WEB_DIR / "stock-pool.csv"
DEFAULT_US_SOURCE = ROOT_DIR / "美股股票池.csv"
DEFAULT_A_SHARE_SOURCE = ROOT_DIR / "A股映射股票池.csv"

FIELDS = [
    "ticker",
    "company",
    "market",
    "category",
    "sector",
    "chain_layer",
    "role",
    "key_focus",
    "source",
    "status",
    "evidence_level",
    "market_state",
    "added_date",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def a_share_category(sector: str) -> str:
    if any(keyword in sector for keyword in ("半导体设备", "测试设备", "晶圆制造")):
        return "半导体设备"
    if any(keyword in sector for keyword in ("光模块", "光器件", "光芯片", "硅光", "激光")):
        return "光通信"
    if any(keyword in sector for keyword in ("PCB", "CCL", "封装载板")):
        return "PCB与材料"
    if "存储" in sector:
        return "数据存储"
    if "机器人" in sector:
        return "机器人"
    if any(keyword in sector for keyword in ("军工", "无人机")):
        return "国防军工"
    if any(keyword in sector for keyword in ("核电", "燃机", "电网")):
        return "能源与核电"
    if any(keyword in sector for keyword in ("液冷", "温控", "电源", "电力设备")):
        return "数据中心基础设施"
    if any(keyword in sector for keyword in ("AI网络", "AIDC", "国产AI计算", "AI服务器")):
        return "AI算力与服务器"
    return sector


def normalize_us(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "ticker": row["ticker"].strip().upper(),
            "company": row["company"].strip(),
            "market": "美股",
            "category": row["sector"].strip(),
            "sector": row["sector"].strip(),
            "chain_layer": row["chain_layer"].strip(),
            "role": row["role"].strip(),
            "key_focus": row["key_focus"].strip(),
            "source": row["source"].strip(),
            "status": row["status"].strip(),
            "evidence_level": "",
            "market_state": "",
            "added_date": row["added_date"].strip(),
        }
        for row in rows
    ]


def normalize_a_shares(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "ticker": row["ticker"].strip().upper(),
            "company": row["company"].strip(),
            "market": "A股",
            "category": a_share_category(row["sector"].strip()),
            "sector": row["sector"].strip(),
            "chain_layer": row["chain_layer"].strip(),
            "role": row["role"].strip(),
            "key_focus": row["key_focus"].strip(),
            "source": row["source_us"].strip(),
            "status": row["pool_status"].strip(),
            "evidence_level": row["evidence_level"].strip(),
            "market_state": row["market_state_2026-06-17"].strip(),
            "added_date": row["added_date"].strip(),
        }
        for row in rows
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge US and A-share source tables into the deploy snapshot.")
    parser.add_argument("--us-source", type=Path, default=DEFAULT_US_SOURCE, help="US stock-pool source CSV")
    parser.add_argument("--a-share-source", type=Path, default=DEFAULT_A_SHARE_SOURCE, help="A-share mapping source CSV")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_FILE, help="Merged output CSV")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = normalize_us(read_csv(args.us_source.expanduser().resolve()))
    rows.extend(normalize_a_shares(read_csv(args.a_share_source.expanduser().resolve())))

    tickers = [row["ticker"] for row in rows]
    duplicates = sorted({ticker for ticker in tickers if tickers.count(ticker) > 1})
    if duplicates:
        raise ValueError(f"Duplicate tickers: {', '.join(duplicates)}")

    output_file = args.output.expanduser().resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    us_count = sum(row["market"] == "美股" for row in rows)
    a_count = sum(row["market"] == "A股" for row in rows)
    print(f"Wrote {output_file}: {len(rows)} symbols (美股 {us_count}, A股 {a_count})")


if __name__ == "__main__":
    main()
