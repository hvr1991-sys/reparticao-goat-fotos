"""Standalone GOAT 2.0 laboratory renderer. Production render.py remains unchanged."""
import json, os, sys
from pathlib import Path
import render as r
import confronto_v2, agenda_campeonato_v2, classificacao_v2, marco_v2, contexto_v2

LAYOUTS={
    "confronto_duplo":confronto_v2.build,
    "agenda_campeonato":agenda_campeonato_v2.build,
    "classificacao":classificacao_v2.build,
    "marco":marco_v2.build,
    "contexto":contexto_v2.build,
}

def build(spec):
    if spec.get("marca","logo") != "logo":
        raise ValueError("usar exclusivamente o logo GOAT")
    tipo=spec.get("tipo")
    if tipo not in LAYOUTS:
        raise ValueError("layout experimental desconhecido")
    if tipo=="classificacao" and not spec.get("fonte_dado"):
        raise ValueError("fonte dos dados obrigatoria")
    return LAYOUTS[tipo](spec)

def render(spec,out):
    from playwright.sync_api import sync_playwright
    doc=build(spec)
    with sync_playwright() as p:
        exe="/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None
        browser=p.chromium.launch(executable_path=exe,args=["--no-sandbox"])
        try:
            page=browser.new_page(viewport={"width":r.W,"height":r.H},device_scale_factor=1)
            page.set_content(doc,wait_until="load")
            page.wait_for_function("document.body.dataset.ok==1",timeout=10000)
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(out))
        finally:
            browser.close()

if __name__=="__main__":
    if len(sys.argv)!=3:
        raise SystemExit("uso: python kit/render_v2.py spec.json saida.png")
    render(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")),sys.argv[2])
