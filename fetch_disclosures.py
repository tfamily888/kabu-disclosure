"""
TDnet適時開示情報 自動取得スクリプト

使い方:
  pip install requests beautifulsoup4
  python fetch_disclosures.py              # 今日の開示を取得
  python fetch_disclosures.py 2026-04-03   # 指定日の開示を取得

出力: data/disclosures.json
"""

import json
import re
import sys
import os
from datetime import datetime, date
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("必要なライブラリをインストールしてください:")
    print("  pip install requests beautifulsoup4")
    sys.exit(1)

# ==================== 設定 ====================

TDNET_BASE = "https://www.release.tdnet.info/inbs"
TDNET_LIST_URL = TDNET_BASE + "/I_list_{page:03d}_{date}.html"

# 重要カテゴリのキーワードマッピング
CATEGORY_KEYWORDS = {
    "決算": ["決算短信", "四半期報告", "決算補足"],
    "業績修正": ["業績予想の修正", "通期業績予想", "連結業績予想の修正"],
    "配当": ["配当予想の修正", "剰余金の配当", "増配", "復配", "特別配当"],
    "自社株買い": ["自己株式の取得", "自社株買い", "自己株式取得"],
    "M&A・組織再編": ["株式交換", "合併", "会社分割", "株式移転", "公開買付",
                      "MBO", "TOB", "経営統合", "子会社化"],
    "業務提携・新製品": ["業務提携", "資本提携", "共同開発", "承認取得",
                        "新製品", "適応拡大"],
    "特別損失": ["減損損失", "特別損失", "のれん", "引当金"],
    "業績修正（上方）": ["上方修正"],
    "業績修正（下方）": ["下方修正"],
    "新サービス": ["新サービス", "商用サービス", "サービス開始"],
    "株式分割": ["株式分割"],
    "新規上場": ["新規上場", "IPO"],
}

# 重要度判定キーワード
HIGH_IMPORTANCE_KEYWORDS = [
    "決算短信", "業績予想の修正", "配当予想の修正", "自己株式の取得",
    "株式交換", "合併", "MBO", "TOB", "公開買付", "上方修正", "下方修正",
    "減損損失", "特別損失", "承認取得", "適応拡大", "株式分割",
    "新規上場", "民事再生", "上場廃止",
]

MEDIUM_IMPORTANCE_KEYWORDS = [
    "業務提携", "資本提携", "新サービス", "商用サービス",
    "代表取締役の異動", "役員人事",
]

# 除外キーワード（重要度低い定型開示）
EXCLUDE_KEYWORDS = [
    "独立役員届出書", "コーポレートガバナンス報告書",
    "定款一部変更", "組織変更", "有価証券届出書",
    "臨時報告書", "大量保有報告書",
]

OUTPUT_DIR = Path(__file__).parent / "data"


# ==================== TDnet取得 ====================

def fetch_tdnet_page(target_date: str, page: int = 1) -> str:
    """TDnetの開示一覧ページを取得"""
    date_str = target_date.replace("-", "")
    url = TDNET_LIST_URL.format(page=page, date=date_str)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.encoding = "utf-8"
        if resp.status_code == 200:
            return resp.text
    except requests.RequestException as e:
        print(f"  ページ{page}取得エラー: {e}")
    return ""


def parse_tdnet_list(html: str) -> list[dict]:
    """TDnetの開示一覧HTMLをパースして開示情報リストを返す"""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # TDnetのテーブル行をパース
    rows = soup.select("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        # 時刻
        time_text = cells[0].get_text(strip=True)
        if not re.match(r"\d{2}:\d{2}", time_text):
            continue

        # 証券コード
        code_text = cells[1].get_text(strip=True)
        code_match = re.match(r"(\d{4})", code_text)
        if not code_match:
            continue
        code = code_match.group(1)

        # 会社名
        company = cells[2].get_text(strip=True)

        # タイトルとPDFリンク
        title_cell = cells[3] if len(cells) > 3 else cells[2]
        title = title_cell.get_text(strip=True)
        pdf_link = ""
        a_tag = title_cell.find("a", href=True)
        if a_tag:
            href = a_tag["href"]
            if not href.startswith("http"):
                href = TDNET_BASE + "/" + href.lstrip("/")
            pdf_link = href
            title = a_tag.get_text(strip=True)

        # 市場区分（あれば）
        market = ""
        if len(cells) > 4:
            market = cells[4].get_text(strip=True)

        items.append({
            "time": time_text,
            "code": code,
            "company": company,
            "title": title,
            "market": market or "プライム",
            "pdfUrl": pdf_link,
        })

    return items


def fetch_all_disclosures(target_date: str) -> list[dict]:
    """全ページの開示情報を取得"""
    all_items = []
    for page in range(1, 20):  # 最大20ページ
        print(f"  ページ {page} を取得中...")
        html = fetch_tdnet_page(target_date, page)
        if not html:
            break
        items = parse_tdnet_list(html)
        if not items:
            break
        all_items.extend(items)
        print(f"    → {len(items)} 件取得")
    return all_items


# ==================== フィルタリング・分類 ====================

def classify_category(title: str) -> str:
    """開示タイトルからカテゴリを判定"""
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in title:
                return category
    return "その他"


def judge_importance(title: str) -> str:
    """開示タイトルから重要度を判定"""
    for kw in HIGH_IMPORTANCE_KEYWORDS:
        if kw in title:
            return "高"
    for kw in MEDIUM_IMPORTANCE_KEYWORDS:
        if kw in title:
            return "中"
    return "低"


def should_exclude(title: str) -> bool:
    """除外すべき定型開示かどうか"""
    for kw in EXCLUDE_KEYWORDS:
        if kw in title:
            return True
    return False


def filter_important(items: list[dict]) -> list[dict]:
    """重要な開示のみ抽出し、カテゴリ・重要度を付与"""
    results = []
    for i, item in enumerate(items):
        title = item["title"]

        if should_exclude(title):
            continue

        category = classify_category(title)
        importance = judge_importance(title)

        # 重要度「低」かつ「その他」カテゴリは除外
        if importance == "低" and category == "その他":
            continue

        item["id"] = f"d{i+1:04d}"
        item["category"] = category
        item["importance"] = importance
        item["summary"] = generate_summary(item)
        item["earnings"] = None  # 決算データは別途パースが必要

        results.append(item)

    return results


def generate_summary(item: dict) -> str:
    """タイトルから簡易要約を生成（実運用ではLLM APIで生成推奨）"""
    title = item["title"]
    company = item["company"]
    category = item.get("category", "")

    if "決算短信" in title:
        return f"{company}が{title.split('〔')[0]}を発表。詳細はPDFをご確認ください。"
    elif "業績予想の修正" in title:
        return f"{company}が業績予想を修正。詳細はPDFをご確認ください。"
    elif "配当予想の修正" in title:
        return f"{company}が配当予想を修正。詳細はPDFをご確認ください。"
    elif "自己株式の取得" in title:
        return f"{company}が自己株式取得を発表。詳細はPDFをご確認ください。"
    else:
        return f"{company}が「{title}」を発表。詳細はPDFをご確認ください。"


# ==================== 出力 ====================

def save_json(disclosures: list[dict], target_date: str):
    """JSON形式で保存"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    data = {
        "lastUpdated": datetime.now().isoformat(),
        "date": target_date,
        "disclosures": disclosures,
    }

    output_path = OUTPUT_DIR / "disclosures.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n保存完了: {output_path}")
    print(f"  重要開示: {len(disclosures)} 件")


# ==================== メイン ====================

def main():
    if len(sys.argv) > 1:
        target_date = sys.argv[1]
    else:
        target_date = date.today().isoformat()

    print(f"=== TDnet開示情報取得 ({target_date}) ===\n")

    # 1. TDnetから全開示を取得
    print("1. TDnetから開示一覧を取得中...")
    all_items = fetch_all_disclosures(target_date)
    print(f"\n   全開示件数: {len(all_items)} 件")

    if not all_items:
        print("\n開示情報が見つかりませんでした。")
        print("※ 市場営業日でない場合や、TDnetの構造変更の可能性があります。")
        # サンプルデータがあればそのまま
        return

    # 2. 重要開示をフィルタリング
    print("\n2. 重要開示を抽出中...")
    important = filter_important(all_items)
    print(f"   重要開示: {len(important)} 件")

    # 3. JSON保存
    print("\n3. JSON出力中...")
    save_json(important, target_date)

    print("\n=== 完了 ===")
    print("index.html をブラウザで開くと一覧が表示されます。")


if __name__ == "__main__":
    main()
