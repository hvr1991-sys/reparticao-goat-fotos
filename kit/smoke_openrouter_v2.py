"""Live API smoke test with synthetic editorial brief; not skill homologation."""
import json
from pathlib import Path
import diretor_v2, openrouter_v2, compositor_v2

out=Path("laboratorio-live")
out.mkdir(exist_ok=True)
brief={"titulo":"FUTEBOL EM FOCO","finalidade":"editorial","ilustrativo":True}
fotos={"principal":{"arquivo":"fotos/90ba0dee-0846-45cd-9f01-1694ec9f855f-j82/1.png","fonte":"https://www.spl.com.sa/en/news/ronaldo-marks-return-with-brilliant-goal-earns-postecoglou-praise"}}
# Explicitly synthetic instructions: the original ZIP has not been verified here.
ctx=diretor_v2.preparar(brief,"INSTRUCOES SINTETICAS DE TESTE: fundo escuro, logo GOAT, titulo curto, tipografia condensada. Sem dados factuais neste teste.",[],[],fotos)
ctx["instrucoes"].append("Crie uma arte editorial original com a foto principal obrigatoria e o titulo FUTEBOL EM FOCO preenchido, nao apenas contornado. Inclua exatamente uma marca. Foto horizontal 1920x1080; nao distorcer. Sem dados inventados. Use margens de 48 px e caixas de texto suficientemente altas.")
result=openrouter_v2.gerar(ctx)
spec=result["spec"]
if not any(e.get("tipo")=="foto" and e.get("ref")=="principal" for e in spec["elementos"]):
    raise ValueError("foto oficial obrigatoria ausente")
if not any(e.get("papel")=="titulo" and e.get("texto")=="FUTEBOL EM FOCO" and e.get("contorno",0)==0 for e in spec["elementos"]):
    raise ValueError("titulo preenchido obrigatorio ausente")
(out/"spec.json").write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding="utf-8")
compositor_v2.render(spec,out/"arte.png")
print("LIVE_FREE_API_RENDER_OK; fixture sintetica; revisao pendente")
