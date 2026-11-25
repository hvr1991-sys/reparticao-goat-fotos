#!/usr/bin/env python3
"""Robô de fotos da Repartição GOAT (roda no GitHub Actions).

Fontes aceitas: site oficial / sala de imprensa do clube ou da liga e posts PÚBLICOS dos perfis
oficiais (Instagram, Facebook, X). Só o que é aberto ao público: nunca faz login nem contorna bloqueio.

Para cada pedido em jobs/<id>.json que ainda não tem fotos/<id>/meta.json:
  {"id": "<card>", "fotos": [{"url": "<imagem ou página do clube>", "credito": "...", "rotulo": "..."}]}

- Se a URL for uma página (HTML), usa a imagem principal declarada nela (og:image / twitter:image).
- Baixa só imagens (JPEG, PNG, WebP), até 25 MB, e salva em fotos/<id>/<n>.jpg|png.
- Não altera a foto: WebP vira PNG sem perda; JPEG e PNG são gravados como vieram.
- Registra em fotos/<id>/meta.json a origem, o tamanho em pixels e qualquer erro.
O designer confere cada foto (marca d'água, resolução) antes de usar.
"""
import io, json, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
JOBS, FOTOS = ROOT / "jobs", ROOT / "fotos"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
MAX = 25 * 1024 * 1024
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
RESTRICTED_HTTP = frozenset({401, 402, 403, 407, 429, 451})


class AcessoRestrito(ValueError):
    """A fonte negou ou limitou o acesso; não tentar outro cliente para contorná-la."""


def conferir_acesso(status):
    if status in RESTRICTED_HTTP:
        raise AcessoRestrito(f"Fonte respondeu HTTP {status}; usar outra fonte oficial autorizada")


def get(url, tentativas=3):
    headers = {
        "User-Agent": UA,
        "Accept": "image/avif,image/webp,image/*,text/html;q=0.9,*/*;q=0.5",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8,de;q=0.7",
        "Referer": "https://www.google.com/",
    }
    ultimo = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                data = r.read(MAX + 1)
                if len(data) > MAX:
                    raise ValueError("arquivo maior que 25 MB")
                return ctype, data, r.geturl()
        except urllib.error.HTTPError as e:
            conferir_acesso(e.code)
            ultimo = e
            if i + 1 < tentativas:
                time.sleep(3 * (i + 1))
        except ValueError:
            raise
        except Exception as e:  # tempo esgotado, conexão recusada etc.
            ultimo = e
            time.sleep(3 * (i + 1))
    raise ultimo


def og_image(html, base):
    for pat in (r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)'):
        m = re.search(pat, html, re.I)
        if m:
            return urllib.parse.urljoin(base, m.group(1).replace("&amp;", "&"))
    return None


_browser = None


def via_navegador(url):
    """Lê conteúdo público dependente de JavaScript; nunca supera negativa de acesso."""
    global _browser
    from playwright.sync_api import sync_playwright
    if _browser is None:
        pw = sync_playwright().start()
        exe = "/usr/bin/google-chrome" if Path("/usr/bin/google-chrome").exists() else None
        _browser = pw.chromium.launch(executable_path=exe, args=["--no-sandbox"]) if exe else pw.chromium.launch(args=["--no-sandbox"])
    ctx = _browser.new_context(user_agent=UA, locale="pt-BR", viewport={"width": 1366, "height": 900})
    try:
        page = ctx.new_page()
        resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if resp:
            conferir_acesso(resp.status)
            if resp.status >= 400:
                raise ValueError(f"página respondeu HTTP {resp.status}")
        ctype = (resp.headers.get("content-type", "") if resp else "").split(";")[0].lower()
        if ctype.startswith("image/"):
            body = resp.body()
            if len(body) > MAX:
                raise ValueError("arquivo maior que 25 MB")
            return ctype, body, page.url
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        img = page.evaluate("""() => {
          const m = document.querySelector('meta[property="og:image"],meta[property="og:image:secure_url"],meta[name="twitter:image"]');
          if (m && m.content) return new URL(m.content, location.href).href;
          let best = null, area = 0;
          for (const i of document.images) {
            const a = (i.naturalWidth || 0) * (i.naturalHeight || 0);
            if (i.naturalWidth >= 800 && a > area) { area = a; best = i.currentSrc || i.src; }
          }
          return best;
        }""")
        if not img:
            raise ValueError(f"página sem imagem principal (título: {page.title()[:80]})")
        r = ctx.request.get(img, headers={"Referer": page.url}, timeout=60000)
        conferir_acesso(r.status)
        if not r.ok:
            raise ValueError(f"imagem respondeu HTTP {r.status}")
        body = r.body()
        if len(body) > MAX:
            raise ValueError("arquivo maior que 25 MB")
        return (r.headers.get("content-type", "") or "").split(";")[0].lower(), body, img
    finally:
        ctx.close()


INSTA = re.compile(r"^https?://(www\.)?instagram\.com/(?:[A-Za-z0-9_.]+/)?(p|reel)/([A-Za-z0-9_-]+)")


def via_instagram_embed(url):
    """Post público do Instagram: usa a página de incorporação oficial (/embed/), que é aberta ao público.
    Se o post não for público ou pedir login, desiste — nunca contorna login."""
    m = INSTA.match(url)
    if not m:
        raise ValueError("não é post do Instagram")
    embed = f"https://www.instagram.com/{m.group(2)}/{m.group(3)}/embed/captioned/"
    ctype, data, final = get(embed)
    html = data.decode("utf-8", "ignore")
    if "login" in final:
        raise ValueError("Instagram pediu login (post não público)")
    cand = re.findall(r'class="EmbeddedMediaImage"[^>]*src="([^"]+)"', html) or re.findall(r'<img[^>]+src="(https://[^"]*(?:cdninstagram|fbcdn)[^"]+)"', html)
    if not cand:
        raise ValueError("Instagram não mostrou a imagem sem login")
    img = cand[0].replace("&amp;", "&")
    ctype, data, origem = get(img)
    return ctype, data, origem


def baixar(item, dest, n):
    url = item.get("url", "")
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL inválida")
    if INSTA.match(url):
        ctype, data, origem = via_instagram_embed(url)
        return salvar(item, url, dest, n, ctype, data, origem)
    try:
        ctype, data, final = get(url)
        origem = final
        if ctype.startswith("text/html"):
            img = og_image(data.decode("utf-8", "ignore"), final)
            if not img:
                raise ValueError("página sem imagem principal (og:image)")
            ctype, data, origem = get(img)
    except AcessoRestrito:
        raise
    except Exception as e1:
        try:
            ctype, data, origem = via_navegador(url)
        except Exception as e2:
            raise ValueError(f"robô simples: {e1} · navegador: {e2}")
    return salvar(item, url, dest, n, ctype, data, origem)


def salvar(item, url, dest, n, ctype, data, origem):
    im = Image.open(io.BytesIO(data))
    im.load()
    fmt = (im.format or "").upper()
    if fmt not in ("JPEG", "PNG", "WEBP"):
        raise ValueError(f"formato não suportado: {fmt or ctype}")
    w, h = im.size
    if fmt == "JPEG":
        path = dest / f"{n}.jpg"
        path.write_bytes(data)
    elif fmt == "PNG":
        path = dest / f"{n}.png"
        path.write_bytes(data)
    else:
        path = dest / f"{n}.png"
        im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB").save(path, "PNG")
    return {"arquivo": path.name, "largura": w, "altura": h, "url_imagem": origem, "pagina": url,
            "credito": item.get("credito", ""), "rotulo": item.get("rotulo", ""),
            "baixa_resolucao": max(w, h) < 1080}


def main():
    feitos = 0
    for job in sorted(JOBS.glob("*.json")):
        try:
            spec = json.loads(job.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"{job.name}: JSON inválido ({e})")
            continue
        jid = str(spec.get("id") or job.stem)
        if not SAFE_ID.match(jid):
            print(f"{job.name}: id inválido")
            continue
        dest = FOTOS / jid
        if (dest / "meta.json").exists():
            continue
        dest.mkdir(parents=True, exist_ok=True)
        resultados = []
        for n, item in enumerate(spec.get("fotos", [])[:6], start=1):
            try:
                resultados.append({"ok": True, **baixar(item, dest, n)})
            except Exception as e:
                resultados.append({"ok": False, "pagina": item.get("url", ""), "erro": str(e)[:300]})
        (dest / "meta.json").write_text(json.dumps({"id": jid, "fotos": resultados}, ensure_ascii=False, indent=2), encoding="utf-8")
        feitos += 1
        print(f"{jid}: {sum(r['ok'] for r in resultados)}/{len(resultados)} fotos")
    print(f"pedidos processados: {feitos}")


if __name__ == "__main__":
    sys.exit(main())
