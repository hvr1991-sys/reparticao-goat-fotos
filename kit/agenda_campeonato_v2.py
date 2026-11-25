"""Experimental championship schedule, independent of production."""
import json, re, sys
from pathlib import Path
import render as r

def build(s):
    if s.get("tipo") != "agenda_campeonato":
        raise ValueError("tipo invalido")
    groups=s.get("dias",[])
    if not isinstance(groups,list) or not 1 <= len(groups) <= 3:
        raise ValueError("um a tres dias")
    if not str(s.get("campeonato","")).strip():
        raise ValueError("campeonato obrigatorio")
    if not s.get("foto") or not Path(s["foto"]).is_file() or not s.get("fonte"):
        raise ValueError("foto e fonte obrigatorias")
    focus=s.get("foco","50% 25%")
    if not re.fullmatch(r"(?:100|[0-9]{1,2})% (?:100|[0-9]{1,2})%",focus):
        raise ValueError("foco invalido")
    blocks=[]
    total=0
    for group in groups:
        games=group.get("jogos",[])
        if not group.get("data") or not 1 <= len(games) <= 3:
            raise ValueError("data e um a tres jogos por dia")
        total+=len(games)
        cols=[]
        for g in games:
            if not g.get("horario") or " X " not in str(g.get("confronto","")).upper():
                raise ValueError("confronto e horario obrigatorios")
            a,b=g["confronto"].upper().split(" X ",1)
            cols.append(f'<div style="flex:1;min-width:0;text-align:center;padding:0 12px;border-right:1px solid {r.Y}"><div style="font:700 38px/1.05 GOAT Sans;white-space:nowrap">{r.esc(a)}</div><div style="font:700 38px/1.05 GOAT Sans;white-space:nowrap"><span style="color:{r.Y}">X</span> {r.esc(b)}</div><div style="font:700 36px/1 GOAT Sans;margin-top:12px">{r.esc(g["horario"])}</div></div>')
        blocks.append(f'<div style="margin-bottom:20px"><div style="text-align:center;border-top:1px solid #555;padding-top:10px;margin-bottom:14px;font:600 26px/1 GOAT Sans;color:{r.Y};letter-spacing:.16em">{r.esc(group["data"].upper())}</div><div style="display:flex">{"".join(cols)}</div></div>')
    if total<2:
        raise ValueError("um jogo deve usar o modelo oficial jogo_unico")
    errors=r.conferir(s)
    if errors:
        raise ValueError(" | ".join(errors))
    return r.page(f"""
    <img src="{r.editorial(s['foto'])}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:{focus}">
    <div style="position:absolute;inset:0;background:linear-gradient(180deg,#08080add,transparent 30%,#08080a22 40%,#08080a 66%)"></div>
    <div style="position:absolute;top:80px;left:60px;right:60px;text-align:center;font:700 78px/1 GOAT Sans"><div>AGENDA DE</div><div style="color:{r.Y};white-space:nowrap">{r.esc(s['campeonato'].upper())}</div></div>
    {r.ilustrativo(s)}
    <div style="position:absolute;bottom:150px;left:60px;right:60px">{"".join(blocks)}</div>
    <div style="position:absolute;bottom:42px;left:0;right:0;text-align:center">{r.mark_tag(s,130)}</div>
    """)

def render_experimental(s,out):
    from playwright.sync_api import sync_playwright
    doc=build(s)
    with sync_playwright() as p:
        b=p.chromium.launch(args=["--no-sandbox"])
        try:
            page=b.new_page(viewport={"width":r.W,"height":r.H},device_scale_factor=1)
            page.set_content(doc,wait_until="load")
            page.wait_for_function("document.body.dataset.ok==1")
            page.screenshot(path=out)
        finally:
            b.close()

if __name__=="__main__":
    if len(sys.argv)!=3:
        raise SystemExit("uso: python kit/agenda_campeonato_v2.py spec.json saida.png")
    render_experimental(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")),sys.argv[2])
