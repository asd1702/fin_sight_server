from __future__ import annotations
"""ECOS API client implementation (pragmatic subset for MVP).

ECOS (한국은행 경제통계시스템) 통계 조회 기본 REST 패턴(요약):
    /api/StatisticSearch/{API_KEY}/json/kr/{startRow}/{endRow}/{STAT_CODE}/{CYCLE}/{START_DATE}/{END_DATE}/{ITEM_CODE1}/{ITEM_CODE2}/{ITEM_CODE3}/{ITEM_CODE4}

Notes:
- Pagination: startRow/endRow (1-based). 응답 totalCount 활용하여 추가 페이지 반복.
- 날짜 포맷 START/END: CYCLE 별
        * 월(M): YYYYMM  (예: 202401)
        * 분기(Q): YYYYQ (예: 2024Q1) => TIME: 2024Q1 형태
        * 연간(A or Y): YYYY
        * 일(D): YYYYMMDD
- 응답 필드: statisticSearch 배열 안 각 객체 { STAT_CODE, CYCLE, TIME, DATA_VALUE, ... }
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, List, Dict, Optional
import os
import time
import random
import logging

import requests  # already in requirements

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndicatorSpec:
    indicator_id: str
    stat_code: Optional[str]
    item_code1: Optional[str]
    item_code2: Optional[str]
    item_code3: Optional[str]
    item_code4: Optional[str]
    frequency: Optional[str]


class EcosApiClient:
    PAGE_SIZE_DEFAULT = 1000

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 15.0,
                 max_retries: int = 3, page_size: Optional[int] = None, sleep_between: float = 0.2):
        # Lazy import settings to avoid circular if settings pulls pipelines
        if api_key is None:
            api_key = os.getenv("ECOS_API_KEY")
        if api_key is None:
            try:
                from app.core.config import settings  # type: ignore
                api_key = getattr(settings, 'ECOS_API_KEY', None)
            except Exception:  # settings load failure ignored
                api_key = None
        self.api_key = api_key
        if not self.api_key:
            raise ValueError(
                "ECOS_API_KEY not found. Set it in environment (.env), export ECOS_API_KEY, or pass api_key explicitly."
            )
        self.base_url = base_url or "https://ecos.bok.or.kr/api/StatisticSearch"
        self.timeout = timeout
        self.max_retries = max_retries
        self.page_size = page_size or int(os.getenv("ECOS_PAGE_SIZE", self.PAGE_SIZE_DEFAULT))
        self.sleep_between = sleep_between

    # -------------- Date / format helpers --------------
    def _format_date_token(self, d: date, freq: str) -> str:
        f = (freq or "M").upper()
        if f in ("M",):
            return f"{d.year}{d.month:02d}"
        if f in ("A", "Y"):
            return f"{d.year}"
        if f == "D":
            return d.strftime("%Y%m%d")
        if f == "Q":
            q = (d.month - 1)//3 + 1
            return f"{d.year}Q{q}"
        # fallback monthly
        return f"{d.year}{d.month:02d}"

    def _expand_chunks(self, start: date, end: date, freq: str) -> Iterable[tuple[date, date]]:
        f = (freq or 'M').upper()
        if f in ("A", "Y"):
            # year by year
            cur_year = start.year
            while cur_year <= end.year:
                y_start = date(cur_year, 1, 1)
                y_end = date(cur_year, 12, 31)
                if y_end < start or y_start > end:
                    cur_year += 1
                    continue
                yield max(start, y_start), min(end, y_end)
                cur_year += 1
        elif f == 'Q':
            # quarter chunk: treat similar to monthly (though API may accept full range)
            cur = start
            while cur <= end:
                q_end = min(end, cur + timedelta(days=92))
                yield cur, q_end
                cur = q_end + timedelta(days=1)
        else:  # Monthly/Daily fallback simple range (single call ok unless very wide => leave chunk logic minimal)
            yield start, end

    # -------------- Core request --------------
    def _fetch_page(self, spec: IndicatorSpec, cycle: str, start_token: str, end_token: str,
                    start_row: int, end_row: int) -> Dict:
        # Build dynamic path trimming trailing empty item codes (ECOS 허용 패턴)
        item_codes = [spec.item_code1, spec.item_code2, spec.item_code3, spec.item_code4]
        # Remove trailing None/''
        while item_codes and (item_codes[-1] is None or item_codes[-1] == ''):
            item_codes.pop()
        path_parts = [
            self.base_url,
            self.api_key,
            'json',
            'kr',
            str(start_row),
            str(end_row),
            spec.stat_code or '',
            cycle,
            start_token,
            end_token,
        ] + [c for c in item_codes if c]
        url = '/'.join(path_parts)
        last_err = None
        logger.debug("ECOS URL %s", url)
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.get(url, timeout=self.timeout)
                if resp.status_code != 200:
                    raise RuntimeError(f"status {resp.status_code} body={resp.text[:200]}")
                try:
                    js = resp.json()
                except Exception:
                    raise RuntimeError("Non-JSON response")
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("ECOS response keys=%s", list(js.keys())[:5])
                return js
            except Exception as e:
                last_err = e
                sleep = (0.5 * attempt) + random.random()*0.2
                logger.warning("ECOS fetch attempt %s failed (%s); retrying in %.2fs", attempt, e, sleep)
                time.sleep(sleep)
        raise RuntimeError(f"ECOS fetch failed after {self.max_retries} attempts: {last_err}")

    def _parse_records(self, spec: IndicatorSpec, payload: Dict, freq: str) -> List[Dict]:
        if not payload:
            return []
        key = None
        # Try common key names
        for k in ('StatisticSearch', 'statisticSearch', 'Statisticsearch'):
            if k in payload:
                key = k
                break
        if not key:
            # Sometimes payload contains error structure
            return []
        items = payload[key]
        # Handle dict style (error or single) structure
        if isinstance(items, dict):
            # Error pattern: {'RESULT': {'CODE':'','MESSAGE':'...'}}
            if 'RESULT' in items and not any(k in items for k in ('row','ROW')):
                result = items['RESULT']
                if isinstance(result, dict):
                    logger.debug("ECOS RESULT code=%s message=%s for %s", result.get('CODE'), result.get('MESSAGE'), spec.indicator_id)
                return []
            # Data may be under 'row'
            if 'row' in items and isinstance(items['row'], list):
                items = [{'row': items['row']}]
            else:
                # Fallback: wrap
                items = [items]
        if not isinstance(items, list):
            return []

        # ECOS 구조:
        # [ {"list_total_count": N}, {"row": [ {...}, {...} ] } ] 형태가 일반적.
        # 또는 이미 row 들이 평평하게 올 수도 있다.
        total_count = None
        flat_rows: List[Dict] = []
        for entry in items:
            if not isinstance(entry, dict):
                continue
            # list_total_count capture
            if total_count is None and 'list_total_count' in entry:
                try:
                    total_count = int(entry.get('list_total_count'))
                except Exception:
                    total_count = None
            # nested row list
            if 'row' in entry and isinstance(entry['row'], list):
                for r in entry['row']:
                    if isinstance(r, dict):
                        flat_rows.append(r)
                continue
            # Fallback: treat entry itself as row if it looks like one
            if any(k in entry for k in ('TIME', 'TIME_PERIOD', 'DATA_VALUE', 'DATA')):
                flat_rows.append(entry)

        if not flat_rows:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "ECOS parse: no flat_rows extracted (total_count=%s) raw_item_keys=%s", 
                    total_count, [list(e.keys())[:5] if isinstance(e, dict) else type(e) for e in items][:3]
                )
            return []
        out: List[Dict] = []
        for row in flat_rows:
            time_token = row.get('TIME') or row.get('TIME_PERIOD') or row.get('TIME_CODE')
            if not time_token:
                continue
            try:
                d = self._time_token_to_date(time_token, freq)
            except Exception:
                continue
            val_raw = row.get('DATA_VALUE') or row.get('DATA') or row.get('VALUE')
            if val_raw in (None, ''):
                continue
            try:
                # Remove commas & whitespace
                val = float(str(val_raw).replace(',', '').strip())
            except ValueError:
                continue
            out.append({
                'indicator_id': spec.indicator_id,
                'date': d,
                'value': val,
            })
        if not out:
            logger.debug("ECOS parse produced 0 rows for %s (freq=%s total_count=%s)", spec.indicator_id, freq, total_count)
        return out

    def _time_token_to_date(self, token: str, freq: str) -> date:
        f = (freq or 'M').upper()
        if f in ('M',):
            # YYYYMM
            year = int(token[:4])
            month = int(token[4:6])
            return date(year, month, 1)
        if f in ('A', 'Y'):
            return date(int(token[:4]), 1, 1)
        if f == 'D':
            return date(int(token[:4]), int(token[4:6]), int(token[6:8]))
        if f == 'Q':
            # token like 2024Q1
            year = int(token[:4])
            quarter = int(token[-1])
            month = (quarter - 1)*3 + 1
            return date(year, month, 1)
        # fallback monthly
        year = int(token[:4])
        month = int(token[4:6]) if len(token) >= 6 else 1
        return date(year, month, 1)

    # -------------- Public --------------
    def fetch_observations(self, spec: IndicatorSpec, start: date, end: date) -> List[Dict]:
        if start > end:
            return []
        # Infer frequency from indicator_id suffix if DB frequency seems inconsistent
        freq = (spec.frequency or '').strip().upper() or 'M'
        if spec.indicator_id.endswith('.d') and freq != 'D':
            freq = 'D'
        elif spec.indicator_id.endswith('.m') and freq != 'M':
            freq = 'M'
        elif spec.indicator_id.endswith('.q') and freq != 'Q':
            freq = 'Q'
        elif spec.indicator_id.endswith('.y') and freq not in ('A','Y'):
            freq = 'A'
        cycle = freq.upper()
        # Guard: stat_code must exist
        if not spec.stat_code:
            logger.warning("Indicator %s missing stat_code, skipping", spec.indicator_id)
            return []
        records: List[Dict] = []
        for chunk_start, chunk_end in self._expand_chunks(start, end, freq):
            start_token = self._format_date_token(chunk_start, freq)
            end_token = self._format_date_token(chunk_end, freq)
            start_row = 1
            while True:
                end_row = start_row + self.page_size - 1
                payload = self._fetch_page(spec, cycle, start_token, end_token, start_row, end_row)
                # Parse
                parsed = self._parse_records(spec, payload, freq)
                records.extend(parsed)
                # Determine if more pages. Many ECOS responses include list length only; robust method would check totalCount.
                # Here, if fewer than page_size items returned, assume last page.
                if len(parsed) < self.page_size:
                    break
                start_row = end_row + 1
                time.sleep(self.sleep_between)
        return records

