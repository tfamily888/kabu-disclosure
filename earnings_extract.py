"""
決算短信PDFから営業利益・経常利益の前年同期比(YoY%)を抽出して
data/disclosures.json の sentiment を再分類する。

ロジック:
  - 営業利益YoY% が +20% 以上 → positive
  - 営業利益YoY% が -20% 以下 → negative
  - 営業利益が抽出できない場合 / 銀行・保険等 → 経常利益で代替
  - それ以外 → 既存 sentiment 維持

GitHub Actions 上で fetch_disclosures.ps1 の後に実行する。

依存: pdfplumber
"""

import io
import json
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pdfplumber

DATA_PATH = Path(__file__).parent / "data" / "disclosures.json"
THRESHOLD = 20.0  # ±20%
PDF_TIMEOUT = 30
SLEEP_BETWEEN = 0.3  # be kind to TDnet


def is_target(d):
    """対象: 決算短信本体 (訂正版・補足説明資料は除く)"""
    title = d.get("title", "")
    if "決算短信" not in title:
        return False
    if "訂正" in title:
        return False
    if "補足" in title:
        return False
    if not d.get("pdfUrl"):
        return False
    return True


def fetch_pdf(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=PDF_TIMEOUT) as resp:
        return resp.read()


def normalize_number(s):
    """日本語の数値表記を float に。△/▲ はマイナス。"""
    if s is None:
        return None
    s = str(s).strip()
    s = s.replace(",", "").replace("，", "")
    s = s.replace("△", "-").replace("▲", "-").replace("−", "-").replace("－", "-")
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_summary_table(text):
    """1ページ目のテキストから 営業利益YoY%, 経常利益YoY% を抽出。

    決算短信の(1)経営成績テーブルは典型的に下記のような構造:
        売 上 高     営業利益    経常利益    親会社株主に帰属する当期純利益(or 四半期純利益)
        百万円 ％    百万円 ％    百万円 ％    百万円 ％
        2026年3月期    XXX,XXX  Y.Y    XX,XXX  Y.Y    XX,XXX  Y.Y    XX,XXX  Y.Y
        2025年3月期    XXX,XXX  Y.Y    XX,XXX  Y.Y    XX,XXX  Y.Y    XX,XXX  Y.Y

    ※ 銀行業: 営業利益→経常収益、経常利益→経常利益
    ※ IFRS: 営業利益→営業利益、経常利益→税引前利益
    ※ 単純化のため「営業利益」「経常利益」のラベルベースで抽出
    """
    lines = [ln for ln in text.split("\n") if ln.strip()]

    # 「2026年3月期」「2026年9月期第2四半期」など年度行を探す
    year_row_re = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月期")
    num_re = re.compile(r"[△▲\-－−]?[\d,，]+\.\d+|[△▲\-－−]?[\d,，]+")

    candidate_rows = []
    for i, line in enumerate(lines):
        if year_row_re.search(line):
            nums = num_re.findall(line)
            if len(nums) >= 6:
                candidate_rows.append((i, line, nums))

    # 最初の候補(=最新期)を採用
    if not candidate_rows:
        return None, None, None

    _, _, nums = candidate_rows[0]
    parsed = [normalize_number(n) for n in nums]

    # 期待カラム順: 売上高, 売上%, 営業利益, 営業利益%, 経常利益, 経常利益%, 純利益, 純利益%
    # IFRS: 売上収益, %, 営業利益, %, 税引前利益, %, 当期利益, %, 親会社所有者帰属当期利益, %
    # 銀行/保険: 経常収益, %, 経常利益, %, ...
    # 6個未満は不正、6-8個でパース
    if len(parsed) < 6:
        return None, None, None

    # heuristic: % は通常 ±100 内、絶対値ベース、利益値は通常 1万 (百万円) 以上
    # 標準的な並び (8値) を仮定
    # parsed[0]=売上高, parsed[1]=売上%, parsed[2]=営業利益, parsed[3]=営業利益%,
    # parsed[4]=経常利益, parsed[5]=経常利益%, parsed[6]=純利益, parsed[7]=純利益%
    op_pct = parsed[3] if len(parsed) > 3 else None
    ord_pct = parsed[5] if len(parsed) > 5 else None

    # サニティチェック: %は -1000 ~ 1000 の範囲
    def sane_pct(v):
        if v is None:
            return None
        if abs(v) > 1000:
            return None
        return v

    op_pct = sane_pct(op_pct)
    ord_pct = sane_pct(ord_pct)

    # 期 (label) を抽出
    period_label = candidate_rows[0][1].split()[0] if candidate_rows[0][1] else ""

    return op_pct, ord_pct, period_label


def classify(op_pct, ord_pct):
    """営業利益優先、無ければ経常利益で sentiment 判定。
    返り値: (sentiment_or_None, primary_pct, used_metric)
    """
    primary = op_pct if op_pct is not None else ord_pct
    metric = "営業利益" if op_pct is not None else "経常利益"

    if primary is None:
        return None, None, None

    if primary >= THRESHOLD:
        return "positive", primary, metric
    if primary <= -THRESHOLD:
        return "negative", primary, metric
    return None, primary, metric  # 既存 sentiment を維持


def main():
    if not DATA_PATH.exists():
        print(f"Not found: {DATA_PATH}", flush=True)
        return

    with open(DATA_PATH, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    disclosures = data.get("disclosures", [])
    targets = [d for d in disclosures if is_target(d)]
    print(f"=== 決算短信の業績抽出 ===", flush=True)
    print(f"対象: {len(targets)} / {len(disclosures)} 件", flush=True)

    overridden_pos = 0
    overridden_neg = 0
    parsed_ok = 0
    failed = 0

    for d in targets:
        code = d.get("code", "")
        company = d.get("company", "")
        title = d.get("title", "")[:60]
        try:
            print(f"\n[{code}] {company}: {title}", flush=True)
            pdf_bytes = fetch_pdf(d["pdfUrl"])
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                if not pdf.pages:
                    print("  (PDFにページなし)", flush=True)
                    failed += 1
                    continue
                text = pdf.pages[0].extract_text() or ""

            op_pct, ord_pct, period = parse_summary_table(text)
            print(f"  期={period} 営業利益YoY={op_pct}% / 経常利益YoY={ord_pct}%", flush=True)

            if op_pct is not None or ord_pct is not None:
                parsed_ok += 1

            d["earnings"] = {
                "period": period,
                "operatingProfitYoYPct": op_pct,
                "ordinaryProfitYoYPct": ord_pct,
            }

            sentiment, primary, metric = classify(op_pct, ord_pct)
            if sentiment == "positive":
                d["sentiment"] = "positive"
                d["analysis"] = f"{metric}が前年同期比 +{primary:.1f}% の大幅増益。決算はポジティブサプライズ。"
                overridden_pos += 1
                print(f"  → POSITIVE 上書き ({metric} +{primary:.1f}%)", flush=True)
            elif sentiment == "negative":
                d["sentiment"] = "negative"
                d["analysis"] = f"{metric}が前年同期比 {primary:.1f}% の大幅減益。要警戒。"
                overridden_neg += 1
                print(f"  → NEGATIVE 上書き ({metric} {primary:.1f}%)", flush=True)

            time.sleep(SLEEP_BETWEEN)

        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            failed += 1

    print(
        f"\n=== 集計 ===\n"
        f"  パース成功: {parsed_ok}件\n"
        f"  失敗: {failed}件\n"
        f"  positive 上書き: {overridden_pos}件\n"
        f"  negative 上書き: {overridden_neg}件",
        flush=True,
    )

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
