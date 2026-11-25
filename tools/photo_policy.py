"""Origens oficiais e integridade das fotos usadas pela Repartição.

Uma URL que abre não prova origem oficial. A lista abaixo é explícita e corresponde
às fontes de clubes/ligas presentes no acervo do projeto. CDNs, portais e agências
não são aceitos como página de origem. Uma foto ainda exige revisão visual.
"""
from pathlib import Path
from urllib.parse import urlparse
import hashlib
import json
import re
import unicodedata

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_DOMAINS = frozenset({
    "spl.com.sa", "ksc.de", "herthabsc.com", "palmeiras.com.br", "cbf.com.br",
    "sv07elversberg.de", "schalke04.de", "vfl-wolfsburg.de", "bvb.de",
    "ittihadclub.sa", "atleticogoianiense.com.br", "fc.de", "scfreiburg.com",
    "bundesliga.com", "internacional.com.br", "estudiantesdelaplata.com",
    "fc-union-berlin.de", "alqadsiah.com", "borussia.de", "the-afc.com",
    "scp07.de", "fcbayern.com", "rbleipzig.com", "concacaf.com",
})
AGENCIES = re.compile(r"getty|reuters|alamy|shutterstock|apimages|afp(?:\.com|\s|$)", re.I)


def official_origin(url):
    try:
        parsed = urlparse(str(url))
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        if host in ("neom.com", "www.neom.com"):
            return "/neom-sports-club/" in parsed.path
        return any(host == domain or host == "www." + domain for domain in OFFICIAL_DOMAINS)
    except ValueError:
        return False


def photo_digest(path):
    with Path(path).open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256")
    return digest.hexdigest()


def _norm(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def biblioteca_verified(root=ROOT):
    """Fotos locais com origem oficial, resolução real e hash único; nunca aprovação visual."""
    root = Path(root).resolve()
    photo_root = (root / "fotos").resolve()
    photos, seen = [], set()
    for meta in sorted(photo_root.glob("*/meta.json")):
        try:
            entries = json.loads(meta.read_text(encoding="utf-8")).get("fotos", [])
        except (OSError, ValueError, AttributeError):
            continue
        for item in entries:
            if not isinstance(item, dict) or item.get("ok") is not True or item.get("baixa_resolucao") is True:
                continue
            page, credit = item.get("pagina", ""), item.get("credito", "")
            if not official_origin(page) or not str(credit).strip() or AGENCIES.search(str(page) + " " + str(credit) + " " + str(item.get("url_imagem", ""))):
                continue
            path = (meta.parent / str(item.get("arquivo", ""))).resolve()
            if not path.is_relative_to(photo_root) or not path.is_file() or path.stat().st_size > 25 * 1024 * 1024:
                continue
            if item.get("marca_dagua") is True or item.get("watermark") is True:
                continue
            try:
                with Image.open(path) as image:
                    width, height = image.size
                    if image.format not in ("PNG", "JPEG", "WEBP") or max(width, height) < 1080 or min(width, height) < 360:
                        continue
                    image.verify()
                sha = photo_digest(path)
            except (OSError, ValueError, Image.DecompressionBombError):
                continue
            if sha in seen:
                continue
            seen.add(sha)
            text = "-".join(_norm(item.get(key, "")) for key in ("rotulo", "pagina", "credito"))
            photos.append({"arquivo": path.relative_to(root).as_posix(), "texto": text,
                           "largura": width, "altura": height, "sha256": sha, "pagina": page,
                           "credito": credit, "url_imagem": item.get("url_imagem", ""),
                           "rotulo": item.get("rotulo", "")})
    return photos
