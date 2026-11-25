"""Live API smoke test with synthetic editorial brief; not skill homologation."""
import json
from pathlib import Path
import diretor_v2, openrouter_v2, compositor_v2

out=Path("laboratorio-live")
out.mkdir(exist_ok=True)
brief={"titulo":"FUTEBOL EM FOCO","finalidade":"editorial","ilustrativo":True}
# Explicitly synthetic instructions: the original ZIP has not been verified here.
ctx=diretor_v2.preparar(brief,"INSTRUCOES SINTETICAS DE TESTE: fundo escuro, logo GOAT, titulo curto, tipografia condensada. Sem dados factuais ou fotografias neste teste.",[],[],{})
ctx["instrucoes"].append("Crie uma arte tipografica original sem fotografias, com o titulo FUTEBOL EM FOCO. Inclua exatamente uma marca. Use margens de 48 px e caixas de texto suficientemente altas.")
result=openrouter_v2.gerar(ctx)
spec=result["spec"]
(out/"spec.json").write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding="utf-8")
compositor_v2.render(spec,out/"arte.png")
print("LIVE_FREE_API_RENDER_OK; fixture sintetica; revisao pendente")
