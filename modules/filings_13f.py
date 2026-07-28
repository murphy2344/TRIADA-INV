"""
13F Filings — квартальные отчёты крупных фондов (институциональных инвесторов).

Источник: официальный SEC EDGAR API (data.sec.gov), без ключа.
ОБЯЗАТЕЛЕН правильный User-Agent с контактным email — без него SEC блокирует.

Встроенная задержка данных: до 45 дней после конца квартала по требованию SEC.
В посте явно указываем период — не создаём ложного впечатления свежих данных.

Воркфлоу:
1. GET data.sec.gov/submissions/CIK{padded}.json — список всех поданных форм
2. Найти последнюю 13F-HR, взять номер accession
3. GET EDGAR filing index — найти infotable.xml (информационная таблица позиций)
4. Парсить XML — взять топ-5 позиций по value (в тысячах долларов)
"""
import logging
import re
import requests
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

SEC_HEADERS = {
    "User-Agent": "TriadaInvestingBot contact@triada-investing.com",
    "Accept": "application/json",
}
TIMEOUT = 20

# CIK — уникальный номер SEC. Источник: EDGAR Company Search.
WATCHLIST_13F = {
    "0001067983": "Berkshire Hathaway (Уоррен Баффет)",
    "0001336528": "Bridgewater Associates",
    "0001037389": "Renaissance Technologies",
    "0001029160": "Soros Fund Management",
}


def _padded_cik(cik: str) -> str:
    """CIK должен быть 10 символов с ведущими нулями."""
    return cik.strip().zfill(10)


def _find_latest_13f_accession(cik: str) -> str | None:
    """Ищет последнюю форму 13F-HR в submissions."""
    try:
        padded = _padded_cik(cik)
        url = f"https://data.sec.gov/submissions/CIK{padded}.json"
        resp = requests.get(url, headers=SEC_HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])

        for form, acc in zip(forms, accessions):
            if form in ("13F-HR", "13F-HR/A"):
                return acc  # формат: "0001067983-24-000001"
        return None
    except Exception as e:
        logger.error(f"13F find accession error (CIK={cik}): {e}")
        return None


def _get_filing_index(cik: str, accession: str) -> list[dict] | None:
    """Получает индекс файлов внутри filing."""
    try:
        padded = _padded_cik(cik)
        acc_clean = accession.replace("-", "")
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={padded}&type=13F-HR&dateb=&owner=include&count=1&search_text="
        # Используем прямой JSON API для индекса
        idx_url = f"https://data.sec.gov/submissions/CIK{padded}.json"
        # Строим URL к индексу конкретного filing
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(padded)}"
            f"/{acc_clean}/{accession}-index.json"
        )
        resp = requests.get(filing_url, headers=SEC_HEADERS, timeout=TIMEOUT)
        if resp.status_code != 200:
            return None
        idx_data = resp.json()
        return idx_data.get("documents", [])
    except Exception as e:
        logger.error(f"13F filing index error (CIK={cik}, acc={accession}): {e}")
        return None


def _parse_infotable_xml(xml_content: bytes) -> list[dict]:
    """Парсит infotable.xml из 13F-HR, возвращает топ-5 позиций по value."""
    try:
        # XML может содержать namespace
        content = xml_content.decode("utf-8", errors="replace")
        # Убираем namespace для упрощения парсинга
        content = re.sub(r'\s+xmlns[^"]*"[^"]*"', '', content)
        content = re.sub(r'<[^>]+:', '<', content)
        content = re.sub(r'</[^>]+:', '</', content)

        root = ET.fromstring(content)
        positions = []

        # Ищем infoTable entries
        for entry in root.iter("infoTable"):
            name = entry.findtext("nameOfIssuer") or entry.findtext("nameofissuer") or ""
            value_text = entry.findtext("value") or entry.findtext("Value") or "0"
            try:
                value = int(str(value_text).replace(",", "").strip())
            except (ValueError, TypeError):
                value = 0
            shrs_node = entry.find("shrsOrPrnAmt") or entry.find("shrsorprnamts")
            shares = 0
            if shrs_node is not None:
                shares_text = shrs_node.findtext("sshPrnamt") or shrs_node.findtext("sshprnamt") or "0"
                try:
                    shares = int(str(shares_text).replace(",", "").strip())
                except (ValueError, TypeError):
                    shares = 0

            if name and value > 0:
                positions.append({"name": name.strip(), "value": value, "shares": shares})

        # Топ-5 по value (в тысячах $)
        positions.sort(key=lambda x: x["value"], reverse=True)
        return positions[:5]
    except Exception as e:
        logger.error(f"infotable XML parse error: {e}")
        return []


def fetch_latest_13f(cik: str) -> dict | None:
    """Загружает последний 13F-HR для CIK. Возвращает dict с топ-5 позициями.
    При любой ошибке парсинга — возвращает None, не падает."""
    try:
        accession = _find_latest_13f_accession(cik)
        if not accession:
            logger.warning(f"13F: no 13F-HR found for CIK={cik}")
            return None

        padded = _padded_cik(cik)
        acc_clean = accession.replace("-", "")
        cik_int = int(padded)

        # Пробуем стандартные имена файла информационной таблицы
        candidate_names = [
            "infotable.xml",
            "form13fInfoTable.xml",
            "13fInfoTable.xml",
            "information_table.xml",
        ]

        xml_content = None
        for fname in candidate_names:
            file_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{fname}"
            try:
                r = requests.get(file_url, headers=SEC_HEADERS, timeout=TIMEOUT)
                if r.status_code == 200 and len(r.content) > 100:
                    xml_content = r.content
                    logger.info(f"13F: found infotable at {fname} for CIK={cik}")
                    break
            except Exception:
                continue

        # Если не нашли по имени — ищем через индекс
        if not xml_content:
            docs = _get_filing_index(cik, accession)
            if docs:
                for doc in docs:
                    doc_name = (doc.get("documentName") or doc.get("name") or "").lower()
                    if "infotable" in doc_name or "information_table" in doc_name:
                        file_url = (
                            f"https://www.sec.gov/Archives/edgar/data/"
                            f"{cik_int}/{acc_clean}/{doc.get('documentName') or doc.get('name')}"
                        )
                        try:
                            r = requests.get(file_url, headers=SEC_HEADERS, timeout=TIMEOUT)
                            if r.status_code == 200 and len(r.content) > 100:
                                xml_content = r.content
                                break
                        except Exception:
                            continue

        if not xml_content:
            logger.warning(f"13F: could not find infotable XML for CIK={cik}, acc={accession}")
            return None

        positions = _parse_infotable_xml(xml_content)
        if not positions:
            return None

        # Определяем период отчёта из accession number (год в номере)
        # Формат: XXXXXXXXXX-YY-NNNNNN → YY = последние 2 цифры года
        acc_parts = accession.split("-")
        report_period = f"accession {accession}"
        if len(acc_parts) >= 2:
            year_short = acc_parts[1]
            try:
                year = 2000 + int(year_short)
                report_period = f"{year}"
            except ValueError:
                pass

        return {
            "cik": cik,
            "accession": accession,
            "report_period": report_period,
            "positions": positions,
        }
    except Exception as e:
        logger.error(f"fetch_latest_13f error (CIK={cik}): {e}")
        return None


def fetch_all_13f() -> list[dict]:
    """Загружает последний 13F по всем фондам из WATCHLIST_13F.
    Один сбойный фонд не роняет остальные."""
    results = []
    for cik, fund_name in WATCHLIST_13F.items():
        try:
            item = fetch_latest_13f(cik)
            if item:
                item["fund_name"] = fund_name
                results.append(item)
        except Exception as e:
            logger.error(f"fetch_all_13f: skip {fund_name} (CIK={cik}): {e}")
            continue
    return results
