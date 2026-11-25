"""Experimental standings layout; no production registration."""
import json, sys
from pathlib import Path
import render as r

def build(s):
    if s.get("tipo") != "classificacao":
        raise ValueError("tipo invalido")
    rows=s.get("linhas",[])
    if not isinstance(rows,list) or not 2 <= len(rows) <= 20:
        raise ValueError("2 a 20 clubes")
    if not str(s.get("campeonato","")).strip():
        raise ValueError("campeonato obrigatorio")
    if not all(isinstance(x,dict) for x in rows):
        raise ValueError("linhas invalidas")
    positions=[x.get("pos") for x in rows]
    if positions != list(range(1,len(rows)+1)):
        raise ValueError("posicoes precisam ser consecutivas e ordenadas")
    seen=set()
    content=[]
    legend={}
    colors={"acesso":r.Y,"playoff":"#B8A04A","rebaixamento":"#EF6262","normal":"#777779"}
    labels={"acesso":"ACESSO","playoff":"PLAYOFF","rebaixamento":"REBAIXAMENTO"}
    for x in rows:
        name=str(x.get("clube","")).strip()
        pts=x.get("pts")
        zone=x.get("zona","normal")
        if not name or len(name)>42 or name.casefold() in seen or type(pts) is not int or pts < 0 or zone not in colors:
            raise ValueError("clube, pontuacao ou zona invalida")
        seen.add(name.casefold())
        color=colors[zone]
        if zone in labels:
            legend[zone]=labels[zone]
        content.append(f'<div style="display:grid;grid-template-columns:80px 1fr 100px;align-items:center;border-left:4px solid {color};background:rgba(245,245,242,.045);height:{min(66,880//len(rows))}px;margin-bottom:3px;padding:0 18px;font:600 {min(34,590//len(rows))}px/1 GOAT Sans"><div style="color:{color}">{x["pos"]:02}</div><div style="white-space:nowrap">{r.esc(name.upper())}</div><div style="text-align:right">{pts}</div></div>')
    errors=r.conferir(s)
    if errors:
        raise ValueError(" | ".join(errors))
    keys="".join(f'<span style="margin:0 12px"><span style="color:{colors[k]}">■</span> {v}</span>' for k,v in legend.items())
    return r.page(f"""
    <div style="position:absolute;inset:0;background:radial-gradient(ellipse at 30% 25%,#242423,{r.BLACK} 70%)"></div>
    {r.ilustrativo(s)}
    <div style="position:absolute;top:75px;left:60px;right:60px;text-align:center">
    <div style="font:600 26px/1 GOAT Sans;color:{r.Y};letter-spacing:.16em;white-space:nowrap">{r.esc(s["campeonato"].upper())}</div>
    <div style="font:700 86px/1 GOAT Sans;margin-top:16px;white-space:nowrap">{r.esc(str(s.get("titulo","CLASSIFICAÇÃO")).upper())}</div>
    <div style="font:500 22px/1 GOAT Sans;margin-top:18px">{keys}</div>
    </div>
    <div style="position:absolute;top:300px;left:90px;right:90px">
    <div style="display:grid;grid-template-columns:80px 1fr 100px;padding:0 22px 12px;color:#aaa;font:500 22px/1 GOAT Sans"><div>POS</div><div>CLUBE</div><div style="text-align:right">PTS</div></div>
    {"".join(content)}
    </div>
    <div style="position:absolute;bottom:45px;left:0;right:0;text-align:center">{r.mark_tag(s,130)}</div>
    """)
