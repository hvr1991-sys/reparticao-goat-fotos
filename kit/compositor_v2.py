"""Experimental data-driven composition. No arbitrary HTML, CSS or code from AI."""
import json, os, re, sys
from pathlib import Path
import render as r

ROOT=r.KIT.parent.resolve()
COLORS={"amarelo":r.Y,"branco":r.WHITE,"preto":r.BLACK,"cinza":"#AAAAAA"}
ALIGN={"esquerda":"left","centro":"center","direita":"right"}
def integer(v,lo,hi):
    if type(v) is not int or not lo<=v<=hi:
        raise ValueError(f"inteiro fora dos limites {lo}-{hi}")
    return v

def asset(a):
    if not isinstance(a,dict) or not str(a.get("fonte","")).startswith("https://"):
        raise ValueError("foto exige fonte HTTPS registrada")
    path=(ROOT/str(a["arquivo"])).resolve()
    if not path.is_relative_to(ROOT/"fotos") or path.suffix.lower() not in (".png",".jpg",".jpeg",".webp") or not path.is_file():
        raise ValueError("foto fora do acervo autorizado")
    # Match exact asset against successful metadata from the existing photo robot.
    meta=json.loads((path.parent/"meta.json").read_text())
    if not any(x.get("ok") is True and x.get("arquivo")==path.name and a["fonte"] in (x.get("pagina"),x.get("url_imagem")) for x in meta.get("fotos",[])):
        raise ValueError("foto sem procedencia correspondente no acervo")
    return path

def recorte_uri(path, points):
    """Polygon mask over original photo; no generative replacement."""
    import base64, io
    from PIL import Image, ImageDraw
    if not isinstance(points,list) or not 3<=len(points)<=120:
        raise ValueError("contorno precisa de 3 a 120 pontos")
    im=Image.open(path).convert("RGB")
    w,h=im.size
    if w*h>40000000:
        raise ValueError("foto grande demais")
    polygon=[]
    for point in points:
        if not isinstance(point,list) or len(point)!=2:
            raise ValueError("ponto invalido")
        x,y=point
        polygon.append((integer(x,0,w-1),integer(y,0,h-1)))
    mask=Image.new("L",(w,h),0)
    ImageDraw.Draw(mask).polygon(polygon,fill=255)
    if not mask.getbbox():
        raise ValueError("mascara vazia")
    im.putalpha(mask)
    buf=io.BytesIO()
    im.save(buf,format="PNG")
    return "data:image/png;base64,"+base64.b64encode(buf.getvalue()).decode()

def build(s):
    if s.get("tipo")!="composicao_livre":
        raise ValueError("tipo invalido")
    if s.get("finalidade")=="agenda_jogo_unico" or (s.get("finalidade")=="agenda" and len(s.get("jogos",[]))==1):
        raise ValueError("usar o modelo obrigatorio jogo_unico")
    if s.get("marca","logo") != "logo":
        raise ValueError("usar exclusivamente o logo GOAT, nunca o bodinho")
    items=s.get("elementos")
    if not isinstance(items,list) or not 2<=len(items)<=32 or not all(isinstance(e,dict) for e in items):
        raise ValueError("2 a 32 elementos")
    if sum(e.get("tipo")=="marca" for e in items)!=1:
        raise ValueError("exatamente uma marca")
    if s.get("finalidade") in ("tarja","thumb","header","transmissao","pre_jogo"):
        raise ValueError("formatos fora do escopo feed 1080x1350")
    if not any(e.get("tipo")=="texto" and e.get("papel")=="titulo" for e in items):
        raise ValueError("titulo obrigatorio")
    assets=s.get("fotos",{})
    if not isinstance(assets,dict) or len(assets)>8:
        raise ValueError("acervo invalido")
    parts=[]
    protected=[]
    foreground=[]
    for e in items:
        t=e.get("tipo")
        x=integer(e.get("x"),0,1079); y=integer(e.get("y"),0,1349)
        w=integer(e.get("w"),1,1080-x); h=integer(e.get("h"),1,1350-y)
        pos=f"position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px"
        if t in ("texto","marca") and (x<48 or y<48 or x+w>1032 or y+h>1302):
            raise ValueError("elemento textual ou marca fora da margem experimental")
        if t in ("texto","marca"):
            foreground.append((x,y,x+w,y+h))
        if t=="foto":
            focus=e.get("foco","50% 25%")
            if not re.fullmatch(r"(?:100|[0-9]{1,2})% (?:100|[0-9]{1,2})%",focus):
                raise ValueError("foco invalido")
            path=asset(assets[e["ref"]])
            # Face boxes supplied by a reviewer are canvas coordinates, not identity labels.
            for box in e.get("rostos_protegidos",[]):
                if not isinstance(box,list) or len(box)!=4:
                    raise ValueError("caixa de rosto invalida")
                bx,by,bw,bh=box
                integer(bx,x,x+w-1); integer(by,y,y+h-1)
                integer(bw,1,x+w-bx); integer(bh,1,y+h-by)
                protected.append((bx,by,bx+bw,by+bh))
            mask=e.get("recorte_poligono")
            src=recorte_uri(path,mask) if mask is not None else r.editorial(path)
            # Feather photo edges without changing original image geometry.
            fade=e.get("transicao")
            effect=""
            if fade is not None:
                if not isinstance(fade,dict):
                    raise ValueError("transicao invalida")
                direction={"base":"to bottom","topo":"to top","esquerda":"to left","direita":"to right"}.get(fade.get("lado"))
                if direction is None:
                    raise ValueError("lado da transicao invalido")
                amount=integer(fade.get("extensao",30),10,45)
                effect=f";mask-image:linear-gradient({direction},black 0%,black {100-amount}%,transparent 100%);-webkit-mask-image:linear-gradient({direction},black 0%,black {100-amount}%,transparent 100%)"
                # Reject a fade that intersects a reviewer-marked face.
                side=fade["lado"]
                for bx,by,bw,bh in e.get("rostos_protegidos",[]):
                    if ((side=="base" and by+bh>y+h*(1-amount/100)) or
                        (side=="topo" and by<y+h*amount/100) or
                        (side=="esquerda" and bx<x+w*amount/100) or
                        (side=="direita" and bx+bw>x+w*(1-amount/100))):
                        raise ValueError("transicao invade rosto protegido")
            parts.append(f'<img src="{src}" style="{pos};object-fit:cover;object-position:{focus}{effect}">')
        elif t=="marca":
            parts.append(f'<div style="{pos};display:flex;align-items:center;justify-content:center">{r.mark_tag(s,w,"max-height:100%;object-fit:contain")}</div>')
        elif t=="forma":
            color=COLORS[e.get("cor","preto")]
            # Provisional conservative guard: yellow is an accent, not a large panel.
            if color==r.Y and w*h>1080*1350*0.08:
                raise ValueError("amarelo reservado a detalhes; bloco grande")
            opacity=integer(e.get("opacidade",100),0,100)/100
            radius=integer(e.get("raio",0),0,100)
            parts.append(f'<div style="{pos};background:{color};opacity:{opacity};border-radius:{radius}px"></div>')
        elif t=="degrade":
            direction={"base":"to top","topo":"to bottom","esquerda":"to right","direita":"to left"}[e.get("direcao","base")]
            strength=integer(e.get("intensidade",90),0,100)/100
            parts.append(f'<div style="{pos};background:linear-gradient({direction},rgba(8,8,10,{strength}),transparent)"></div>')
        elif t=="texto":
            value=e.get("texto","")
            if not isinstance(value,str) or not value.strip() or len(value)>100 or "\\n" in value:
                raise ValueError("texto invalido")
            role=e.get("papel","apoio")
            if role not in ("titulo","apoio","sobretitulo","dado","jogo"):
                raise ValueError("papel textual invalido")
            if role=="titulo" and len(value)>22:
                raise ValueError("linha de titulo longa")
            if role=="apoio" and len(value)>70:
                raise ValueError("apoio longo")
            if role=="dado" and not s.get("fonte_dado"):
                raise ValueError("dado exige fonte")
            size=integer(e.get("tamanho",48),24,180)
            weight=integer(e.get("peso",600),400,800)
            if weight not in (400,500,600,700,800):
                raise ValueError("peso tipografico indisponivel")
            align=ALIGN[e.get("alinhamento","esquerda")]
            color=COLORS[e.get("cor","branco")]
            stroke=integer(e.get("contorno",0),0,5)
            if stroke and role!="titulo":
                raise ValueError("contorno reservado ao titulo experimental")
            outline=f"-webkit-text-stroke:{stroke}px {color};color:transparent" if stroke else f"color:{color}"
            parts.append(f'<div data-text="1" style="{pos};font:{weight} {size}px/1.1 \'GOAT Sans\';text-align:{align};{outline};white-space:nowrap">{r.esc(value)}</div>')
        else:
            raise ValueError("elemento desconhecido")
    if sum(e.get("papel")=="titulo" for e in items)>2:
        raise ValueError("maximo de duas linhas de titulo")
    for a in foreground:
        for b in protected:
            if max(a[0],b[0])<min(a[2],b[2]) and max(a[1],b[1])<min(a[3],b[3]):
                raise ValueError("texto ou marca invade area de rosto protegida")
    errors=r.conferir(s)
    if errors:
        raise ValueError(" | ".join(errors))
    if s.get("ilustrativo"):
        parts.append('<div style="position:absolute;top:12px;left:12px;color:#FFD318;background:#08080A;padding:4px 8px;font:600 22px GOAT Sans">DADOS ILUSTRATIVOS</div>')
    return r.page("".join(parts))

def render(s,out):
    from playwright.sync_api import sync_playwright
    doc=build(s)
    with sync_playwright() as p:
        exe="/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None
        b=p.chromium.launch(executable_path=exe,args=["--no-sandbox"])
        try:
            pg=b.new_page(viewport={"width":1080,"height":1350},device_scale_factor=1)
            pg.set_content(doc,wait_until="load")
            pg.wait_for_function("document.body.dataset.ok==1")
            bad=pg.evaluate("""() => [...document.querySelectorAll('[data-text]')].filter(e=>e.scrollWidth>e.clientWidth+1 || e.scrollHeight>e.clientHeight+1 || parseFloat(getComputedStyle(e).fontSize)<24).map(e=>e.textContent)""")
            if bad:
                raise ValueError("texto excede caixa ou legibilidade: "+str(bad))
            pg.screenshot(path=str(out))
        finally:
            b.close()

if __name__=="__main__":
    if len(sys.argv)!=3:
        raise SystemExit("uso: python kit/compositor_v2.py spec.json saida.png")
    render(json.loads(Path(sys.argv[1]).read_text()),sys.argv[2])
