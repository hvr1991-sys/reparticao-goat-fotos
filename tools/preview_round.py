"""Offline integration preview. Never imports processar or accesses Supabase."""
import json, tempfile
from pathlib import Path
from unittest.mock import patch
from tools import designer_openrouter as designer

def main():
    card={"id":"preview-only","designer":"goat-designer","title":"Agenda experimental","pub_date":"2026-11-28","due_date":"2026-11-27"}
    docs=[{"id":"goat-designer","content":"Dados ilustrativos. Logo GOAT. Barlow Condensed. Sem publicação."}]
    plan={"brief":"Entrega: SEX 27.11 · Post: SAB 28.11","fotos":[],"foto_obrigatoria":False,"spec":{"tipo":"agenda","marca":"logo","ilustrativo":True,"data_dia_semana":"SABADO","data_resto":"28 DE NOVEMBRO","jogos":[{"horario":"16H","rotulo":"TESTE TECNICO","confronto":"PROGRAMA A"},{"horario":"18H","rotulo":"TESTE TECNICO","confronto":"PROGRAMA B"}]}}
    events=[]
    with tempfile.TemporaryDirectory() as temp:
        png=Path(temp)/"preview.png"
        def mount(cid,spec):
            from kit.render import render
            render(spec,str(png))
            return "feito",{"arquivo":str(png)},png
        def no_photos(*args):
            raise AssertionError("Unexpected network photo request")
        with patch.object(designer,"planejar",return_value=plan),patch.object(designer,"revisar_arte",return_value=(True,"")):
            designer.produzir(card,docs,no_photos,mount,events.append)
        assert events and events[-1].get("stage")=="pente",events
        from PIL import Image
        with Image.open(png) as im:
            assert im.size==(1080,1350)
            im.verify()
        out=Path("/tmp/goat-round-preview")
        out.mkdir(exist_ok=True)
        (out/"agenda.png").write_bytes(png.read_bytes())
        (out/"events.json").write_text(json.dumps(events,ensure_ascii=False,indent=2))
    print("Offline designer orchestration passed; AI responses mocked; no database writes.")

if __name__=="__main__":
    main()
