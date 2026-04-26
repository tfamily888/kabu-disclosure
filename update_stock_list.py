"""
JPX公式の東証上場銘柄一覧を取得して scan_stocks.json を生成する。

- ソース: https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls
- 対象: プライム/スタンダード/グロース市場の内国株式（ETF/REIT/ベンチャーファンド/PRO Marketは除外）
- 出力: scan_stocks.json

GitHub Actions の月次ワークフローで実行される想定。
ローカルで動かしたい場合: pip install xlrd
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

import xlrd

JPX_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"

# 含める市場区分（内国株式のみ）
INCLUDE_MARKETS = {
    "プライム（内国株式）",
    "スタンダード（内国株式）",
    "グロース（内国株式）",
}


def download_xls(url):
    print(f"Downloading: {url}", flush=True)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=60) as resp:
        data = resp.read()
    print(f"  {len(data):,} bytes", flush=True)
    return data


def find_column_indices(header_row):
    code_idx = name_idx = market_idx = None
    for i, cell in enumerate(header_row):
        s = str(cell).strip()
        if s == "コード":
            code_idx = i
        elif s == "銘柄名":
            name_idx = i
        elif "市場・商品区分" in s:
            market_idx = i
    return code_idx, name_idx, market_idx


def parse_xls(xls_bytes):
    book = xlrd.open_workbook(file_contents=xls_bytes)
    sheet = book.sheet_by_index(0)
    print(f"  Sheet: {sheet.name}, rows={sheet.nrows}, cols={sheet.ncols}", flush=True)

    header = [sheet.cell_value(0, c) for c in range(sheet.ncols)]
    print(f"  Header: {header}", flush=True)

    code_idx, name_idx, market_idx = find_column_indices(header)
    if code_idx is None or name_idx is None or market_idx is None:
        raise RuntimeError(
            f"カラムが見つかりません: code={code_idx}, name={name_idx}, market={market_idx}"
        )
    print(
        f"  Columns: code={code_idx}, name={name_idx}, market={market_idx}",
        flush=True,
    )

    market_counts = {}
    stocks = []
    for row_idx in range(1, sheet.nrows):
        market_raw = sheet.cell_value(row_idx, market_idx)
        market = str(market_raw).strip()
        market_counts[market] = market_counts.get(market, 0) + 1

        if market not in INCLUDE_MARKETS:
            continue

        code_cell = sheet.cell_value(row_idx, code_idx)
        # コードはfloat (例: 1301.0) か str
        if isinstance(code_cell, float):
            code = str(int(code_cell))
        else:
            code = str(code_cell).strip()

        if not code.isdigit() or len(code) != 4:
            continue

        name = str(sheet.cell_value(row_idx, name_idx)).strip()
        stocks.append({"code": code, "name": name})

    # 市場区分の分布をログ
    print("\n  市場区分別件数:", flush=True)
    for k, v in sorted(market_counts.items(), key=lambda x: -x[1]):
        marker = " ← 取得対象" if k in INCLUDE_MARKETS else ""
        print(f"    {k}: {v}{marker}", flush=True)

    # 重複除去 + ソート
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

    print(f"\n抽出銘柄数: {len(stocks)}", flush=True)
    if not stocks:
        print("ERROR: 抽出ゼロ件。書き込みをスキップ", flush=True)
        sys.exit(1)

    print(f"  最小コード: {stocks[0]['code']} {stocks[0]['name']}", flush=True)
    print(f"  最大コード: {stocks[-1]['code']} {stocks[-1]['name']}", flush=True)

    jst = timezone(timedelta(hours=9))
    out_data = {
        "description": "東証上場銘柄一覧（プライム/スタンダード/グロース・内国株式）",
        "source": JPX_URL,
        "lastUpdated": datetime.now(jst).isoformat(),
        "count": len(stocks),
        "stocks": stocks,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)

    print(f"\n保存: {out_path} ({out_path.stat().st_size:,} bytes)", flush=True)


if __name__ == "__main__":
    main()
