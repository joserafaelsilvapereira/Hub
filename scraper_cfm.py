# ============================================================
# AGENTE CFM - Busca de Médicos (UF = SP)
# Extrai: nome, CRM, situação, especialidade (quando disponíveis)
# Feito para rodar via GitHub Actions (dependências instaladas no workflow)
# ============================================================

import re
import time
from playwright.sync_api import sync_playwright

URL = "https://portal.cfm.org.br/busca-medicos/"
RATE_LIMIT_SECONDS = 2.0
MAX_PAGES = None  # None = todas as páginas

CRM_REGEX = re.compile(r"\b(EME)?\s?\d{4,7}(-?P)?\b", re.IGNORECASE)

resultados = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    print(f"Abrindo {URL}")
    page.goto(URL, wait_until="domcontentloaded")

    try:
        page.get_by_text("Aceito", exact=True).click(timeout=5000)
    except Exception:
        pass

    # --- Seleciona UF = São Paulo ---
    uf_selecionada = False
    try:
        selects = page.locator("select")
        for i in range(selects.count()):
            sel = selects.nth(i)
            options = sel.locator("option").all_inner_texts()
            paulo_opts = [o for o in options if "PAULO" in o.upper()]
            if paulo_opts:
                sel.select_option(label=paulo_opts[0])
                uf_selecionada = True
                break
    except Exception as e:
        print(f"Tentativa via <select> falhou: {e}")

    if not uf_selecionada:
        try:
            page.get_by_text("Selecione o Estado", exact=True).click()
            page.get_by_text("SÃO PAULO", exact=True).click()
            uf_selecionada = True
        except Exception as e:
            print(f"ERRO ao selecionar UF: {e}")

    if uf_selecionada:
        print("UF = São Paulo selecionada.")
        page.get_by_text("ENVIAR", exact=True).click()
        page.wait_for_timeout(3000)

        page_num = 1
        while True:
            print(f"\nLendo página {page_num}...")

            cards = page.locator(".resultado-item, .card-medico, li.medico, .item-resultado")
            n_cards = cards.count()

            if n_cards > 0:
                for i in range(n_cards):
                    texto = cards.nth(i).inner_text().strip()
                    linhas = [l.strip() for l in texto.split("\n") if l.strip()]

                    crm_match = CRM_REGEX.search(texto)
                    crm = crm_match.group(0) if crm_match else None

                    nome = linhas[0] if linhas else None
                    situacao = next((l for l in linhas if l.upper() in ("ATIVO", "INATIVO")), None)
                    especialidade = next((l for l in linhas if "ESPECIALIDADE" in l.upper()), None)

                    resultados.append({
                        "pagina": page_num,
                        "nome": nome,
                        "crm": crm,
                        "situacao": situacao,
                        "especialidade": especialidade,
                        "texto_bruto": texto,
                    })
            else:
                print("  (seletores de card não bateram - salvando texto bruto da página)")
                body_text = page.inner_text("body")
                crms_pagina = [m.group(0) for m in CRM_REGEX.finditer(body_text)]
                for crm in crms_pagina:
                    resultados.append({
                        "pagina": page_num,
                        "nome": None,
                        "crm": crm,
                        "situacao": None,
                        "especialidade": None,
                        "texto_bruto": None,
                    })

            print(f"  -> {len(resultados)} registros acumulados até agora")

            if MAX_PAGES and page_num >= MAX_PAGES:
                print("MAX_PAGES atingido, parando.")
                break

            proxima = page.get_by_text("Próxima", exact=False)
            if proxima.count() == 0 or not proxima.first.is_enabled():
                print("Fim da paginação.")
                break

            proxima.first.click()
            time.sleep(RATE_LIMIT_SECONDS)
            page_num += 1
    else:
        print("Não foi possível selecionar a UF. Veja o erro acima.")

    browser.close()

print("\n" + "=" * 50)
print(f"TOTAL DE REGISTROS: {len(resultados)}")
print("=" * 50)
for r in resultados:
    print(f"[Pág {r['pagina']}] Nome: {r['nome']} | CRM: {r['crm']} | "
          f"Situação: {r['situacao']} | Especialidade: {r['especialidade']}")

import csv
with open("crms_sp.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["pagina", "nome", "crm", "situacao", "especialidade"])
    writer.writeheader()
    for r in resultados:
        writer.writerow({k: r[k] for k in ["pagina", "nome", "crm", "situacao", "especialidade"]})
print("\nCSV salvo em crms_sp.csv")
