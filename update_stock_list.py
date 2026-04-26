"""
JPX公式の東証上場銘柄一覧を取得して scan_stocks.json を生成する。

- ソース: https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls
- 対象: プライム/スタンダード/グロース市場の内国株式（ETF/REIT/ベンチャーファンド/PRO Marketは除外）
- 出力: scan_stocks.json

GitHub Actions の月次ワークフローで実行される想定。
ローカルで動かしたい場合: pip install pandas xlrd
"""

import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

JPX_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"

# 含める市場区分（内国株式のみ）
INCLUDE_MARKETS = {
    "プライム（内国株式）",
    "スタンダード（内国株式）",
    "グロース（内国株式）",
}

# 念のため除外する区分（重複防止）
EXCLUDE_KEYWORDS = ["外国株式", "ETF", "ETN", "REIT", "出資証券",
                    "PRO Market", "ベンチャーファンド", "インフラファンド",
                    "受益証券発行信託"]


def download_xls(url: str) -> bytes:
    print(f"Downloading: {url}")
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=60) as resp:
        data = resp.read()
    print(f"  {len(data):,} bytes")
    return data


def parse_xls(xls_bytes: bytes) -> list[dict]:
    """XLSをパースして銘柄リストを返す。"""
    from io import BytesIO
    df = pd.read_excel(BytesIO(xls_bytes), engine="xlrd")
    print(f"  Total rows: {len(df)}")
    print(f"  Columns: {list(df.columns)}")

    # 期待カラム: 日付, コード, 銘柄名, 市場・商品区分, 33業種コード, ...
    code_col = None
    name_col = None
    market_col = None
    for c in df.columns:
        if "コード" in str(c):
            code_col = c
        elif "銘柄名" in str(c):
            name_col = c
        elif "市場" in str(c) and "区分" in str(c):
            market_col = c

    if not (code_col and name_col and market_col):
        raise RuntimeError(
            f"カラムが見つかりません: code={code_col}, name={name_col}, market={market_col}"
        )

    stocks = []
    for _, row in df.iterrows():
        market = str(row[market_col]).strip()
        if market not in INCLUDE_MARKETS:
            continue
        if any(kw in market for kw in EXCLUDE_KEYWORDS):
            continue

        code = str(row[code_col]).strip()
        # JPX銘柄コードは数字4桁。5桁(優先株等)も含むことがあるが、
        # Yahoo Financeは4桁ベースなのでスキップ
        if not code.isdigit() or len(code) != 4:
            continue

        name = str(row[name_col]).strip()
        stocks.append({"code": code, "name": name})

    # 重複除去 (同じcodeが複数回登場することは通常ないが念のため)
    seen = set()
    unique = []
    for s in stocks:
        if s["code"] in seen:
            continue
        seen.add(s["code"])
        unique.append(s)

    unique.sort(key=lambda x: x["code"])
    return unique


def main():
    out_path = Path(__file__).parent / "scan_stocks.json"

    xls_bytes = download_xls(JPX_URL)
    stocks = parse_xls(xls_bytes)

    print(f"\n抽出銘柄数: {len(stocks)}")

    # 市場区分別の内訳をログに
    print(f"  最小コード: {stocks[0]['code']} {stocks[0]['name']}")
    print(f"  最大コード: {stocks[-1]['code']} {stocks[-1]['name']}")

    out_data = {
        "description": "東証上場銘柄一覧（プライム/スタンダード/グロース・内国株式）",
        "source": JPX_URL,
        "lastUpdated": pd.Timestamp.now(tz="Asia/Tokyo").isoformat(),
        "count": len(stocks),
        "stocks": stocks,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)

    print(f"\n保存: {out_path} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
