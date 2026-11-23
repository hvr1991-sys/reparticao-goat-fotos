#!/usr/bin/env python3
"""Robô de fotos da Repartição GOAT (roda no GitHub Actions).

Para cada pedido em jobs/<id>.json que ainda não tem fotos/<id>/meta.json:
  {"id": "<card>", "fotos": [{"url": "<imagem ou página do clube>", "credito": "...", "rotulo": "..."}]}

- Se a URL for uma página (HTML), usa a imagem principal declarada nela (og:image / twitter:image).
- Baixa só imagens (JPEG, PNG, WebP), até 25 MB, e salva em fotos/<id>/<n>.jpg|png.
- Não altera a foto: WebP vira PNG sem perda; JPEG e PNG são gravados como vieram.
- Registra em fotos/<id>/meta.json a origem, o tamanho em pixels e qualquer erro.
O designer confere cada foto (marca d'água, resolução) antes de usar.
"""
import io, json, re, sys, urllib.parse, urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
JOBS, FOTOS = ROOT / "jobs", ROOT / "fotos"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
MAX = 25 * 1024 * 1024
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,text/html;q=0.8,*/*;q=0.5"})
    with urllib.request.urlopen(req, timeout=40) as r:
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        data = r.read(MAX + 1)
        if len(data) > MAX:
            raise ValueError("arquivo maior que 25 MB")
        return ctype, data, r.geturl()


def og_image(html, base):
    for pat in (r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)'):
        m = re.search(pat, html, re.I)
        if m:
            return urllib.parse.urljoin(base, m.group(1).replace("&amp;", "&"))
    return None


def baixar(item, dest, n):
    url = item.get("url", "")
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL inválida")
    ctype, data, final = get(url)
    origem = final
    if ctype.startswith("text/html"):
        img = og_image(data.decode("utf-8", "ignore"), final)
        if not img:
            raise ValueError("página sem imagem principal (og:image)")
        ctype, data, origem = get(img)
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
