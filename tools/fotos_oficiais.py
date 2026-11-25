#!/usr/bin/env python3
"""Busca fotos novas no SITE OFICIAL do clube, sem busca paga.

1. Descobre o site oficial do clube (cache em tools/clubes.json; o Gemini sugere e o robô confere se abre).
2. Abre a página inicial e as notícias mais recentes do próprio site (mesmo domínio).
3. Baixa a imagem principal de cada notícia (og:image) com tools/baixar.py para fotos/<pasta>/.
As fotos entram na biblioteca com o nome do clube no rótulo e o crédito do site oficial;
quem escolhe qual serve é o Gemini, olhando a imagem (tools/agenda.py).
"""
import json, re, subprocess, sys, urllib.parse
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import baixar  # noqa: E402

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


def site_oficial(time, campeonato):
    cache = _cache()
    chave = _norm(time)
    if chave in cache:
        return cache[chave].get("site")
    site = None
    try:
        import gemini
        r = gemini.json_de(gemini.gerar([{"text": f"""Qual é o site OFICIAL do clube de futebol "{time}" (competição: {campeonato})?
Só o domínio oficial do próprio clube (não Wikipedia, não portal de notícias, não loja).
Responda só ```json {{"site": "https://..."}}``` ou {{"site": null}} se não tiver certeza."""}], temp=0.0))
        site = r.get("site")
        if site:
            _, _, final = baixar.get(site, tentativas=2)
            site = final or site
    except Exception as e:
        print(f"  site oficial de {time}: não achei ({str(e)[:80]})", file=sys.stderr, flush=True)
        site = None
    cache[chave] = {"time": time, "site": site, "conferido": datetime.utcnow().date().isoformat()}
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return site


def noticias(site, n=6):
    try:
        ctype, data, final = baixar.get(site, tentativas=2)
    except Exception as e:
        print(f"  {site}: não abriu ({str(e)[:80]})", file=sys.stderr, flush=True)
        return []
    if "html" not in ctype:
        return []
    html = data.decode("utf-8", errors="ignore")
    dominio = urllib.parse.urlparse(final).netloc.replace("www.", "")
    links = []
    for href in re.findall(r'href=["\']([^"\'#]+)["\']', html):
        url = urllib.parse.urljoin(final, href.replace("&amp;", "&"))
        p = urllib.parse.urlparse(url)
        if p.netloc.replace("www.", "") != dominio or not NOTICIA.search(p.path) or len(p.path) < 18:
            continue
        if url not in links:
            links.append(url)
    return links[:n]


def buscar(time, campeonato, rotulo):
    """Baixa até 6 fotos novas do site oficial do clube. Devolve os caminhos (fotos/<pasta>/<n>.ext)."""
    site = site_oficial(time, campeonato)
    if not site:
        return []
    paginas = noticias(site)
    print(f"  {time}: site {site} · {len(paginas)} notícias", file=sys.stderr, flush=True)
    if not paginas:
        paginas = [site]
    pasta = f"oficial-{_norm(time)[:40]}-{datetime.utcnow().strftime('%Y%m%d%H%M')}"
    credito = urllib.parse.urlparse(site).netloc.replace("www.", "")
    (ROOT / "jobs").mkdir(exist_ok=True)
    (ROOT / "jobs" / f"{pasta}.json").write_text(json.dumps({"id": pasta, "fotos": [
        {"url": u, "credito": f"{time} (site oficial · {credito})", "rotulo": rotulo} for u in paginas]}, ensure_ascii=False), encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "tools" / "baixar.py")], check=False, capture_output=True)
    meta = ROOT / "fotos" / pasta / "meta.json"
    if not meta.exists():
        return []
    m = json.loads(meta.read_text(encoding="utf-8"))
    return [f"fotos/{pasta}/{f['arquivo']}" for f in m.get("fotos", []) if f.get("ok") and not f.get("baixa_resolucao")]
