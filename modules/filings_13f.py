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
    """Получает список документов внутри filing.

    Уровень 1: JSON-индекс EDGAR ({accession}-index.json).
    Уровень 2: HTML-страница индекса EDGAR — парсим ссылки на .xml файлы
               через regex, без зависимости от BeautifulSoup.
    """
    padded = _padded_cik(cik)
    acc_clean = accession.replace("-", "")
    cik_int = int(padded)
    base_archive = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}"

    # ── Уровень 1: JSON индекс ──────────────────────────────────────────────
    try:
        json_url = f"{base_archive}/{accession}-index.json"
        resp = requests.get(json_url, headers=SEC_HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            docs = resp.json().get("documents", [])
            if docs:
                logger.info(f"13F: index JSON OK for CIK={cik}, {len(docs)} docs")
                return docs
    except Exception as e:
        logger.warning(f"13F: JSON index failed for CIK={cik}: {e}")

    # ── Уровень 2: HTML индекс (парсинг regex) ──────────────────────────────
    try:
        html_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/"
        resp = requests.get(html_url, headers={**SEC_HEADERS, "Accept": "text/html"},
                            timeout=TIMEOUT)
        if resp.status_code == 200:
            # Ищем все href на .xml файлы внутри архива
            xml_links = re.findall(
                rf'{re.escape(acc_clean)}/([^"\'>\s]+\.xml)',
                resp.text, re.IGNORECASE,
            )
            # Fallback: любая ссылка на .xml в href
            if not xml_links:
                xml_links = re.findall(r'href="([^"]+\.xml)"', resp.text, re.IGNORECASE)
                xml_links = [lnk.split("/")[-1] for lnk in xml_links]
            if xml_links:
                logger.info(f"13F: HTML index found {xml_links} for CIK={cik}")
                return [{"documentName": name, "description": ""} for name in xml_links]
    except Exception as e:
        logger.warning(f"13F: HTML index failed for CIK={cik}: {e}")

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

        xml_content = None

        # ШАГ 1: читаем индекс filing — самый надёжный способ,
        # не зависит от того как фонд назвал свой файл
        docs = _get_filing_index(cik, accession)
        if docs:
            # Ищем XML-файл таблицы позиций по ключевым словам в имени/описании
            xml_doc = None
            for doc in docs:
                doc_name = (doc.get("documentName") or doc.get("name") or "").lower()
                doc_desc = (doc.get("description") or doc.get("type") or "").lower()
                if any(kw in doc_name or kw in doc_desc for kw in
                       ("infotable", "information_table", "form13f", "13f-hr")):
                    xml_doc = doc.get("documentName") or doc.get("name")
                    break
            # Fallback: любой .xml кроме первичного документа (cover page)
            if not xml_doc:
                for i, doc in enumerate(docs):
                    doc_name = (doc.get("documentName") or doc.get("name") or "").lower()
                    if doc_name.endswith(".xml") and i > 0:
                        xml_doc = doc.get("documentName") or doc.get("name")
                        break
            if xml_doc:
                file_url = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{cik_int}/{acc_clean}/{xml_doc}"
                )
                try:
                    r = requests.get(file_url, headers=SEC_HEADERS, timeout=TIMEOUT)
                    if r.status_code == 200 and len(r.content) > 100:
                        xml_content = r.content
                        logger.info(f"13F: found infotable via index ({xml_doc}) for CIK={cik}")
                except Exception as e:
                    logger.warning(f"13F: index XML fetch failed ({xml_doc}): {e}")

        # ШАГ 2: если индекс не помог — перебираем типичные имена файлов
        if not xml_content:
            candidate_names = [
                "infotable.xml",
                "form13fInfoTable.xml",
                "13fInfoTable.xml",
                "information_table.xml",
                "wfbrkinfopage.xml",   # Berkshire Hathaway
                "13fform.xml",
            ]
            for fname in candidate_names:
                file_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{fname}"
                try:
                    r = requests.get(file_url, headers=SEC_HEADERS, timeout=TIMEOUT)
                    if r.status_code == 200 and len(r.content) > 100:
                        xml_content = r.content
                        logger.info(f"13F: found infotable by name ({fname}) for CIK={cik}")
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
