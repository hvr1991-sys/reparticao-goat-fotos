"""Experimental headline with compact contextual standings."""
import re
from pathlib import Path
import render as r

def build(s):
    if s.get("tipo")!="contexto":
        raise ValueError("tipo invalido")
    if not s.get("foto") or not Path(s["foto"]).is_file() or not s.get("fonte"):
        raise ValueError("foto e fonte obrigatorias")
    if not s.get("fonte_dado"):
        raise ValueError("fonte do dado obrigatoria")
    focus=s.get("foco","50% 25%")
    if not re.fullmatch(r"(?:100|[0-9]{1,2})% (?:100|[0-9]{1,2})%",focus):
        raise ValueError("foco invalido")
    lines=s.get("titulo",[])
    if not isinstance(lines,list) or not 1<=len(lines)<=2 or not all(isinstance(x,dict) and str(x.get("texto","")).strip() for x in lines):
        raise ValueError("titulo invalido")
    errors=r.conferir(dict(s,tipo="manchete"))
    if errors:
        raise ValueError(" | ".join(errors))
    rows=s.get("linhas",[])
    if not isinstance(rows,list) or not 1<=len(rows)<=4:
        raise ValueError("1 a 4 linhas contextuais")
    content=[]
    for row in rows:
        name=str(row.get("rotulo","")).strip()
        value=str(row.get("valor","")).strip()
        if not name or not value or len(name)>45 or len(value)>14:
            raise ValueError("linha contextual invalida")
        color=r.Y if row.get("destaque") else r.WHITE
        content.append(f'<div style="display:flex;justify-content:space-between;gap:15px;border-bottom:1px solid #777;padding:9px 0;color:{color};font:600 32px/1 GOAT Sans"><div style="flex:1;min-width:0;white-space:nowrap">{r.esc(name.upper())}</div><div>{r.esc(value)}</div></div>')
    j=s.get("jogo")
    game=f'<div style="margin-top:23px">{r._linha_jogo(j,42)}</div>' if j else ""
    return r.page(f"""
    <img src="{r.editorial(s['foto'])}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:{focus}">
    <div style="position:absolute;inset:0;background:linear-gradient(180deg,#08080a77,transparent 25%,transparent 35%,#08080ae8 65%,#08080a 100%)"></div>
    <div style="position:absolute;top:48px;left:54px">{r.mark_tag(s,130)}</div>
    {r.ilustrativo(s)}
    <div style="position:absolute;bottom:60px;left:60px;right:60px">
    <div style="font:600 28px/1 GOAT Sans;color:{r.Y};letter-spacing:.15em;white-space:nowrap;margin-bottom:16px">{r.esc(s.get("sobretitulo","").upper())}</div>
    <div style="font:700 96px/.95 GOAT Sans;margin-bottom:20px">{r._titulo_duas_cores(lines)}</div>
    <div style="width:70%;margin:18px 0">{''.join(content)}</div>
    {game}
    </div>""")
