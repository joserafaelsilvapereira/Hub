"""
Scraper do "Busca por médicos" do Portal CFM (portal.cfm.org.br/busca-medicos)

O QUE ESSE SCRIPT FAZ
----------------------
1. Abre o navegador (Chrome via Selenium) na página de busca.
2. Seleciona a UF (SP, no primeiro momento).
3. Envia a busca.
4. Espera alguns segundos pro resultado carregar (é uma chamada AJAX).
5. Lê nome / CRM / especialidade de cada linha do resultado.
6. Clica em "próxima página" e repete, até acabar as páginas.
7. Salva tudo em um CSV.

IMPORTANTE - SELETORES
-----------------------
Não consegui abrir um navegador de verdade nesta sessão pra inspecionar o
HTML real (só tenho acesso a uma versão estática da página, sem o JS
renderizado). Os seletores abaixo (SELECTORS) são minha melhor estimativa
com base no padrão do site, mas você provavelmente vai precisar corrigir
1 ou 2 deles.

Como ajustar:
  1. Rode o script uma vez com HEADLESS = False (linha abaixo) pra ver o
     Chrome abrindo de verdade.
  2. Quando der erro de "elemento não encontrado", aperte F12 no navegador
     na página https://portal.cfm.org.br/busca-medicos/, clique com o
     botão direito no campo/elemento que o script não achou > Inspecionar,
     e copie o seletor certo (id, name ou classe) pro dicionário SELECTORS.

REQUISITOS (rodar localmente, no seu computador):
    O script instala o pacote "selenium" sozinho na primeira vez que rodar
    (veja abaixo). Você só precisa ter o Chrome instalado e o chromedriver
    compatível com sua versão do Chrome:
    # https://googlechromelabs.github.io/chrome-for-testing/
"""

import csv
import subprocess
import sys
import time

try:
    from selenium import webdriver
except ImportError:
    print("Pacote 'selenium' não encontrado - instalando via pip...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "selenium"])
    from selenium import webdriver

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ----------------------------------------------------------------------
# CONFIGURAÇÃO
# ----------------------------------------------------------------------
URL_BUSCA = "https://portal.cfm.org.br/busca-medicos/"
UF_DESEJADA = "SP"
HEADLESS = False          # deixe False na primeira vez, pra você acompanhar
ESPERA_APOS_BUSCA = 5      # segundos de espera após clicar em enviar (pedido seu)
ESPERA_APOS_PAGINACAO = 4  # segundos de espera após trocar de página
SAIDA_CSV = "medicos_sp.csv"
MAX_PAGINAS = None         # None = vai até acabar; ou defina um número pra testar (ex: 3)

# Seletores do formulário/resultado — AJUSTAR conforme o HTML real (ver docstring acima)
SELECTORS = {
    "cookie_aceito_widget": ".cb__b_allow",
    "cookie_aceito": "//button[contains(., 'Aceito')] | //a[contains(., 'ACEITO')]",
    "select_uf": "select[name='uf'], #uf, select#estado",
    "botao_enviar": "//button[contains(., 'ENVIAR')] | //input[@value='ENVIAR']",
    "linha_resultado": "table tbody tr, .resultado-item, .card-medico",
    "coluna_nome": ".nome, td:nth-child(1)",
    "coluna_crm": ".crm, td:nth-child(2)",
    "coluna_especialidade": ".especialidade, td:nth-child(3)",
    "botao_proxima_pagina": "//a[contains(., 'Próxima')] | //a[contains(@class,'next')] | //li[contains(@class,'next')]/a",
}


def montar_driver():
    options = webdriver.ChromeOptions()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--lang=pt-BR")
    driver = webdriver.Chrome(options=options)
    return driver


def aceitar_cookies(driver, wait):
    # O botão de texto "Aceito" costuma ficar coberto por um widget de
    # cookies (classe cb__b_allow) que sobrepõe o layout, o que causa
    # ElementClickInterceptedException num .click() normal do Selenium.
    # Por isso: (1) tenta o seletor real do widget primeiro, e (2) usa
    # clique via JavaScript, que ignora sobreposição de elementos.
    for by, seletor in [
        (By.CSS_SELECTOR, SELECTORS["cookie_aceito_widget"]),
        (By.XPATH, SELECTORS["cookie_aceito"]),
    ]:
        try:
            botao = WebDriverWait(driver, 4).until(EC.presence_of_element_located((by, seletor)))
            driver.execute_script("arguments[0].click();", botao)
            time.sleep(0.5)
            return
        except TimeoutException:
            continue
    pass  # banner pode não aparecer sempre


def selecionar_uf(driver, wait, uf: str):
    select_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORS["select_uf"])))
    Select(select_el).select_by_visible_text(uf) if len(uf) > 2 else _select_by_value_ou_texto(select_el, uf)


def _select_by_value_ou_texto(select_el, uf):
    sel = Select(select_el)
    try:
        sel.select_by_value(uf)
    except NoSuchElementException:
        # tenta achar a opção cujo texto contenha a sigla
        for opt in sel.options:
            if uf.lower() in opt.text.lower():
                sel.select_by_visible_text(opt.text)
                return
        raise


def enviar_busca(driver, wait):
    botao = wait.until(EC.element_to_be_clickable((By.XPATH, SELECTORS["botao_enviar"])))
    botao.click()
    # espera pedida: alguns segundos após a busca, pro resultado (AJAX) aparecer
    time.sleep(ESPERA_APOS_BUSCA)


def extrair_pagina_atual(driver):
    resultados = []
    linhas = driver.find_elements(By.CSS_SELECTOR, SELECTORS["linha_resultado"])
    for linha in linhas:
        try:
            nome = linha.find_element(By.CSS_SELECTOR, SELECTORS["coluna_nome"]).text.strip()
        except NoSuchElementException:
            nome = ""
        try:
            crm = linha.find_element(By.CSS_SELECTOR, SELECTORS["coluna_crm"]).text.strip()
        except NoSuchElementException:
            crm = ""
        try:
            especialidade = linha.find_element(By.CSS_SELECTOR, SELECTORS["coluna_especialidade"]).text.strip()
        except NoSuchElementException:
            especialidade = ""

        if nome:  # ignora linhas vazias/cabeçalho
            resultados.append({"nome": nome, "crm": crm, "uf": UF_DESEJADA, "especialidade": especialidade})
    return resultados


def ir_para_proxima_pagina(driver) -> bool:
    """Retorna True se conseguiu clicar e avançar, False se não há mais páginas."""
    try:
        botao = driver.find_element(By.XPATH, SELECTORS["botao_proxima_pagina"])
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
        aceitar_cookies(driver, wait)
        selecionar_uf(driver, wait, UF_DESEJADA)
        enviar_busca(driver, wait)

        pagina = 1
        while True:
            print(f"Lendo página {pagina}...")
            resultados_pagina = extrair_pagina_atual(driver)
            print(f"  -> {len(resultados_pagina)} registros encontrados nesta página")
            todos_resultados.extend(resultados_pagina)

            if MAX_PAGINAS and pagina >= MAX_PAGINAS:
                break

            avancou = ir_para_proxima_pagina(driver)
            if not avancou:
                print("Não há mais páginas. Fim da busca.")
                break
            pagina += 1

    finally:
        driver.quit()

    # salva em CSV
    with open(SAIDA_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["nome", "crm", "uf", "especialidade"])
        writer.writeheader()
        writer.writerows(todos_resultados)

    print(f"\nTotal: {len(todos_resultados)} médicos salvos em {SAIDA_CSV}")


if __name__ == "__main__":
    main()
