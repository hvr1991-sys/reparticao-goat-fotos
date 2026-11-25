"""Experimental milestone card; preserves official photographic treatment."""
import re
from pathlib import Path
import render as r

def build(s):
    if s.get("tipo")!="marco":
        raise ValueError("tipo invalido")
    if not s.get("foto") or not Path(s["foto"]).is_file() or not s.get("fonte"):
        raise ValueError("foto e fonte obrigatorias")
    if not s.get("fonte_dado"):
        raise ValueError("fonte do dado obrigatoria")
    focus=s.get("foco","50% 25%")
    if not re.fullmatch(r"(?:100|[0-9]{1,2})% (?:100|[0-9]{1,2})%",focus):
        raise ValueError("foco invalido")
    atual,meta=s.get("atual"),s.get("meta")
    if type(atual) is not int or type(meta) is not int or not 0<=atual<=meta<=99999:
        raise ValueError("numeros invalidos")
    nome=str(s.get("nome","")).strip()
    unidade=str(s.get("unidade","")).strip()
    if not nome or not unidade or len(nome)>40 or len(unidade)>20:
        raise ValueError("nome ou unidade invalida")
    errors=r.conferir(s)
    if errors:
        raise ValueError(" | ".join(errors))
    apoio=r.esc(s.get("apoio",""))
    if len(str(s.get("apoio","")))>70:
        raise ValueError("apoio longo demais")
    return r.page(f"""
    <img src="{r.editorial(s['foto'])}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:{focus}">
    <div style="position:absolute;inset:0;background:linear-gradient(180deg,#08080add,transparent 24%,transparent 52%,#08080a 100%),linear-gradient(90deg,#08080a99,transparent 30%,transparent 70%,#08080a99)"></div>
    {r.ilustrativo(s)}
    <div style="position:absolute;top:88px;left:60px;right:60px;text-align:center;letter-spacing:.25em;font:600 32px/1 GOAT Sans;color:{r.Y};white-space:nowrap">{r.esc(nome.upper())}</div>
    <div style="position:absolute;top:325px;left:48px;width:250px;text-align:center"><div style="font:700 132px/.9 GOAT Sans;color:{r.Y};white-space:nowrap">{atual}</div><div style="font:500 36px/1 GOAT Sans;margin-top:16px">{r.esc(unidade.upper())}</div></div>
    <div style="position:absolute;top:325px;right:48px;width:250px;text-align:center"><div style="font:500 36px/1 GOAT Sans">FALTAM</div><div style="font:700 132px/.9 GOAT Sans;color:{r.Y};white-space:nowrap">{meta-atual}</div></div>
    <div style="position:absolute;bottom:138px;left:60px;right:60px;text-align:center;font:600 30px/1.1 GOAT Sans;color:{r.Y};white-space:nowrap">{apoio}</div>
    <div style="position:absolute;bottom:45px;left:0;right:0;text-align:center">{r.mark_tag(s,130)}</div>
    """)
