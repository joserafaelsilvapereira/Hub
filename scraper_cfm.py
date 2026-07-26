# ============================================================
# AGENTE CFM - Busca de Médicos (UF = SP) - v3
# Corrige bug: existem 2 <select> com opção "SÃO PAULO" na página
# (o seletor de "site regional" no topo, e o campo UF do formulário
# de busca). O script agora localiza especificamente o <select>
# associado ao label "UF:" dentro da seção "Encontre um médico".
# ============================================================

import re
import time
from playwright.sync_api import sync_playwright

URL = "https://portal.cfm.org.br/busca-medicos/"
RATE_LIMIT_SECONDS = 2.0
SAFETY_MAX_PAGES = 2000

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
        try:
            page.get_by_text("PERMITIR", exact=True).click(timeout=3000)
            print("Cookie banner (PERMITIR) aceito.")
        except Exception:
            print("Sem banner de cookies (ou já fechado).")

    page.screenshot(path="debug_01_form.png", full_page=True)

    # --- Seleciona UF = São Paulo DENTRO DO FORMULÁRIO DE BUSCA ---
    # Estratégia: localizar o texto "Encontre um médico" e restringir a
    # busca do <select> à área abaixo dele (evita pegar o seletor do
    # topo da página, que também tem opção "SÃO PAULO").
    uf_selecionada = False
    try:
        form_section = page.locator("text=Encontre um médico").locator(
            "xpath=ancestor::*[self::section or self::div][1]"
        )
        # Sobe alguns níveis até achar um container que já tenha o <select> de UF
        container = page.locator("body")
        selects_no_form = form_section.locator("xpath=following::select")
        n = selects_no_form.count()
        print(f"Selects encontrados APÓS o texto 'Encontre um médico': {n}")

        for i in range(n):
            sel = selects_no_form.nth(i)
            options = sel.locator("option").all_inner_texts()
            paulo_opts = [o for o in options if "PAULO" in o.upper()]
            if paulo_opts:
                sel.select_option(label=paulo_opts[0])
                sel.dispatch_event("change")
                uf_selecionada = True
                print(f"UF selecionada via <select> (pós-label) #{i}: {paulo_opts[0]}")
                break
    except Exception as e:
        print(f"Tentativa via localização por label falhou: {e}")

    # Fallback antigo, mas agora como ÚLTIMO recurso, avisando explicitamente
    if not uf_selecionada:
        print("AVISO: usando fallback genérico de <select> - pode pegar o seletor errado.")
        try:
            selects = page.locator("select")
            n = selects.count()
            for i in range(n):
                sel = selects.nth(i)
                options = sel.locator("option").all_inner_texts()
                paulo_opts = [o for o in options if "PAULO" in o.upper()]
                if paulo_opts:
                    sel.select_option(label=paulo_opts[0])
                    sel.dispatch_event("change")
                    uf_selecionada = True
                    print(f"UF selecionada via <select> genérico #{i}: {paulo_opts[0]}")
                    break
        except Exception as e:
            print(f"Fallback genérico também falhou: {e}")

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
                print("  Seletores de card não bateram - usando fallback de texto.")
                container_loc = page.locator("main")
                if container_loc.count() > 0:
                    body_text = container_loc.first.inner_text()
                else:
                    body_text = page.inner_text("body")
                crms_pagina = [m.group(0) for m in CRM_REGEX.finditer(body_text)]
                for crm in crms_pagina:
                    resultados.append({
                        "pagina": page_num, "nome": None, "crm": crm,
                        "situacao": None, "especialidade": None,
                    })

            print(f"  -> {len(resultados)} registros acumulados até agora")

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
