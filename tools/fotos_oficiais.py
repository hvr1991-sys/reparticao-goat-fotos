#!/usr/bin/env python3
"""Busca limitada a sites oficiais conhecidos, sem descoberta de URLs por IA.

As páginas precisam pertencer a um clube/liga da lista revisada. Cada nova foto
é baixada isoladamente, conserva a origem e ainda precisa de revisão visual.
"""
import json, re, sys, urllib.parse
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import baixar  # noqa: E402
from photo_policy import official_origin, biblioteca_verified  # noqa: E402

CACHE = ROOT / "tools" / "clubes.json"
NOTICIA = re.compile(r"/(news|noticias|noticia|aktuelles|aktuell|artikel|article|articles|media|spielberichte|match|matches|post|posts|blog|en/news|ar/news)/", re.I)


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _cache():
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


KNOWN_SITES = {
    "hertha": "https://www.herthabsc.com/de", "hertha-berlim": "https://www.herthabsc.com/de",
    "karlsruher": "https://www.ksc.de", "karlsruher-sc": "https://www.ksc.de",
    "paderborn": "https://www.scp07.de", "schalke": "https://schalke04.de", "schalke-04": "https://schalke04.de",
    "palmeiras": "https://www.palmeiras.com.br", "internacional": "https://internacional.com.br",
    "atletico-go": "https://atleticogoianiense.com.br", "atletico-goianiense": "https://atleticogoianiense.com.br",
    "colonia": "https://fc.de", "fc-koln": "https://fc.de", "bayern": "https://fcbayern.com",
    "bayern-de-munique": "https://fcbayern.com", "borussia-dortmund": "https://www.bvb.de",
    "wolfsburg": "https://www.vfl-wolfsburg.de", "freiburg": "https://www.scfreiburg.com",
    "union-berlin": "https://www.fc-union-berlin.de", "union-berlim": "https://www.fc-union-berlin.de",
    "estudiantes": "https://estudiantesdelaplata.com", "al-ittihad": "https://www.ittihadclub.sa",
    "al-qadsiah": "https://alqadsiah.com", "neom": "https://www.neom.com/en-us/neom-sports-club/",
}


def _same_origin(a, b):
    return (urllib.parse.urlparse(a).hostname or "").removeprefix("www.") == (urllib.parse.urlparse(b).hostname or "").removeprefix("www.")


def site_oficial(time, campeonato):
    """Usa apenas a relação clube→site revisada; abrir um URL não verifica sua autoria."""
    chave = _norm(time)
    known = KNOWN_SITES.get(chave)
    if not known:
        return None
    cached = _cache().get(chave, {}).get("site")
    if cached and official_origin(cached) and _same_origin(cached, known):
        return cached
    return known if official_origin(known) else None


def _html_navegador(url):
    """Sites que montam a página com JavaScript: abre num Chrome de verdade e pega o HTML pronto."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        exe = "/usr/bin/google-chrome" if Path("/usr/bin/google-chrome").exists() else None
        b = pw.chromium.launch(executable_path=exe, args=["--no-sandbox"]) if exe else pw.chromium.launch(args=["--no-sandbox"])
        try:
            pg = b.new_page(user_agent=baixar.UA, locale="pt-BR")
            pg.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                pg.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            return pg.content(), pg.url
        finally:
            b.close()


def noticias(site, n=4):
    if not official_origin(site):
        return []
    try:
        ctype, data, final = baixar.get(site, tentativas=2)
        html = data.decode("utf-8", errors="ignore") if "html" in ctype else ""
    except Exception as e:
        print(f"  {site}: não abriu direto ({str(e)[:80]})", file=sys.stderr, flush=True)
        html, final = "", site
    links = _links(html, final, n) if official_origin(final) and _same_origin(site, final) else []
    if len(links) < 2:
        try:
            html, final = _html_navegador(site)
            links = _links(html, final, n) if official_origin(final) and _same_origin(site, final) else []
        except Exception as e:
            print(f"  {site}: navegador falhou ({str(e)[:80]})", file=sys.stderr, flush=True)
    return links


def _links(html, final, n):
    if not official_origin(final):
        return []
    dominio = urllib.parse.urlparse(final).netloc.replace("www.", "")
    links = []
    for href in re.findall(r'href=["\']([^"\'#]+)["\']', html):
        url = urllib.parse.urljoin(final, href.replace("&amp;", "&"))
        p = urllib.parse.urlparse(url)
        if not official_origin(url) or p.netloc.replace("www.", "") != dominio or not NOTICIA.search(p.path) or len(p.path) < 18:
            continue
        if url not in links:
            links.append(url)
    return links[:n]


def buscar(time, campeonato, rotulo):
    """Baixa só as candidatas desta chamada; não executa outros pedidos da fila."""
    site = site_oficial(time, campeonato)
    if not site:
        return []
    paginas = noticias(site)
    if not paginas:
        return []
    pasta = f"oficial-{_norm(time)[:40]}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    credito = urllib.parse.urlparse(site).netloc.replace("www.", "")
    dest = ROOT / "fotos" / pasta
    dest.mkdir(parents=True, exist_ok=True)
    resultados = []
    for index, url in enumerate(paginas[:4], 1):
        if not official_origin(url) or not _same_origin(site, url):
            continue
        item = {"url": url, "credito": f"{time} (site oficial · {credito})", "rotulo": rotulo}
        try:
            resultados.append({"ok": True, **baixar.baixar(item, dest, index)})
        except Exception:
            resultados.append({"ok": False, "pagina": url, "erro": "Foto indisponível na fonte oficial"})
    (dest / "meta.json").write_text(json.dumps({"id": pasta, "fotos": resultados}, ensure_ascii=False, indent=2), encoding="utf-8")
    return [f["arquivo"] for f in biblioteca_verified(ROOT) if f["arquivo"].startswith(f"fotos/{pasta}/")]
