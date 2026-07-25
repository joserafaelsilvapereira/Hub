# ============================================================
# SCRAPER CFM - Busca de Médicos (UF = SP)
# ============================================================
# Instalar antes de rodar (uma vez só), no terminal:
#   pip install playwright
#   playwright install chromium
#   playwright install-deps chromium
# ============================================================

import csv
import re
import time
from playwright.sync_api import sync_playwright

URL = "https://portal.cfm.org.br/busca-medicos/"
OUTPUT_CSV = "crms_sp.csv"
RATE_LIMIT_SECONDS = 2.0
MAX_PAGES = None  # None = pega todas as páginas

CRM_REGEX = re.compile(r"\b(EME)?\s?\d{4,7}(-?P)?\b", re.IGNORECASE)


def log(msg):
    print(f"[cfm-scraper] {msg}", flush=True)


def run():
    resultados = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        log(f"Abrindo {URL}")
        page.goto(URL, wait_until="domcontentloaded")

        try:
            page.get_by_text("Aceito", exact=True).click(timeout=5000)
        except Exception:
            pass

        uf_selecionada = False
        try:
            selects = page.locator("select")
            for i in range(selects.count()):
                sel = selects.nth(i)
                options = sel.locator("option").all_inner_texts()
                if any("SÃO PAULO" in o.upper() or "SAO PAULO" in o.upper() for o in options):
                    sel.select_option(label=[o for o in options if "PAULO" in o.upper()][0])
                    uf_selecionada = True
                    break
        except Exception as e:
            log(f"Tentativa via <select> falhou: {e}")

        if not uf_selecionada:
            try:
                page.get_by_text("Selecione o Estado", exact=True).click()
                page.get_by_text("SÃO PAULO", exact=True).click()
                uf_selecionada = True
            except Exception as e:
                log(f"ERRO ao selecionar UF: {e}")
                browser.close()
                return

        log("UF = São Paulo selecionada.")

        page.get_by_text("ENVIAR", exact=True).click()
        page.wait_for_timeout(3000)

        page_num = 1
        while True:
            log(f"Lendo página {page_num}...")

            body_text = page.inner_text("body")
            matches = CRM_REGEX.finditer(body_text)
            crms_pagina = [m.group(0).strip() for m in matches]

            if not crms_pagina:
                log("Nenhum CRM identificado nesta página.")

            for crm in crms_pagina:
                resultados.append({"pagina": page_num, "crm": crm})

            log(f"  -> {len(crms_pagina)} CRMs nesta página (total: {len(resultados)})")

            if MAX_PAGES and page_num >= MAX_PAGES:
                log("MAX_PAGES atingido, parando.")
                break

            proxima = page.get_by_text("Próxima", exact=False)
            if proxima.count() == 0 or not proxima.first.is_enabled():
                log("Fim da paginação.")
                break

            proxima.first.click()
            time.sleep(RATE_LIMIT_SECONDS)
            page_num += 1

        browser.close()

    if resultados:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["pagina", "crm"])
            writer.writeheader()
            writer.writerows(resultados)
        log(f"Salvo {len(resultados)} CRMs em {OUTPUT_CSV}")
    else:
        log("Nenhum CRM coletado.")


run()
