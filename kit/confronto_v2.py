"""Experimental split-photo layout. Does not register in production renderer."""
import json, re, sys
from pathlib import Path
import render as r

def build(s):
    if s.get("tipo") != "confronto_duplo":
        raise ValueError("tipo invalido")
    fotos = s.get("fotos", [])
    if len(fotos) != 2 or not all(isinstance(f, dict) for f in fotos):
        raise ValueError("duas fotos obrigatorias")
    j = s.get("jogo", {})
    if not all(str(j.get(k,"")).strip() for k in ("campeonato","confronto","data","hora")):
        raise ValueError("dados do jogo incompletos")
    if " X " not in j["confronto"].upper():
        raise ValueError("confronto precisa de dois times")
    lines = s.get("titulo", [])
    if not isinstance(lines,list) or not 1 <= len(lines) <= 2 or not all(isinstance(l,dict) and str(l.get("texto","")).strip() for l in lines):
        raise ValueError("titulo precisa de uma ou duas linhas")
    check = dict(s, tipo="chamada")
    errors = r.conferir(check)
    if errors:
        raise ValueError(" | ".join(errors))
    images=[]
    for i,f in enumerate(fotos):
        path = Path(f["arquivo"])
        if not path.is_file() or not f.get("fonte"):
            raise ValueError("arquivo e fonte obrigatorios")
        focus=f.get("foco","50% 25%")
        if not re.fullmatch(r"(?:100|[0-9]{1,2})% (?:100|[0-9]{1,2})%",focus):
            raise ValueError("foco invalido")
        clip="polygon(0 0, 100% 0, 83% 100%, 0 100%)" if i==0 else "polygon(17% 0, 100% 0, 100% 100%, 0 100%)"
        side="left:0" if i==0 else "right:0"
        images.append(f'<img src="{r.editorial(path)}" style="position:absolute;top:0;{side};width:60%;height:1000px;object-fit:cover;object-position:{focus};clip-path:{clip}">')
    pre = f'<div style="font-size:30px;color:{r.Y};margin-top:15px">PRÉ-JOGO ÀS {r.esc(s["pre_jogo"])}</div>' if s.get("pre_jogo") else ""
    return r.page(f"""
    {''.join(images)}
    <div style="position:absolute;top:0;left:59.8%;width:3px;height:1000px;background:{r.Y};transform-origin:top;transform:rotate(6deg)"></div>
    <div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.45),transparent 18%,transparent 44%,{r.BLACK} 80%)"></div>
    <div style="position:absolute;top:48px;left:54px">{r.mark_tag(s,130)}</div>
    {r.ilustrativo(s)}
    <div style="position:absolute;bottom:66px;left:64px;right:64px;text-align:center">
    <div style="font:600 28px/1 'GOAT Sans';letter-spacing:.15em;color:{r.Y};white-space:nowrap;margin-bottom:20px">{r.esc(j["campeonato"].upper())}</div>
    <div style="font:700 112px/.95 'GOAT Sans';margin-bottom:26px">{r._titulo_duas_cores(lines)}</div>
    <div style="font:600 42px/1 'GOAT Sans';white-space:nowrap"><span style="color:{r.Y}">{r.esc(j["data"])} · {r.esc(j["hora"])}</span> | {r.confronto(j["confronto"])}</div>
    {pre}
    </div>""")

def render_experimental(s,out):
    # Explicit standalone entry point; no changes to the standard kit.
    doc=build(s)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(args=["--no-sandbox"])
        try:
            page=browser.new_page(viewport={"width":r.W,"height":r.H},device_scale_factor=1)
            page.set_content(doc,wait_until="load")
            page.wait_for_function("document.body.dataset.ok==1")
            page.screenshot(path=out)
        finally:
            browser.close()

if __name__=="__main__":
    if len(sys.argv)!=3:
        raise SystemExit("uso: python kit/confronto_v2.py spec.json saida.png")
    render_experimental(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")),sys.argv[2])
