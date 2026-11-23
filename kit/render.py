#!/usr/bin/env python3
"""Motor de artes do Canal GOAT (Repartição GOAT).

Monta as peças seguindo a skill canal-goat-artes e renderiza PNG em tamanho final
com Chrome (Playwright). Uso:

    python3 render.py spec.json saida.png

O spec.json define a peça ("tipo") e os dados. Tudo o que é texto entra como
tipografia real (nunca dentro da imagem). Fotos passam pelo preset
GOAT_SPORTS_EDITORIAL antes de entrar na arte e não são redesenhadas.

Tipos: agenda, jogo_unico, manchete, chamada, estatisticas.
"""
import base64, html, io, json, os, sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
Y = "#FFD318"          # amarelo oficial, sempre este
BLACK = "#08080A"
SURF1, SURF2 = "#121214", "#141416"
WHITE = "#F5F5F2"
MUTED = "rgba(245,245,242,0.62)"
W, H = 1080, 1350


def esc(s):
    return html.escape(str(s or ""))


def data_uri(path, mime):
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def fonts_css():
    f = KIT / "fonts"
    faces = [("BarlowCondensed-Regular.woff2", 400, "woff2"), ("BarlowCondensed-Medium.ttf", 500, "truetype"),
             ("BarlowCondensed-SemiBold.woff2", 600, "woff2"), ("BarlowCondensed-Bold.woff2", 700, "woff2")]
    out = []
    for name, wt, fmt in faces:
        mime = "font/woff2" if fmt == "woff2" else "font/ttf"
        out.append(f"@font-face{{font-family:'Barlow Condensed';font-weight:{wt};src:url({data_uri(f / name, mime)}) format('{fmt}');}}")
    return "\n".join(out)


def logo_tag(width, style=""):
    # Logo ou bodinho: nunca os dois. Por padrão, logo GOAT amarelo.
    return f'<img src="{data_uri(KIT / "brand" / "logo-goat-amarelo.png", "image/png")}" alt="" style="width:{width}px;{style}">'


def mark_tag(spec, width, style=""):
    if spec.get("marca") == "bodinho":
        p = KIT / "brand" / "bodinho.png"
        if not p.exists():
            raise SystemExit("bodinho.png não está no kit: envie o arquivo do bodinho ou use a marca 'logo'.")
        return f'<img src="{data_uri(p, "image/png")}" alt="" style="width:{width}px;{style}">'
    return logo_tag(width, style)


def editorial(photo_path):
    """Preset GOAT_SPORTS_EDITORIAL: ajuste global, igual para a foto inteira."""
    from PIL import Image, ImageEnhance
    import numpy as np
    im = Image.open(photo_path).convert("RGB")
    im = ImageEnhance.Contrast(im).enhance(1.075)
    im = ImageEnhance.Color(im).enhance(0.94)
    im = ImageEnhance.Sharpness(im).enhance(1.06)
    a = np.asarray(im).astype("float32") / 255.0
    lum = (0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2])[..., None]
    hi, sh = lum, 1.0 - lum
    a[..., 0:1] += 0.012 * hi - 0.006 * sh   # R: realces quentes, sombras frias
    a[..., 2:3] += -0.004 * hi + 0.010 * sh  # B
    im = Image.fromarray((a.clip(0, 1) * 255).astype("uint8"))
    w, h = im.size
    if max(w, h) < 900:
        print(f"AVISO: foto {photo_path} em baixa resolução ({w}x{h}). Peça uma versão maior.", file=sys.stderr)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def confronto(txt):
    # "TIME A X TIME B": o X fica amarelo
    parts = str(txt).upper().split(" X ")
    if len(parts) == 2:
        return f'{esc(parts[0])} <span style="color:{Y}">X</span> {esc(parts[1])}'
    return esc(str(txt).upper())


def ilustrativo(spec):
    if not spec.get("ilustrativo"):
        return ""
    return (f'<div style="position:absolute;top:22px;right:22px;border:2px solid {MUTED};color:{WHITE};'
            f'font:600 22px/1 \'Barlow Condensed\';letter-spacing:.12em;padding:8px 10px;z-index:9">DADOS ILUSTRATIVOS</div>')


def page(body, w=W, h=H):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{fonts_css()}
*{{box-sizing:border-box}}
html,body{{margin:0;width:{w}px;height:{h}px;overflow:hidden;background:{BLACK}}}
body{{font-family:'Barlow Condensed',sans-serif;color:{WHITE};-webkit-font-smoothing:antialiased}}
.art{{position:relative;width:{w}px;height:{h}px;overflow:hidden;background:{BLACK}}}
</style></head><body><div class="art">{body}</div></body></html>"""


# ---------------- peças ----------------

def agenda(spec):
    """Agenda do dia (feed 1080x1350), conforme a skill."""
    jogos = spec["jogos"]
    dia, resto = spec["data_dia_semana"].upper(), spec["data_resto"].upper()
    fundo = spec.get("fundo")
    if fundo:
        bg = f'<img src="{editorial(fundo)}" alt="" style="position:absolute;inset:-40px;width:calc(100% + 80px);height:calc(100% + 80px);object-fit:cover;filter:blur(18px) brightness(.28) saturate(.8)">'
    else:
        bg = ('<div style="position:absolute;inset:0;background:radial-gradient(ellipse 80% 45% at 50% 18%,rgba(255,255,255,.07),transparent 70%),'
              f'radial-gradient(ellipse 120% 60% at 50% 110%,rgba(255,211,24,.05),transparent 60%),{BLACK}"></div>')
    n = len(jogos)
    gap = 22
    card_h = 111
    total = n * card_h + (n - 1) * gap
    top_area, bottom_area = 330, H - 190  # entre a data e o logo
    y0 = top_area + max(0, ((bottom_area - top_area) - total) // 2)
    cards = []
    for i, j in enumerate(jogos):
        y = y0 + i * (card_h + gap)
        foto = j.get("foto")
        foto_html = ""
        if foto:
            foto_html = (f'<div style="position:absolute;right:0;top:0;bottom:0;width:42%;overflow:hidden;border-radius:0 16px 16px 0">'
                         f'<img src="{editorial(foto)}" alt="" style="width:100%;height:100%;object-fit:cover;object-position:{esc(j.get("foco","70% 25%"))}">'
                         f'<div style="position:absolute;inset:0;background:linear-gradient(90deg,{SURF2} 0%,rgba(20,20,22,.85) 18%,rgba(20,20,22,.35) 55%,rgba(20,20,22,0) 85%)"></div></div>')
        # título cabe inteiro: reduz a fonte em confrontos longos (sem reticências)
        limite = 17 if foto else 30
        n_chars = len(str(j.get("confronto", "")))
        tam = 38 if n_chars <= limite else max(26, int(38 * limite / n_chars))
        titulo = confronto(j["confronto"]) if " X " in str(j.get("confronto", "")).upper() else esc(str(j.get("confronto", "")).upper())
        cards.append(f"""
<div style="position:absolute;left:{(W-910)//2}px;top:{y}px;width:910px;height:{card_h}px;border-radius:16px;overflow:hidden;
 background:linear-gradient(180deg,{SURF2},{SURF1});box-shadow:inset 0 0 0 1px rgba(245,245,242,.06)">
 <div style="position:absolute;left:0;top:0;bottom:0;width:3px;background:{Y}"></div>
 {foto_html}
 <div style="position:absolute;left:34px;top:0;bottom:0;width:150px;display:flex;align-items:center;font:600 56px/1 'Barlow Condensed';color:{WHITE};text-transform:uppercase">{esc(j["horario"]).upper()}</div>
 <div style="position:absolute;left:190px;top:24px;bottom:24px;width:1px;background:rgba(245,245,242,.22)"></div>
 <div style="position:absolute;left:216px;right:{'40%' if foto else '30px'};top:0;bottom:0;display:flex;flex-direction:column;justify-content:center;gap:8px">
  <div style="font:600 19px/1 'Barlow Condensed';letter-spacing:.14em;color:{Y};text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(j["rotulo"])}</div>
  <div style="font:700 {tam}px/1 'Barlow Condensed';color:{WHITE};text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{titulo}</div>
 </div>
</div>""")
    body = f"""{bg}{ilustrativo(spec)}
<div style="position:absolute;top:118px;left:0;right:0;text-align:center;font:700 112px/1 'Barlow Condensed';letter-spacing:.01em">AGENDA <span style="font-weight:400">DO DIA</span></div>
<div style="position:absolute;top:248px;left:0;right:0;text-align:center;font:600 32px/1 'Barlow Condensed';letter-spacing:.12em;color:rgba(245,245,242,.78)"><span style="color:{Y}">{esc(dia)}</span> {esc(resto)}</div>
{''.join(cards)}
<div style="position:absolute;bottom:72px;left:0;right:0;display:flex;justify-content:center">{mark_tag(spec, 150)}</div>"""
    return page(body)


def jogo_unico(spec):
    foto = editorial(spec["foto"])
    body = f"""<img src="{foto}" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:{esc(spec.get('foco','50% 30%'))}">
<div style="position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.9) 0%,rgba(0,0,0,.75) 22%,rgba(0,0,0,0) 55%)"></div>
<div style="position:absolute;inset:0;background:linear-gradient(to bottom,rgba(0,0,0,.55),rgba(0,0,0,0) 18%)"></div>
{ilustrativo(spec)}
<div style="position:absolute;top:70px;left:0;right:0;text-align:center;font:600 30px/1 'Barlow Condensed';letter-spacing:.16em">AGENDA DO DIA</div>
<div style="position:absolute;top:112px;left:0;right:0;text-align:center;font:500 24px/1 'Barlow Condensed';letter-spacing:.14em;color:rgba(245,245,242,.78)"><span style="color:{Y}">{esc(spec['data_dia_semana'].upper())}</span> {esc(spec['data_resto'].upper())}</div>
<div style="position:absolute;left:64px;right:64px;bottom:230px;text-align:center;font:600 26px/1 'Barlow Condensed';letter-spacing:.16em;color:{Y};text-transform:uppercase">{esc(spec['campeonato'])}</div>
<div id="linha" style="position:absolute;left:64px;right:64px;bottom:140px;text-align:center;font:700 76px/1 'Barlow Condensed';text-transform:uppercase;white-space:nowrap">{esc(spec['horario']).upper()} <span style="color:rgba(245,245,242,.4)">|</span> {confronto(spec['confronto'])}</div>
<div style="position:absolute;bottom:56px;left:0;right:0;display:flex;justify-content:center">{mark_tag(spec, 130)}</div>
<script>const l=document.getElementById('linha');let s=76;while(l.scrollWidth>l.clientWidth&&s>36){{s-=2;l.style.fontSize=s+'px';}}</script>"""
    return page(body)


def _titulo_duas_cores(linhas):
    # linhas: [{"texto":..., "amarelo":bool}]
    return "".join(f'<div style="color:{Y if l.get("amarelo") else WHITE}">{esc(str(l["texto"]).upper())}</div>' for l in linhas)


def manchete(spec):
    foto = spec.get("foto")
    if foto:
        bg = (f'<img src="{editorial(foto)}" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:{esc(spec.get("foco","50% 25%"))}">'
              '<div style="position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.88) 0%,rgba(0,0,0,.8) 30%,rgba(0,0,0,0) 62%)"></div>')
    else:
        bg = '<div style="position:absolute;inset:0;background:#181818"></div>'
    sobre = f'<div style="font:400 34px/1 \'Barlow Condensed\';letter-spacing:.12em;color:rgba(255,255,255,.78);margin-bottom:22px;text-transform:uppercase">{esc(spec.get("sobretitulo",""))}</div>' if spec.get("sobretitulo") else ""
    apoio = f'<div style="font:400 40px/1.15 \'Barlow Condensed\';color:{WHITE};margin-top:26px">{spec_apoio(spec)}</div>' if spec.get("apoio") else ""
    size = spec.get("tamanho_titulo", 104)
    body = f"""{bg}{ilustrativo(spec)}
<div style="position:absolute;left:64px;right:64px;bottom:{'250' if foto else '420'}px;text-align:center">
{sobre}<div id="t" style="font:700 {size}px/.96 'Barlow Condensed'">{_titulo_duas_cores(spec['titulo'])}</div>{apoio}</div>
<div style="position:absolute;bottom:72px;left:0;right:0;display:flex;justify-content:center">{mark_tag(spec, 150)}</div>
<script>const t=document.getElementById('t');let s={size};while(t.scrollWidth>t.clientWidth&&s>48){{s-=2;t.style.fontSize=s+'px';}}</script>"""
    return page(body)


def spec_apoio(spec):
    # negrito só no dado: trechos entre ** viram 700
    txt = esc(spec.get("apoio", ""))
    parts = txt.split("**")
    return "".join(f"<b style='font-weight:700'>{p}</b>" if i % 2 else p for i, p in enumerate(parts))


def chamada(spec):
    foto = editorial(spec["foto"])
    body = f"""<img src="{foto}" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:{esc(spec.get('foco','50% 30%'))}">
<div style="position:absolute;inset:0;background:rgba(0,0,0,.55)"></div>
<div style="position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.88),rgba(0,0,0,0) 55%)"></div>
{ilustrativo(spec)}
<div style="position:absolute;top:64px;left:0;right:0;display:flex;justify-content:center">{mark_tag(spec, 150)}</div>
<div style="position:absolute;left:64px;right:64px;top:430px;text-align:center;font:700 92px/.98 'Barlow Condensed';text-transform:uppercase">{_titulo_duas_cores(spec['pergunta'])}</div>
<div style="position:absolute;left:64px;right:64px;bottom:250px;text-align:center;font:600 26px/1 'Barlow Condensed';letter-spacing:.16em;color:{Y};text-transform:uppercase">{esc(spec['campeonato'])}</div>
<div style="position:absolute;left:64px;right:64px;bottom:160px;text-align:center;font:700 64px/1 'Barlow Condensed';text-transform:uppercase">{confronto(spec['confronto'])}</div>
<div style="position:absolute;left:64px;right:64px;bottom:90px;text-align:center;font:600 40px/1 'Barlow Condensed';letter-spacing:.06em"><span style="color:{Y}">{esc(spec['data'])}</span> · {esc(spec['hora'])}</div>"""
    return page(body)


def estatisticas(spec):
    foto = spec.get("foto")
    bg = (f'<img src="{editorial(foto)}" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:{esc(spec.get("foco","50% 20%"))}">'
          '<div style="position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.92) 0%,rgba(0,0,0,.8) 38%,rgba(0,0,0,0) 70%)"></div>') if foto else '<div style="position:absolute;inset:0;background:#181818"></div>'
    nums = "".join(f'<div style="flex:1;text-align:center"><div style="font:700 110px/.9 \'Barlow Condensed\';color:{Y}">{esc(n["valor"])}</div>'
                   f'<div style="margin-top:16px;font:500 32px/1.05 \'Barlow Condensed\';text-transform:uppercase">{esc(n["rotulo"])}</div></div>' for n in spec["numeros"])
    body = f"""{bg}{ilustrativo(spec)}
<div style="position:absolute;left:64px;right:64px;bottom:440px;text-align:center">
<div style="font:400 34px/1 'Barlow Condensed';letter-spacing:.12em;color:rgba(255,255,255,.78);margin-bottom:16px;text-transform:uppercase">{esc(spec.get('sobretitulo',''))}</div>
<div style="font:700 96px/.96 'Barlow Condensed';text-transform:uppercase">{_titulo_duas_cores(spec['titulo'])}</div></div>
<div style="position:absolute;left:64px;right:64px;bottom:200px;display:flex;gap:32px">{nums}</div>
<div style="position:absolute;bottom:72px;left:0;right:0;display:flex;justify-content:center">{mark_tag(spec, 150)}</div>"""
    return page(body)


TIPOS = {"agenda": agenda, "jogo_unico": jogo_unico, "manchete": manchete, "chamada": chamada, "estatisticas": estatisticas}


def render(spec, out_path):
    from playwright.sync_api import sync_playwright
    tipo = spec.get("tipo")
    if tipo not in TIPOS:
        raise SystemExit(f"tipo inválido: {tipo}. Use: {', '.join(TIPOS)}")
    doc = TIPOS[tipo](spec)
    with sync_playwright() as p:
        exe = "/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None
        b = p.chromium.launch(executable_path=exe, args=["--no-sandbox"]) if exe else p.chromium.launch(args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.set_content(doc, wait_until="load")
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(150)
        pg.screenshot(path=out_path, clip={"x": 0, "y": 0, "width": W, "height": H})
        b.close()
    print(out_path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("uso: python3 render.py spec.json saida.png")
    render(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")), sys.argv[2])
