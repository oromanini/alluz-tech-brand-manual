import asyncio
import random
import re
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout

AVA_LOGIN_URL = "https://www.copel.com/avaweb/paginaLogin/login.jsf"
AVA_INICIO_URL = "https://www.copel.com/avaweb/paginas/inicio.jsf"

# Tolerância máxima por operação (ms)
TIMEOUT_NAV = 30_000
TIMEOUT_ELEM = 15_000


class CopelAuthError(Exception):
    pass


class CopelFaturaNotFoundError(Exception):
    pass


class CopelScraperError(Exception):
    pass


async def _delay():
    """Pausa aleatória entre ações para não disparar WAF."""
    await asyncio.sleep(random.uniform(1.2, 3.5))


async def _fazer_login(page: Page, cpf_cnpj: str, senha: str) -> None:
    await page.goto(AVA_LOGIN_URL, wait_until="domcontentloaded", timeout=TIMEOUT_NAV)
    await _delay()

    # Tentar preencher CPF/CNPJ — o portal AVA usa campos com IDs JSF gerados
    # Tentamos múltiplos seletores por ordem de especificidade
    cpf_selectors = [
        'input[id*="cpf"]',
        'input[id*="Cpf"]',
        'input[id*="login"]',
        'input[name*="cpf"]',
        'input[type="text"]:first-of-type',
    ]
    senha_selectors = [
        'input[id*="senha"]',
        'input[id*="Senha"]',
        'input[type="password"]',
    ]

    cpf_field = None
    for sel in cpf_selectors:
        try:
            cpf_field = page.locator(sel).first
            await cpf_field.wait_for(state="visible", timeout=5_000)
            break
        except PlaywrightTimeout:
            cpf_field = None

    if cpf_field is None:
        raise CopelScraperError("Campo de CPF/CNPJ não encontrado na página de login.")

    await cpf_field.fill(cpf_cnpj)
    await _delay()

    senha_field = None
    for sel in senha_selectors:
        try:
            senha_field = page.locator(sel).first
            await senha_field.wait_for(state="visible", timeout=5_000)
            break
        except PlaywrightTimeout:
            senha_field = None

    if senha_field is None:
        raise CopelScraperError("Campo de senha não encontrado na página de login.")

    await senha_field.fill(senha)
    await _delay()

    # Submeter formulário — tenta botão visível ou Enter
    submit_selectors = [
        'button[id*="entrar"]',
        'button[id*="login"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a[id*="entrar"]',
    ]
    submitted = False
    for sel in submit_selectors:
        try:
            btn = page.locator(sel).first
            await btn.wait_for(state="visible", timeout=3_000)
            await btn.click()
            submitted = True
            break
        except PlaywrightTimeout:
            continue

    if not submitted:
        await senha_field.press("Enter")

    # Aguardar navegação pós-login
    try:
        await page.wait_for_url(re.compile(r"inicio|home|principal", re.IGNORECASE), timeout=TIMEOUT_NAV)
    except PlaywrightTimeout:
        # Verificar se há mensagem de erro de credenciais
        page_text = await page.inner_text("body")
        if any(msg in page_text.lower() for msg in ["senha incorreta", "inválid", "não encontrad", "bloqueada"]):
            raise CopelAuthError("Credenciais inválidas ou conta bloqueada.")
        raise CopelScraperError("Timeout aguardando página inicial após login.")


async def _navegar_para_faturas(page: Page) -> None:
    await _delay()

    # Copel AVA: menu "Contas" ou "Faturas" ou "2ª via"
    menu_selectors = [
        'a:has-text("2ª via")',
        'a:has-text("Segunda via")',
        'a:has-text("Fatura")',
        'a:has-text("Conta")',
        'a[id*="fatura"]',
        'a[id*="conta"]',
    ]
    for sel in menu_selectors:
        try:
            link = page.locator(sel).first
            await link.wait_for(state="visible", timeout=5_000)
            await link.click()
            await _delay()
            return
        except PlaywrightTimeout:
            continue

    raise CopelScraperError("Menu de faturas não encontrado. Layout do portal pode ter mudado.")


def _parse_competencia(competencia: Optional[str]) -> Optional[tuple[int, int]]:
    """Retorna (ano, mes) ou None para a mais recente."""
    if competencia is None:
        return None
    try:
        dt = datetime.strptime(competencia, "%Y-%m")
        return (dt.year, dt.month)
    except ValueError:
        raise CopelScraperError(f"Formato de competência inválido: '{competencia}'. Use YYYY-MM.")


async def _selecionar_e_baixar_pdf(
    page: Page, competencia: Optional[tuple[int, int]]
) -> bytes:
    await _delay()

    if competencia is not None:
        ano, mes = competencia
        # Tentar selecionar competência na lista/select disponível no portal
        meses_pt = [
            "janeiro", "fevereiro", "março", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
        ]
        mes_nome = meses_pt[mes - 1]
        competencia_texto = f"{mes_nome}/{ano}"

        # Seleciona no dropdown ou lista de competências
        select_found = False
        for sel in ['select[id*="competencia"]', 'select[id*="mes"]', 'select[id*="referencia"]']:
            try:
                select_el = page.locator(sel).first
                await select_el.wait_for(state="visible", timeout=5_000)
                # Tentar selecionar por valor YYYY-MM ou pelo texto
                try:
                    await select_el.select_option(value=f"{ano}-{mes:02d}")
                except Exception:
                    await select_el.select_option(label=re.compile(competencia_texto, re.IGNORECASE))
                select_found = True
                await _delay()
                break
            except (PlaywrightTimeout, Exception):
                continue

        if not select_found:
            # Tentar clicar em link/row da tabela de faturas com o mês/ano
            try:
                row = page.locator(f'tr:has-text("{mes_nome}"), a:has-text("{mes_nome}")').first
                await row.wait_for(state="visible", timeout=5_000)
                await row.click()
                await _delay()
            except PlaywrightTimeout:
                raise CopelFaturaNotFoundError(
                    f"Fatura de {competencia_texto} não encontrada no portal."
                )

    # Interceptar download do PDF
    download_selectors = [
        'a:has-text("PDF")',
        'a:has-text("Download")',
        'a:has-text("Baixar")',
        'a:has-text("Imprimir")',
        'button:has-text("PDF")',
        'a[href*=".pdf"]',
        'a[id*="pdf"]',
        'a[id*="imprimir"]',
        'a[id*="download"]',
        'a[id*="segunda"]',
        'a[id*="via"]',
    ]

    pdf_bytes: Optional[bytes] = None

    for sel in download_selectors:
        try:
            link = page.locator(sel).first
            await link.wait_for(state="visible", timeout=5_000)

            # Interceptar download
            async with page.expect_download(timeout=30_000) as dl_info:
                await link.click()
            download = await dl_info.value
            pdf_bytes = await download.read()

            if pdf_bytes and pdf_bytes[:4] == b"%PDF":
                return pdf_bytes

            # Se não veio como download, pode ter aberto nova aba com PDF
            pdf_bytes = None
        except (PlaywrightTimeout, Exception):
            continue

    # Tentar capturar nova aba com PDF aberta após clique
    if pdf_bytes is None:
        for sel in download_selectors:
            try:
                link = page.locator(sel).first
                await link.wait_for(state="visible", timeout=3_000)
                async with page.context.expect_page(timeout=15_000) as new_page_info:
                    await link.click()
                new_page = await new_page_info.value
                await new_page.wait_for_load_state("networkidle", timeout=20_000)
                pdf_bytes = await new_page.pdf() if new_page.url.endswith(".jsf") else None
                if pdf_bytes is None:
                    # Tentar ler conteúdo da URL como PDF
                    response = await new_page.goto(new_page.url, timeout=20_000)
                    if response:
                        body = await response.body()
                        if body[:4] == b"%PDF":
                            return body
                await new_page.close()
                break
            except (PlaywrightTimeout, Exception):
                continue

    if pdf_bytes is None:
        raise CopelFaturaNotFoundError("Não foi possível localizar ou baixar o PDF da fatura.")

    return pdf_bytes


async def baixar_fatura(cpf_cnpj: str, senha: str, competencia: Optional[str] = None) -> bytes:
    """
    Faz login no portal AVA da Copel e baixa a fatura PDF.

    Args:
        cpf_cnpj: CPF ou CNPJ do titular da conta.
        senha: Senha da Agência Virtual Copel.
        competencia: Mês de referência no formato "YYYY-MM". Se None, baixa a mais recente.

    Returns:
        Bytes do arquivo PDF da fatura.

    Raises:
        CopelAuthError: Credenciais inválidas.
        CopelFaturaNotFoundError: Fatura não encontrada para a competência solicitada.
        CopelScraperError: Falha genérica de navegação (mudança de layout, timeout, etc.).
    """
    competencia_parsed = _parse_competencia(competencia)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            accept_downloads=True,
        )
        page = await context.new_page()

        try:
            await _fazer_login(page, cpf_cnpj, senha)
            await _navegar_para_faturas(page)
            pdf_bytes = await _selecionar_e_baixar_pdf(page, competencia_parsed)
            return pdf_bytes
        finally:
            await context.close()
            await browser.close()
