"""
Scraper do "Busca por médicos" do Portal CFM - via Selenium
Versão adaptada para rodar em GitHub Actions (sempre headless).
"""

import csv
import time
import re

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

URL_BUSCA = "https://portal.cfm.org.br/busca-medicos/"
UF_DESEJADA_TEXTO = "SÃO PAULO"   # texto visível da opção no <select>
ESPERA_APOS_BUSCA = 6
ESPERA_APOS_PAGINACAO = 4
SAIDA_CSV = "medicos_sp.csv"
MAX_PAGINAS = None  # None = até acabar

CRM_REGEX = re.compile(r"\b(EME)?\s?\d{4,7}(-?P)?\b", re.IGNORECASE)


def montar_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")   # sempre headless no CI
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--window-size=1366,1600")
    options.add_argument("--lang=pt-BR")
    # Não passamos 'service' explícito: o Selenium Manager (embutido desde a
    # v4.6) baixa e casa automaticamente a versão certa do chromedriver com
    # o Chrome instalado, evitando o mismatch que costuma causar crash.
    driver = webdriver.Chrome(options=options)
    return driver


def aceitar_cookies(driver, wait):
    for texto in ["Aceito", "PERMITIR", "ACEITO"]:
        try:
            botao = WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable((By.XPATH, f"//button[contains(., '{texto}')] | //a[contains(., '{texto}')]"))
            )
            botao.click()
            print(f"Cookie banner aceito ('{texto}').")
            return
        except TimeoutException:
            continue
    print("Sem banner de cookies (ou já fechado).")


def selecionar_uf_correto(driver, wait):
    """
    Existem 2 <select> na página com uma opção 'SÃO PAULO': o seletor de
    'site regional' no topo, e o campo UF de verdade dentro do formulário
    'Encontre um médico'. Este função localiza especificamente o segundo,
    procurando o <select> que aparece DEPOIS do texto 'Encontre um médico'.
    """
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "select")))

    try:
        marcador = driver.find_element(By.XPATH, "//*[contains(text(), 'Encontre um médico')]")
        selects_apos = driver.find_elements(
            By.XPATH, "//*[contains(text(), 'Encontre um médico')]/following::select"
        )
    except NoSuchElementException:
        selects_apos = []

    candidatos = selects_apos if selects_apos else driver.find_elements(By.TAG_NAME, "select")

    for sel_el in candidatos:
        sel = Select(sel_el)
        opcoes = [o.text.strip().upper() for o in sel.options]
        if any("PAULO" in o for o in opcoes):
            texto_opcao = next(o.text for o in sel.options if "PAULO" in o.text.upper())
            sel.select_by_visible_text(texto_opcao)
            driver.execute_script(
                "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));", sel_el
            )
            print(f"UF selecionada: '{texto_opcao}' (via {'form' if selects_apos else 'fallback genérico'})")
            return True

    print("ERRO: não encontrei nenhum <select> com opção contendo 'PAULO'.")
    return False


def enviar_busca(driver, wait):
    botao = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'ENVIAR')] | //input[@value='ENVIAR']"))
    )
    botao.click()
    print("Botão ENVIAR clicado.")
    time.sleep(ESPERA_APOS_BUSCA)


def extrair_pagina_atual(driver):
    resultados = []
    seletores_linha = [
        "table tbody tr", ".resultado-item", ".card-medico", "li.medico", ".item-resultado"
    ]
    linhas = []
    for sel in seletores_linha:
        linhas = driver.find_elements(By.CSS_SELECTOR, sel)
        if linhas:
            print(f"  Usando seletor de linha: '{sel}' ({len(linhas)} encontradas)")
            break

    if linhas:
        for linha in linhas:
            texto = linha.text.strip()
            if not texto:
                continue
            crm_match = CRM_REGEX.search(texto)
            crm = crm_match.group(0) if crm_match else ""
            primeira_linha = texto.split("\n")[0]
            resultados.append({"nome": primeira_linha, "crm": crm, "uf": "SP", "texto_bruto": texto})
    else:
        print("  Nenhuma linha de resultado estruturada encontrada - salvando fallback vazio.")

    return resultados


def ir_para_proxima_pagina(driver):
    try:
        botao = driver.find_element(
            By.XPATH, "//a[contains(., 'Próxima')] | //a[contains(@class,'next')] | //li[contains(@class,'next')]/a"
        )
    except NoSuchElementException:
        return False

    classes = (botao.get_attribute("class") or "").lower()
    if "disabled" in classes:
        return False

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", botao)
    botao.click()
    time.sleep(ESPERA_APOS_PAGINACAO)
    return True


def main():
    driver = montar_driver()
    wait = WebDriverWait(driver, 15)
    todos_resultados = []

    try:
        driver.get(URL_BUSCA)
        time.sleep(1.5)
        aceitar_cookies(driver, wait)
        driver.save_screenshot("debug_01_form.png")

        uf_ok = selecionar_uf_correto(driver, wait)
        driver.save_screenshot("debug_02_apos_uf.png")

        if uf_ok:
            enviar_busca(driver, wait)
            driver.save_screenshot("debug_03_apos_enviar.png")

            pagina = 1
            while True:
                print(f"\nLendo página {pagina}...")
                resultados_pagina = extrair_pagina_atual(driver)
                print(f"  -> {len(resultados_pagina)} registros nesta página")
                todos_resultados.extend(resultados_pagina)

                if pagina == 1 or pagina % 20 == 0:
                    driver.save_screenshot(f"debug_page_{pagina:04d}.png")

                if MAX_PAGINAS and pagina >= MAX_PAGINAS:
                    print("MAX_PAGINAS atingido.")
                    break

                if not ir_para_proxima_pagina(driver):
                    print("Não há mais páginas. Fim da busca.")
                    break
                pagina += 1
        else:
            print("Abortando: UF não foi selecionada.")

    finally:
        driver.quit()

    with open(SAIDA_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["nome", "crm", "uf", "texto_bruto"])
        writer.writeheader()
        writer.writerows(todos_resultados)

    print(f"\n{'='*50}\nTOTAL: {len(todos_resultados)} registros salvos em {SAIDA_CSV}\n{'='*50}")
    for r in todos_resultados[:50]:
        print(r)


if __name__ == "__main__":
    main()
