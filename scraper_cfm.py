# ============================================================
# AGENTE CFM - Busca de Médicos (UF = SP) - VERSÃO COM DEBUG
# Pagina até o final, mesmo se os seletores de card não baterem
# (nesse caso, cai no fallback de regex por página)
# ============================================================

import re
import time
from playwright.sync_api import sync_playwright

URL = "https://portal.cfm.org.br/busca-medicos/"
RATE_LIMIT_SECONDS = 2.0
SAFETY_MAX_PAGES = 2000  # trava de segurança, não é o limite "real" esperado

CRM_REGEX = re.compile(r"\b(EME)?\s?\d{4,7}(-?P)?\b", re.IGNORECASE)

resultados = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 1600})
    print(f"Abrindo {URL}")
    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)

    try:
        page.get_by_text("Aceito", exact=True).click(timeout=5000)
        print("Cookie banner aceito.")
    except Exception:
        print("Sem banner de cookies (ou já fechado).")

    page.screenshot(path="debug_01_form.png", full_page=True)

    # --- Seleciona UF = São Paulo ---
    uf_selecionada = False
    try:
        selects = page.locator("select")
        n = selects.count()
        print(f"Encontrados {n} elementos <select> na página.")
        for i in range(n):
            sel = selects.nth(i)
            options = sel.locator("option").all_inner_texts()
            paulo_opts = [o for o in options if "PAULO" in o.upper()]
            if paulo_opts:
                sel.select_option(label=paulo_opts[0])
                uf_selecionada = True
                print(f"UF selecionada via <select> #{i}: {paulo_opts[0]}")
                break
    except Exception as e:
        print(f"Tentativa via <select> falhou: {e}")

    if not uf_selecionada:
        try:
            page.get_by_text("Selecione o Estado", exact=True).click()
            page.wait_for_timeout(500)
            page.screenshot(path="debug_02_dropdown_aberto.png", full_page=True)
            page.get_by_text("SÃO PAULO", exact=True).click()
            uf_selecionada = True
            print("UF selecionada via clique em dropdown customizado.")
        except Exception as e:
            print(f"ERRO ao selecionar UF: {e}")

    page.screenshot(path="debug_03_apos_selecionar_uf.png", full_page=True)

    if uf_selecionada:
        try:
            page.get_by_text("ENVIAR", exact=True).click()
            print("Botão ENVIAR clicado.")
        except Exception as e:
            print(f"ERRO ao clicar em ENVIAR: {e}")

        try:
            page.wait_for_load_state("networkidle", timeout=15000)
            print("Rede ficou ociosa.")
        except Exception:
            print("Timeout esperando rede ociosa - seguindo mesmo assim.")

        page.wait_for_timeout(3000)
        page.screenshot(path="debug_04_apos_enviar.png", full_page=True)

        page_num = 1
        while page_num <= SAFETY_MAX_PAGES:
            print(f"\nLendo página {page_num}...")

            cards = page.locator(".resultado-item, .card-medico, li.medico, .item-resultado")
            n_cards = cards.count()

            if n_cards > 0:
                print(f"  {n_cards} cards estruturados encontrados.")
                for i in range(n_cards):
                    texto = cards.nth(i).inner_text().strip()
                    linhas = [l.strip() for l in texto.split("\n") if l.strip()]
                    crm_match = CRM_REGEX.search(texto)
                    crm = crm_match.group(0) if crm_match else None
                    nome = linhas[0] if linhas else None
                    situacao = next((l for l in linhas if l.upper() in ("ATIVO", "INATIVO")), None)
                    especialidade = next((l for l in linhas if "ESPECIALIDADE" in l.upper()), None)
                    resultados.append({
                        "pagina": page_num, "nome": nome, "crm": crm,
                        "situacao": situacao, "especialidade": especialidade,
                    })
            else:
                # Fallback: tenta achar uma área de conteúdo principal (evita header/footer)
                print("  Seletores de card não bateram - usando fallback de texto.")
                container = page.locator("main")
                if container.count() > 0:
                    body_text = container.first.inner_text()
                else:
                    body_text = page.inner_text("body")
                crms_pagina = [m.group(0) for m in CRM_REGEX.finditer(body_text)]
                for crm in crms_pagina:
                    resultados.append({
                        "pagina": page_num, "nome": None, "crm": crm,
                        "situacao": None, "especialidade": None,
                    })

            print(f"  -> {len(resultados)} registros acumulados até agora")

            # Salva um screenshot leve a cada 20 páginas, só pra acompanhar sem gerar excesso de arquivos
            if page_num == 1 or page_num % 20 == 0:
                page.screenshot(path=f"debug_page_{page_num:04d}.png", full_page=True)

            proxima = page.get_by_text("Próxima", exact=False)
            if proxima.count() == 0 or not proxima.first.is_enabled():
                print("Fim da paginação - não há mais botão 'Próxima' habilitado.")
                break

            proxima.first.click()
            time.sleep(RATE_LIMIT_SECONDS)
            page_num += 1
        else:
            print(f"Atingido o limite de segurança de {SAFETY_MAX_PAGES} páginas - parando.")

    browser.close()

print("\n" + "=" * 50)
print(f"TOTAL DE REGISTROS: {len(resultados)}")
print("=" * 50)
for r in resultados[:50]:
    print(f"[Pág {r['pagina']}] Nome: {r['nome']} | CRM: {r['crm']} | "
          f"Situação: {r['situacao']} | Especialidade: {r['especialidade']}")
if len(resultados) > 50:
    print(f"... ({len(resultados) - 50} registros a mais, veja o CSV completo)")

import csv
with open("crms_sp.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["pagina", "nome", "crm", "situacao", "especialidade"])
    writer.writeheader()
    for r in resultados:
        writer.writerow({k: r[k] for k in ["pagina", "nome", "crm", "situacao", "especialidade"]})
print("\nCSV salvo em crms_sp.csv")
