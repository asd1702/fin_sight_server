import os
import json
import time
import math
import pathlib
from datetime import datetime
from dotenv import load_dotenv
import requests

# --- 설정 ---
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
SILVER_DIR = DATA_DIR / "silver"
CATALOG_PATH = pathlib.Path(__file__).resolve().parent / "catalog_core15.json"

RAW_DIR.mkdir(parents=True, exist_ok=True)
SILVER_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env.dev")
API_KEY = os.getenv("ECOS_API_KEY")
assert API_KEY, "ECOS_API_KEY가 .env.dev에 필요합니다."

# ECOS API endpoint format:
# http://ecos.bok.or.kr/api/StatisticSearch/{API_KEY}/json/kr/{startRow}/{endRow}/{STAT_CODE}/{CYCLE}/{START}/{END}/{ITEM_CODE1}/{ITEM_CODE2}/{ITEM_CODE3}
ECOS_ENDPOINT = "http://ecos.bok.or.kr/api/StatisticSearch/{api}/json/kr/{start}/{end}/{stat}/{cycle}/{sdate}/{edate}"

# 수집 기간(예시): 최근 10년
START_YEAR = 2020
TODAY = datetime.today()

def date_span_for_frequency(freq: str):
    """빈도에 맞는 시작/끝 포맷 계산"""
    if freq == "M":
        s = f"{START_YEAR}01"                  # YYYYMM
        e = TODAY.strftime("%Y%m")
        cycle = "M"
    elif freq == "Q":
        s = f"{START_YEAR}01"                  # ECOS는 분기도 YYYYMM 형식 사용
        e = TODAY.strftime("%Y%m")
        cycle = "Q"
    elif freq == "D":
        s = f"{START_YEAR}0101"                # YYYYMMDD
        e = TODAY.strftime("%Y%m%d")
        cycle = "D"
    else:
        raise ValueError(f"unknown frequency: {freq}")
    return cycle, s, e

def build_url(stat_code, cycle, start_date, end_date, item1=None, item2=None, item3=None, start_row=1, end_row=1000):
    url = ECOS_ENDPOINT.format(
        api=API_KEY, start=start_row, end=end_row, stat=stat_code, cycle=cycle, sdate=start_date, edate=end_date
    )
    # 항목 코드가 있으면 뒤에 이어붙이기
    if item1 is not None:
        url += f"/{item1}"
        if item2 is not None:
            url += f"/{item2}"
            if item3 is not None:
                url += f"/{item3}"
    return url

def fetch_all_rows(stat_code, freq, item1=None, item2=None, item3=None):
    cycle, sdate, edate = date_span_for_frequency(freq)
    results = []
    page = 0
    page_size = 1000

    while True:
        start_row = page * page_size + 1
        end_row = (page + 1) * page_size
        url = build_url(stat_code, cycle, sdate, edate, item1, item2, item3, start_row, end_row)

        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()

        if "StatisticSearch" not in data or "row" not in data["StatisticSearch"]:
            # 더 이상 데이터 없거나, 코드/파라미터가 잘못된 경우일 수 있음
            break

        rows = data["StatisticSearch"]["row"]
        results.extend(rows)

        total_cnt = int(data["StatisticSearch"].get("list_total_count", len(rows)))
        if end_row >= total_cnt:
            break

        page += 1
        time.sleep(0.2)  # rate-limit 여유

    return results

def normalize_record(indicator_id, freq, row: dict):
    # ECOS 공통 필드: TIME, DATA_VALUE, UNIT_NAME 등
    time_key = row.get("TIME")  # YYYYMM or YYYYMMDD or YYYY
    val_str = row.get("DATA_VALUE", None)
    unit = row.get("UNIT_NAME", None)
    source = "ECOS"

    # 값 파싱
    if val_str in (None, "", "."):
        value = None
    else:
        try:
            value = float(val_str)
        except ValueError:
            value = None

    # 날짜 정규화(월/분기/일)
    if freq == "M":
        # YYYYMM → 월말로 정규화
        dt = datetime.strptime(time_key, "%Y%m")
        # 월말로 통일하려면 다음달 1일 - 1일 등으로 처리해도 되지만,
        # 여기서는 YYYY-MM-01로 저장해도 무방(사후 리샘플 단계에서 처리)
        date_str = dt.strftime("%Y-%m-01")
    elif freq == "Q":
        # ECOS 분기도 YYYYMM 형식. 예: 2025Q2 → 202506 등으로 들어오는 경우 있음.
        # 일반화: YYYYMM을 분기 첫달 1일로 저장
        dt = datetime.strptime(time_key, "%Y%m")
        date_str = dt.strftime("%Y-%m-01")
    elif freq == "D":
        dt = datetime.strptime(time_key, "%Y%m%d")
        date_str = dt.strftime("%Y-%m-%d")
    else:
        raise ValueError(f"freq error: {freq}")

    return {
        "indicator_id": indicator_id,
        "date": date_str,
        "value": value,
        "unit": unit,
        "source": source
    }

def main():
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    out_path = SILVER_DIR / "observations_core15.jsonl"
    n_ok = 0
    n_err = 0

    with open(out_path, "w", encoding="utf-8") as out_f:
        for item in catalog:
            indicator_id = item["indicator_id"]
            freq = item["frequency"]
            stat = item["stat_code"]
            item1 = item.get("item_code1")
            item2 = item.get("item_code2")
            item3 = item.get("item_code3")

            print(f"[{indicator_id}] fetching ...")
            try:
                rows = fetch_all_rows(stat, freq, item1, item2, item3)

                # 원본 백업(옵션)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                raw_file = RAW_DIR / f"{indicator_id}_{stamp}.json"
                with open(raw_file, "w", encoding="utf-8") as rf:
                    json.dump(rows, rf, ensure_ascii=False)

                # 정규화 + JSONL 저장
                for r in rows:
                    rec = normalize_record(indicator_id, freq, r)
                    out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")

                n_ok += 1
            except Exception as e:
                n_err += 1
                print(f"  -> ERROR: {e}")

            # polite sleep
            time.sleep(0.2)

    print(f"\nDone. success={n_ok}, error={n_err}")
    print(f"Saved: {out_path}")

if __name__ == "__main__":
    main()
