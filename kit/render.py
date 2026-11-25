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
import base64, html, io, json, os, re, sys
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


FONT = "GOAT Sans"  # Barlow Condensed em todas as artes (padrão dos modelos do Gestor)


def fonts_css():
    f = KIT / "fonts"
    faces = [("BarlowCondensed-Regular.woff2", (300, 400), "woff2"), ("BarlowCondensed-Medium.ttf", (500,), "truetype"),
             ("BarlowCondensed-SemiBold.woff2", (600,), "woff2"), ("BarlowCondensed-Bold.woff2", (700, 800), "woff2")]
    out = []
    for name, pesos, fmt in faces:
        mime = "font/woff2" if fmt == "woff2" else "font/ttf"
        uri = data_uri(f / name, mime)
        for wt in pesos:
            out.append(f"@font-face{{font-family:'{FONT}';font-weight:{wt};src:url({uri}) format('{fmt}');}}")
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
            f'font:600 22px/1 \'GOAT Sans\';letter-spacing:.06em;padding:8px 10px;z-index:9">DADOS ILUSTRATIVOS</div>')


def page(body, w=W, h=H):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{fonts_css()}
*{{box-sizing:border-box}}
html,body{{margin:0;width:{w}px;height:{h}px;overflow:hidden;background:{BLACK}}}
body{{font-family:'GOAT Sans',sans-serif;color:{WHITE};-webkit-font-smoothing:antialiased}}
.art{{position:relative;width:{w}px;height:{h}px;overflow:hidden;background:{BLACK}}}
</style></head><body><div class="art">{body}</div>
<script>document.fonts.ready.then(()=>new Promise(r=>setTimeout(r,30))).then(()=>{{for(const el of document.querySelectorAll('.art div')){{const cs=getComputedStyle(el);if(cs.whiteSpace!=='nowrap'&&!el.classList.contains('fit'))continue;let s=parseFloat(cs.fontSize);while(el.scrollWidth>el.clientWidth+1&&s>14){{s-=1;el.style.fontSize=s+'px';}}}}document.body.dataset.ok=1;}});</script></body></html>"""


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
    # informações da transmissão 50% maiores (pedido do Gestor); com muitos jogos, tudo encolhe junto para caber
    top_area, bottom_area = 320, H - 180  # entre a data e o logo
    gap = 20
    k = min(1.0, ((bottom_area - top_area) - (n - 1) * gap) / (n * 111)) if n else 1.0
    card_h = int(111 * k)
    # horário no tamanho de sempre; rótulo e confronto maiores, com espaço para a foto à direita
    f_hora, f_rot, f_tit = int(46 * max(k, .8)), int(24 * k), int(41 * k)
    total = n * card_h + (n - 1) * gap
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
        conf = str(j.get("confronto", "")).upper()
        estilo = f"font:700 {f_tit}px/1.04 'GOAT Sans';color:{WHITE};text-transform:uppercase;white-space:nowrap;overflow:hidden"
        if foto and " X " in conf:
            # com foto: um time por linha ("TIME A X" / "TIME B"), sem cortar nem reticências
            a_, b_ = conf.split(" X ", 1)
            tit_html = (f'<div style="{estilo}">{esc(a_)} <span style="color:{Y}">X</span></div>'
                        f'<div style="{estilo}">{esc(b_)}</div>')
        else:
            tit_html = f'<div style="{estilo}">{confronto(conf) if " X " in conf else esc(conf)}</div>'
        cards.append(f"""
<div style="position:absolute;left:{(W-910)//2}px;top:{y}px;width:910px;height:{card_h}px;border-radius:16px;overflow:hidden;
 background:linear-gradient(180deg,{SURF2},{SURF1});box-shadow:inset 0 0 0 1px rgba(245,245,242,.06)">
 <div style="position:absolute;left:0;top:0;bottom:0;width:3px;background:{Y}"></div>
 {foto_html}
 <div style="position:absolute;left:30px;top:0;bottom:0;width:{int(150*k)}px;display:flex;align-items:center;font:600 {f_hora}px/1 'GOAT Sans';color:{WHITE};text-transform:uppercase;white-space:nowrap">{esc(j["horario"]).upper()}</div>
 <div style="position:absolute;left:{int(30+160*k)}px;top:{int(28*k)}px;bottom:{int(28*k)}px;width:1px;background:rgba(245,245,242,.22)"></div>
 <div style="position:absolute;left:{int(30+160*k)+24}px;right:{'42%' if foto else '30px'};top:0;bottom:0;display:flex;flex-direction:column;justify-content:center;gap:{int(6*k)}px">
  <div style="font:600 {f_rot}px/1.05 'GOAT Sans';letter-spacing:.04em;color:{Y};text-transform:uppercase;white-space:nowrap;overflow:hidden">{esc(j["rotulo"])}</div>
  {tit_html}
 </div>
</div>""")
    body = f"""{bg}{ilustrativo(spec)}
<div style="position:absolute;top:118px;left:0;right:0;text-align:center;font:700 96px/1 'GOAT Sans';letter-spacing:.01em">AGENDA <span style="font-weight:300">DO DIA</span></div>
<div style="position:absolute;top:248px;left:0;right:0;text-align:center;font:600 32px/1 'GOAT Sans';letter-spacing:.06em;color:rgba(245,245,242,.78)"><span style="color:{Y}">{esc(dia)}</span> {esc(resto)}</div>
{''.join(cards)}
<div style="position:absolute;bottom:72px;left:0;right:0;display:flex;justify-content:center">{mark_tag(spec, 150)}</div>"""
    return page(body)


def jogo_unico(spec):
    """Agenda de jogo único — segue o modelo do Gestor (modelos/jogo-unico/MODELO_AGENDA_JOGO_UNICO_2.png):
    foto inteira escurecida; topo: "AGENDA DO DIA" à esquerda e a data espaçada à direita;
    base: campeonato espaçado e, logo abaixo, "21H | TIME A X TIME B" grande (hora e X em amarelo); logo centralizado."""
    foto = editorial(spec["foto"])
    data_txt = esc(str(spec.get("data_resto") or spec.get("data") or "").upper())
    body = f"""<img src="{foto}" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:{esc(spec.get('foco','50% 30%'))};filter:brightness(.78)">
<div style="position:absolute;inset:0;background:linear-gradient(to bottom,rgba(0,0,0,.45) 0%,rgba(0,0,0,0) 16%,rgba(0,0,0,0) 52%,rgba(0,0,0,.72) 70%,rgba(0,0,0,.97) 86%,#000 100%)"></div>
{ilustrativo(spec)}
<div style="position:absolute;top:56px;left:54px;font:700 40px/1 'GOAT Sans';text-transform:uppercase;white-space:nowrap">AGENDA <span style="font-weight:400">DO DIA</span></div>
<div style="position:absolute;top:62px;right:24px;font:600 30px/1 'GOAT Sans';letter-spacing:.3em;color:rgba(245,245,242,.85);text-transform:uppercase;white-space:nowrap">{data_txt}</div>
<div style="position:absolute;left:0;right:0;top:{982 - int(spec.get('deslocar_y', 0) or 0)}px;text-align:center">
 <div id="bloco" style="display:inline-block;text-align:left;max-width:960px">
  <div style="font:500 28px/1 'GOAT Sans';letter-spacing:.3em;color:rgba(245,245,242,.82);text-transform:uppercase;white-space:nowrap;margin-bottom:22px">{esc(spec['campeonato'])}</div>
  <div id="linha" style="font:600 {int(spec.get('tamanho_titulo', 136) or 136)}px/1 'GOAT Sans';text-transform:uppercase;white-space:nowrap;letter-spacing:-.01em"><span style="color:{Y}">{esc(spec['horario']).upper()}</span> <span style="font-weight:500;color:{WHITE}">|</span> {confronto(spec['confronto'])}</div>
 </div>
</div>
<div style="position:absolute;top:1180px;left:0;right:0;display:flex;justify-content:center">{mark_tag(spec, 140)}</div>
<script>document.fonts.ready.then(()=>{{const l=document.getElementById('linha');let s={int(spec.get('tamanho_titulo', 136) or 136)};while(l.scrollWidth>960&&s>44){{s-=2;l.style.fontSize=s+'px';}}}});</script>"""
    return page(body)

def _alinhamento(spec):
    a = str(spec.get("alinhamento", "centro")).lower()
    return {"esquerda": "left", "direita": "right"}.get(a, "center")


def _degrade_lateral(al):
    """Com título na lateral, um degradê lateral suave garante a leitura sem cobrir o rosto."""
    if al == "left":
        return '<div style="position:absolute;inset:0;background:linear-gradient(90deg,rgba(0,0,0,.88) 0%,rgba(0,0,0,.62) 34%,rgba(0,0,0,0) 66%)"></div>'
    if al == "right":
        return '<div style="position:absolute;inset:0;background:linear-gradient(270deg,rgba(0,0,0,.88) 0%,rgba(0,0,0,.62) 34%,rgba(0,0,0,0) 66%)"></div>'
    return ""


def _rodape_jogo(spec):
    """Informações do jogo SEMPRE no rodapé e com destaque: campeonato, confronto e dia/hora."""
    j = spec.get("jogo")
    if not j:
        return ""
    quando = " · ".join(x for x in [esc(str(j.get("data", "")).upper()), esc(str(j.get("hora", "")).upper())] if x)
    return f"""
<div style="position:absolute;left:0;right:0;bottom:0;height:330px;background:linear-gradient(to top,rgba(0,0,0,.96) 0%,rgba(0,0,0,.85) 55%,rgba(0,0,0,0) 100%)"></div>
<div style="position:absolute;left:64px;right:64px;bottom:178px;text-align:center;font:600 26px/1 'GOAT Sans';letter-spacing:.1em;color:{Y};text-transform:uppercase;white-space:nowrap">{esc(j.get('campeonato',''))}</div>
<div style="position:absolute;left:64px;right:64px;bottom:112px;text-align:center;font:700 56px/1 'GOAT Sans';text-transform:uppercase;white-space:nowrap">{confronto(j.get('confronto',''))}</div>
<div style="position:absolute;left:64px;right:64px;bottom:62px;text-align:center;font:600 34px/1 'GOAT Sans';letter-spacing:.04em;white-space:nowrap"><span style="color:{Y}">{quando}</span></div>"""


def _marca_canto(spec, al):
    """Com rodapé de jogo, a marca sobe para o topo (lado oposto ao título quando lateral)."""
    lado = "right:56px" if al == "left" else ("left:56px" if al == "right" else "left:0;right:0;display:flex;justify-content:center")
    return f'<div style="position:absolute;top:56px;{lado}">{mark_tag(spec, 130)}</div>'


def _titulo_duas_cores(linhas):
    # linhas: [{"texto":..., "amarelo":bool}]
    if isinstance(linhas, str):
        linhas = [{"texto": linhas}]
    return "".join(f'<div style="color:{Y if l.get("amarelo") else WHITE};white-space:nowrap">{esc(str(l["texto"]).upper())}</div>' for l in linhas)


def _linha_jogo(j, tam=64):
    """Mesma linha do modelo de jogo único: 'SÁB 28.11 · 11H30 | TIME A X TIME B' (data/hora e X em amarelo)."""
    quando = " · ".join(x for x in [str(j.get("data", "")).upper(), str(j.get("hora", "")).upper()] if x)
    sep = f' <span style="font-weight:500;color:{WHITE}">|</span> ' if quando else ""
    return (f'<div style="font:500 26px/1 \'GOAT Sans\';letter-spacing:.28em;color:rgba(245,245,242,.82);text-transform:uppercase;white-space:nowrap;margin-bottom:16px">{esc(j.get("campeonato",""))}</div>'
            f'<div class="fit" style="font:600 {tam}px/1 \'GOAT Sans\';text-transform:uppercase;white-space:nowrap"><span style="color:{Y}">{esc(quando)}</span>{sep}{confronto(j.get("confronto",""))}</div>')


def _post(spec, meio=""):
    """Layout único dos posts do feed (manchete, chamada, estatísticas), no espírito do modelo de jogo único:
    foto inteira; tudo empilhado e ancorado na BASE (nunca no meio da foto, nunca sobre rostos):
    sobretítulo → título curto grande → apoio → [meio: números] → linha do jogo em destaque. Marca pequena no topo."""
    foto = spec.get("foto")
    al = _alinhamento(spec)
    if foto:
        bg = (f'<img src="{editorial(foto)}" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:{esc(spec.get("foco","50% 25%"))};filter:brightness(.85)">'
              '<div style="position:absolute;inset:0;background:linear-gradient(to bottom,rgba(0,0,0,.45) 0%,rgba(0,0,0,0) 14%,rgba(0,0,0,0) 40%,rgba(0,0,0,.78) 60%,rgba(0,0,0,.96) 78%,#000 100%)"></div>'
              + (_degrade_lateral(al) if al != "center" else ""))
    else:
        bg = f'<div style="position:absolute;inset:0;background:radial-gradient(ellipse 90% 60% at 50% 30%,#1c1c1f,{BLACK} 70%)"></div>'
    j = spec.get("jogo")
    sobre = f'<div style="font:600 30px/1 \'GOAT Sans\';letter-spacing:.2em;color:{Y};text-transform:uppercase;white-space:nowrap;margin-bottom:18px">{esc(spec.get("sobretitulo",""))}</div>' if spec.get("sobretitulo") else ""
    size = spec.get("tamanho_titulo", 122)
    titulo = f'<div class="fit" style="font:700 {size}px/.95 \'GOAT Sans\';text-transform:uppercase">{_titulo_duas_cores(spec["titulo"])}</div>'
    apoio = f'<div class="fit" style="font:500 38px/1.15 \'GOAT Sans\';color:rgba(245,245,242,.92);margin-top:16px;white-space:nowrap">{spec_apoio(spec)}</div>' if spec.get("apoio") else ""
    jogo = f'<div style="margin-top:22px;padding-top:18px;border-top:2px solid rgba(255,211,24,.55)">{_linha_jogo(j)}</div>' if j else ""
    largura = "max-width:960px" if al == "center" else "width:900px"
    lado = {"center": "left:0;right:0;text-align:center", "left": "left:60px;text-align:left", "right": "right:60px;text-align:right"}[al]
    body = f"""{bg}{ilustrativo(spec)}
<div style="position:absolute;top:52px;{'left:0;right:0;display:flex;justify-content:center' if al=='center' else ('right:56px' if al=='left' else 'left:56px')}">{mark_tag(spec, 130)}</div>
<div style="position:absolute;bottom:{70 + int(spec.get("deslocar_y", 0) or 0)}px;{lado}">
 <div style="display:inline-block;{largura};text-align:{al}">{sobre}{titulo}{apoio}{meio}{jogo}</div>
</div>"""
    return page(body)


def manchete(spec):
    return _post(spec)


def spec_apoio(spec):
    # negrito só no dado: trechos entre ** viram 700
    txt = esc(spec.get("apoio", ""))
    parts = txt.split("**")
    return "".join(f"<b style='font-weight:700'>{p}</b>" if i % 2 else p for i, p in enumerate(parts))


def chamada(spec):
    """Chamada para interação/jogo: título curto (pergunta) + linha do jogo no rodapé."""
    s2 = dict(spec)
    s2.setdefault("titulo", spec.get("pergunta", []))
    if not s2.get("jogo") and spec.get("confronto"):
        s2["jogo"] = {"campeonato": spec.get("campeonato", ""), "confronto": spec["confronto"], "data": spec.get("data", ""), "hora": spec.get("hora", "")}
    return _post(s2)


def estatisticas(spec):
    nums = "".join(f'<div style="flex:1;min-width:0;text-align:center"><div style="font:700 104px/.92 \'GOAT Sans\';color:{Y}">{esc(n["valor"])}</div>'
                   f'<div style="margin-top:12px;font:600 26px/1.1 \'GOAT Sans\';letter-spacing:.06em;text-transform:uppercase;color:rgba(245,245,242,.9)">{esc(n["rotulo"])}</div></div>' for n in spec["numeros"])
    meio = f'<div style="display:flex;gap:28px;margin-top:24px;width:900px;max-width:100%">{nums}</div>'
    s2 = dict(spec)
    s2.setdefault("tamanho_titulo", 96)
    return _post(s2, meio)


# ---------- conferência automática (regras do Gestor) ----------
def _proibidos():
    f = KIT / "proibidos.txt"
    if not f.exists():
        return []
    return [l.strip().lower() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]


def _textos(spec):
    out = []
    def walk(v):
        if isinstance(v, str):
            if not re.search(r"\.(png|jpe?g|webp)$|^/|^fotos/|^https?:", v):
                out.append(v)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for k, x in v.items():
                if k not in ("foto", "fundo", "foco", "tipo", "marca"):
                    walk(x)
    walk(spec)
    return out


def conferir(spec):
    """Barra a arte que quebra uma regra fixa do Gestor. Devolve a lista de problemas (vazia = ok)."""
    erros = []
    tipo = spec.get("tipo")
    if tipo in ("manchete", "chamada", "estatisticas"):
        tl = spec.get("titulo", spec.get("pergunta", []))
        tl = [tl] if isinstance(tl, str) else (tl or [])
        if len(tl) > 2:
            erros.append("título com mais de 2 linhas (use frase curta: 1 linha, no máximo 2 curtas)")
        for l in tl:
            t = l if isinstance(l, str) else str(l.get("texto", ""))
            if len(t) > 22:
                erros.append(f'linha do título longa demais ({len(t)} letras, máx. 22): "{t}"')
        if len(str(spec.get("apoio", ""))) > 70:
            erros.append("subtítulo/apoio passa de 70 caracteres (tem que caber em 1 linha)")
        if len(str(spec.get("sobretitulo", ""))) > 30:
            erros.append("sobretítulo longo demais (máx. 30)")
        j = spec.get("jogo") or {}
        if j and not (j.get("confronto") and (j.get("data") or j.get("hora"))):
            erros.append('linha do jogo incompleta: precisa de confronto e dia/hora')
    if tipo == "agenda":
        for j in spec.get("jogos") or []:
            programa = " X " not in str(j.get("confronto", "")).upper()
            if not programa and not j.get("foto"):
                erros.append(f'card da agenda sem foto: {j.get("confronto")} (todo jogo leva foto)')
    texto = " ".join(_textos(spec)).lower()
    for termo in _proibidos():
        if re.search(r"(?<![a-zà-ú])" + re.escape(termo) + r"(?![a-zà-ú])", texto):
            erros.append(f'termo proibido pelo Gestor: "{termo}"')
    return erros


TIPOS = {"agenda": agenda, "jogo_unico": jogo_unico, "manchete": manchete, "chamada": chamada, "estatisticas": estatisticas}


# ---- fotos da equipe (apresentadores, comentaristas e repórteres) ----
# No spec, a foto de um programa pode vir como "equipe:<Nome como na planilha>" (ou "equipe:<arquivo>").
# As fotos ficam criptografadas em equipe/enc/ e o robô abre em equipe/private/ (fora do git).
EQUIPE = KIT.parent / "equipe" / "private"


def _slug(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def foto_equipe(valor):
    import hashlib, random
    ref = str(valor)[len("equipe:"):].strip()
    if re.fullmatch(r"[0-9a-f]{16}-\d+\.jpg", ref):
        cands = [EQUIPE / ref]
        nome = ref
    else:
        nome, _, idx = ref.partition("#")
        chave = hashlib.sha256(_slug(nome).encode()).hexdigest()[:16]
        cands = sorted(EQUIPE.glob(f"{chave}-*.jpg"))
        if idx.strip().isdigit():
            cands = [c for c in cands if c.stem.endswith(f"-{idx.strip()}")] or cands
    cands = [c for c in cands if c.exists()]
    if cands:
        return str(random.choice(cands))
    if os.environ.get("RG_EXIGIR_EQUIPE"):
        raise SystemExit(f"Sem foto da equipe para '{nome}'. Confira o nome no rodízio (rg_equipe_rodizio) ou suba a foto em Apresentadores.")
    # prévia sem a chave (sessão dos agentes): marcador cinza no lugar da foto
    from PIL import Image, ImageDraw
    ph = Path("/tmp") / f"equipe-previa-{_slug(nome) or 'x'}.jpg"
    if not ph.exists():
        im = Image.new("RGB", (1200, 1500), (46, 46, 50))
        d = ImageDraw.Draw(im)
        d.ellipse((400, 260, 800, 660), fill=(70, 70, 76))
        d.rounded_rectangle((260, 720, 940, 1500), 200, fill=(70, 70, 76))
        im.save(ph, quality=90)
    print(f"AVISO: prévia sem a foto real de '{nome}' (o robô coloca a foto na arte final).", file=sys.stderr)
    return str(ph)


def foco_rosto(path, caixa=(400, 160), centro=0.55):
    """Enquadra o rosto do retrato no card da agenda (object-position). Sem OpenCV, usa o topo da foto."""
    try:
        import cv2
        img = cv2.imread(str(path))
        h, w = img.shape[:2]
        cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = det.detectMultiScale(cinza, 1.1, 6, minSize=(w // 12, w // 12))
        if len(faces) == 0:
            return "50% 14%"
        x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
        cx, cy = (x + fw / 2) / w, (y + fh * centro) / h  # 0,55: um pouco abaixo dos olhos (pega o sorriso)
        bw, bh = caixa
        esc_ = max(bw / w, bh / h)
        sw, sh = w * esc_, h * esc_
        py = 50 if sh <= bh else (cy * sh - bh / 2) / (sh - bh) * 100
        px = 50 if sw <= bw else (cx * sw - bw / 2) / (sw - bw) * 100
        return f"{min(100, max(0, px)):.0f}% {min(100, max(0, py)):.0f}%"
    except Exception:
        return "50% 14%"


def resolver_equipe(spec):
    def fix(v):
        return foto_equipe(v) if isinstance(v, str) and v.startswith("equipe:") else v
    spec = dict(spec)
    for k in ("foto", "fundo"):
        if spec.get(k):
            spec[k] = fix(spec[k])
    if spec.get("jogos"):
        jogos = []
        for j in spec["jogos"]:
            f = j.get("foto")
            if isinstance(f, str) and f.startswith("equipe:"):
                # retrato da equipe: enquadra o rosto (cabeça inteira) por padrão
                caminho = fix(f)
                j = {"foco": foco_rosto(caminho), **j, "foto": caminho}
            jogos.append(j)
        spec["jogos"] = jogos
    return spec


def render(spec, out_path):
    from playwright.sync_api import sync_playwright
    spec = resolver_equipe(spec)
    tipo = spec.get("tipo")
    if tipo == "agenda" and len(spec.get("jogos") or []) == 1:
        # regra do Gestor: dia com jogo único usa SEMPRE o modelo de jogo único
        j = spec["jogos"][0]
        foto = j.get("foto") or spec.get("fundo")
        if not foto:
            raise SystemExit("Dia com jogo único: o modelo de jogo único exige foto do jogo. Peça a foto ao robô e monte de novo.")
        spec = {**spec, "tipo": "jogo_unico", "foto": foto, "foco": j.get("foco", "50% 30%"),
                "campeonato": j.get("rotulo", ""), "horario": j.get("horario", ""), "confronto": j.get("confronto", "")}
        tipo = "jogo_unico"
    if not os.environ.get("RG_SEM_CONFERENCIA"):
        erros = conferir(spec)
        if erros:
            raise SystemExit("CONFERÊNCIA AUTOMÁTICA REPROVOU A ARTE: " + " | ".join(erros))
    if tipo not in TIPOS:
        raise SystemExit(f"tipo inválido: {tipo}. Use: {', '.join(TIPOS)}")
    doc = TIPOS[tipo](spec)
    with sync_playwright() as p:
        exe = "/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None
        b = p.chromium.launch(executable_path=exe, args=["--no-sandbox"]) if exe else p.chromium.launch(args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.set_content(doc, wait_until="load")
        pg.evaluate("document.fonts.ready")
        pg.wait_for_function("document.body.dataset.ok==1", timeout=5000)
        pg.wait_for_timeout(150)
        pg.screenshot(path=out_path, clip={"x": 0, "y": 0, "width": W, "height": H})
        b.close()
    print(out_path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("uso: python3 render.py spec.json saida.png")
    render(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")), sys.argv[2])
