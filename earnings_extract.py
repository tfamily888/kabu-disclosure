"""
決算短信PDFから営業利益・経常利益の前年同期比(YoY%)を抽出して
data/disclosures.json の sentiment を再分類する。

ロジック:
  - 営業利益YoY% が +20% 以上 → positive
  - 営業利益YoY% が -20% 以下 → negative
  - 営業利益が抽出できない場合 → 経常利益で代替
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
SLEEP_BETWEEN = 0.3

# 決算短信本体ではないもの (タイトルに「決算短信」を含むだけの開示) を除外
NON_KESSAN_KEYWORDS = [
    "訂正", "補足", "の開示", "開示遅延", "遅延", "委員会",
    "サマリー", "説明資料", "について（", "について(",
]


def is_target(d):
    title = d.get("title", "")
    if "決算短信" not in title:
        return False
    for kw in NON_KESSAN_KEYWORDS:
        if kw in title:
            return False
    if not d.get("pdfUrl"):
        return False
    return True


def fetch_pdf(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=PDF_TIMEOUT) as resp:
        return resp.read()


def normalize_number(s):
    """数値 or '－'(プレースホルダ) を float | None に変換。"""
    if s is None:
        return None
    s = str(s).strip()
    # 「－」「―」「−」単独はYoY算出不能 → None
    if s in {"-", "－", "―", "−"}:
        return None
    s = s.replace(",", "").replace("，", "")
    s = s.replace("△", "-").replace("▲", "-").replace("−", "-").replace("－", "-")
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


YEAR_RE = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月期")
# 数値 or 「－」(YoY算出不能のプレースホルダ)
NUM_RE = re.compile(r"[△▲\-－−]?[\d,，]+\.\d+|[△▲\-－−]?[\d,，]+|[－―−]")
# 「第X四半期」「（中間期）」「中間連結」など期種接尾辞
QUARTER_PREFIX_RE = re.compile(r"^\s*(第[０-９0-9]+四半期|中間連結|中間|（中間期）|\(中間期\))\s*")

# 見出し行（実データ行ではない）を識別するキーワード
HEADER_HINTS = [
    "業績", "経営成績", "連結", "非連結", "個別",
    "（連結）", "（非連結）", "（個別）",
    "（百万円", "（％）", "（％表示", "（％は",
    "対前年同期", "対前期",
]


def is_data_row(line, year_match):
    """この行が実際の決算データ行かどうか判定"""
    # 行頭〜数文字以内に年度プレフィックスがあるべき
    if year_match.start() > 8:
        return False
    # 見出しキーワードを含む行は除外
    for kw in HEADER_HINTS:
        if kw in line:
            return False
    return True


def parse_summary_table(text):
    """1ページ目テキストから 営業利益YoY%, 経常利益YoY% を抽出。

    決算短信の(1)経営成績テーブル:
        売 上 高     営業利益    経常利益    親会社株主に帰属する当期純利益
        百万円  ％    百万円  ％   百万円  ％    百万円  ％
        2026年3月期    XXX,XXX  Y.Y    XX,XXX  Y.Y    XX,XXX  Y.Y    XX,XXX  Y.Y
        2025年3月期    XXX,XXX  Y.Y    XX,XXX  Y.Y    XX,XXX  Y.Y    XX,XXX  Y.Y

    IFRSの場合: 売上収益, 営業利益, 税引前利益, 当期利益(純利益)
                 → 「経常利益」位置は「税引前利益」だが本実装では同じ列に格納
    """
    lines = text.split("\n")

    candidates = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = YEAR_RE.search(line)
        if not m:
            continue
        if not is_data_row(line, m):
            continue
        # 年度プレフィックス以降のテキストだけを対象に
        rest = line[m.end():]
        # 「第X四半期」「中間期」などの期種接尾辞を除去
        rest = QUARTER_PREFIX_RE.sub("", rest)
        nums = NUM_RE.findall(rest)
        parsed = [normalize_number(n) for n in nums]
        # 位置を保持 (None も列構造のため残す)

        # データ行は最低6個 (3列構造)、最大12個程度の数値+ダッシュ
        if len(parsed) < 6 or len(parsed) > 14:
            continue
        candidates.append((line, parsed))

    if not candidates:
        return None, None, None

    # 候補が複数あれば最初(=最新期、通常2026年X月期)を採用
    best_line, parsed = candidates[0]

    # 想定カラム順 (年度プレフィックス除去済):
    #   8個 (4列): 売上, 売上%, 営業利益, 営業利益%, 経常利益, 経常利益%, 純利益, 純利益%
    #   6個 (3列): 売上, 売上%, 営業利益, 営業利益%, 純利益, 純利益% (経常利益省略=IFRS一部)
    op_pct = None
    ord_pct = None

    if len(parsed) >= 8:
        op_pct = parsed[3]
        ord_pct = parsed[5]
    elif len(parsed) >= 6:
        op_pct = parsed[3]

    def sane_pct(v):
        if v is None:
            return None
        if abs(v) > 1000:  # 異常値は除外
            return None
        return v

    return sane_pct(op_pct), sane_pct(ord_pct), best_line[:60]


def classify(op_pct, ord_pct):
    """営業利益優先、無ければ経常利益で sentiment 判定。"""
    primary = op_pct if op_pct is not None else ord_pct
    metric = "営業利益" if op_pct is not None else "経常利益"

    if primary is None:
        return None, None, None

    if primary >= THRESHOLD:
        return "positive", primary, metric
    if primary <= -THRESHOLD:
        return "negative", primary, metric
    return None, primary, metric


def main():
    debug = "--debug" in sys.argv

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

            if debug:
                print("  --- DEBUG TEXT (first 30 lines) ---", flush=True)
                for ln in text.split("\n")[:30]:
                    print(f"  | {ln}", flush=True)
                print("  --- END DEBUG ---", flush=True)

            op_pct, ord_pct, period = parse_summary_table(text)
            print(f"  → period='{period}' 営業利益={op_pct}% 経常利益={ord_pct}%", flush=True)

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
                print(f"  ★ POSITIVE 上書き ({metric} +{primary:.1f}%)", flush=True)
            elif sentiment == "negative":
                d["sentiment"] = "negative"
                d["analysis"] = f"{metric}が前年同期比 {primary:.1f}% の大幅減益。要警戒。"
                overridden_neg += 1
                print(f"  ★ NEGATIVE 上書き ({metric} {primary:.1f}%)", flush=True)

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
