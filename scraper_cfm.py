"""
Agente de varredura - Busca de Médicos CFM (portal.cfm.org.br/busca-medicos/)
Filtra UF = São Paulo, navega página por página e lista os CRMs encontrados.

REQUISITOS (rodar localmente, na sua máquina):
    pip install playwright pandas
    playwright install chromium

USO:
    python scraper_cfm.py

SAÍDA:
    - crms_sp.csv (nome, crm, uf, situacao, especialidade quando disponíveis)
    - Log no console conforme avança nas páginas

OBSERVAÇÕES:
    - O site usa carregamento dinâmico (JS). Por isso o script controla um
      navegador real via Playwright em vez de bater direto num endpoint HTTP.
    - Os seletores (texto/labels) podem mudar se o CFM atualizar o layout do
      site. Se o script parar de encontrar elementos, rode com HEADLESS=False
      para ver o que está acontecendo na tela e ajustar os seletores.
    - Há uma pausa (RATE_LIMIT_SECONDS) entre páginas para não sobrecarregar
      o servidor do CFM. Não reduza agressivamente.
    - Uso responsável: respeite os Termos de Uso do portal.cfm.org.br e a
      LGPD ao armazenar/tratar os dados coletados.
"""

import csv
import time
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL = "https://portal.cfm.org.br/busca-medicos/"
UF_ALVO = "SÃO PAULO"          # texto exibido no combo de UF
OUTPUT_CSV = "crms_sp.csv"
HEADLESS = True                 # mude para False para debugar visualmente
RATE_LIMIT_SECONDS = 2.0        # pausa entre páginas
MAX_PAGES = None                # None = todas; ou defina um int para limitar em teste


def log(msg):
    print(f"[cfm-scraper] {msg}", flush=True)


def run():
    resultados = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page()
        log(f"Abrindo {URL}")
        page.goto(URL, wait_until="domcontentloaded")

        # Aceita cookies, se o banner aparecer
        try:
            page.get_by_text("Aceito", exact=True).click(timeout=5000)
        except PWTimeout:
            pass

        # Seleciona a UF no combo (ajuste o seletor se o site mudar)
        # O campo é um <select> nativo ou um componente custom - tentamos os dois padrões
        try:
            page.select_option("select#uf", label=UF_ALVO)
        except Exception:
            # fallback: procurar por qualquer <select> próximo ao label "UF"
            selects = page.locator("select")
            found = False
            for i in range(selects.count()):
                sel = selects.nth(i)
                options = sel.locator("option").all_inner_texts()
                if any("SÃO PAULO" in o.upper() or "SAO PAULO" in o.upper() for o in options):
                    sel.select_option(label=UF_ALVO)
                    found = True
                    break
            if not found:
                log("ERRO: não encontrei o campo de UF. Rode com HEADLESS=False para inspecionar.")
                browser.close()
                sys.exit(1)

        log("UF definida como São Paulo. Enviando busca...")

        # Clica no botão ENVIAR
        page.get_by_text("ENVIAR", exact=True).click()

        # Espera resultados carregarem (ajuste o seletor conforme o HTML real da lista)
        page.wait_for_timeout(3000)

        page_num = 1
        while True:
            log(f"Lendo página {page_num}...")

            # --- AJUSTE AQUI: seletor real dos itens de resultado ---
            # Trocar '.resultado-item' pelo seletor correto encontrado ao inspecionar
            # a página (botão direito > Inspecionar no navegador).
            items = page.locator(".resultado-item")
            count = items.count()

            if count == 0:
                log("Nenhum item encontrado nesta página com o seletor atual. "
                    "Ajuste o seletor '.resultado-item' no script.")
                break

            for i in range(count):
                item = items.nth(i)
                texto = item.inner_text()
                # Tenta extrair um padrão de CRM (número, eventualmente com sufixo)
                resultados.append({"pagina": page_num, "bruto": texto.strip()})

            log(f"  -> {count} registros capturados nesta página (total acumulado: {len(resultados)})")

            if MAX_PAGES and page_num >= MAX_PAGES:
                log("Limite MAX_PAGES atingido, parando.")
                break

            # --- AJUSTE AQUI: botão "Próxima página" ---
            proxima = page.get_by_text("Próxima", exact=False)
            if proxima.count() == 0 or not proxima.first.is_enabled():
                log("Não há mais páginas. Fim da varredura.")
                break

            proxima.first.click()
            time.sleep(RATE_LIMIT_SECONDS)
            page_num += 1

        browser.close()

    # Salva CSV
    if resultados:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["pagina", "bruto"])
            writer.writeheader()
            writer.writerows(resultados)
        log(f"Salvo {len(resultados)} registros em {OUTPUT_CSV}")
    else:
        log("Nenhum resultado coletado.")


if __name__ == "__main__":
    run()
