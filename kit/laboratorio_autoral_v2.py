"""Six synthetic editorial trials with official archived photographs."""
import json
from pathlib import Path
import diretor_v2, openrouter_v2, compositor_v2
from PIL import Image
out=Path("laboratorio-autoral")
out.mkdir(exist_ok=True)
base="fotos/90ba0dee-0846-45cd-9f01-1694ec9f855f-j82/"
photos={
 "principal":{"arquivo":base+"1.png","fonte":"https://www.spl.com.sa/en/news/ronaldo-marks-return-with-brilliant-goal-earns-postecoglou-praise"},
 "secundaria":{"arquivo":base+"2.png","fonte":"https://www.spl.com.sa/en/news/on-to-the-next-ronaldo-hits-980-career-goals-as-champions-al-nassr-move-joint-top"}
}
cases=[
 ("manchete","FUTEBOL EM FOCO","Impacto editorial com foto dominante."),
 ("duas_imagens","DOIS MOMENTOS","Duas fotos do mesmo atleta; nao simular confronto entre atletas distintos."),
 ("estatistica","EM NUMEROS","Hierarquia numerica; use somente o numero ilustrativo 10, sem atribuir desempenho real."),
 ("marco","RUMO AO MARCO","Valorize a expectativa de um marco sem inventar total ou recorde."),
 ("contexto","O JOGO CONTINUA","Composicao editorial com area de respiro e contexto sem alegacoes factuais."),
 ("especial","ALÉM DO CAMPO","Explore uma composicao autoral com camadas e tipografia preenchida.")
]
report=[]
recentes=[]
for name,title,angle in cases:
    try:
        brief={"titulo":title,"finalidade":"editorial","ilustrativo":True,"fonte_dado":"fixture sintetica, nao publicar" if name=="estatistica" else None}
        ctx=diretor_v2.preparar(brief,"INSTRUCOES SINTETICAS PARA TESTE, NAO SKILL ORIGINAL. Fundo escuro, logo GOAT, tipografia condensada, titulo preenchido, fotos reais sem deformacao.",[],[],photos,recentes)
        ctx["instrucoes"].append(f"Titulo literal: {title}. {angle} Use foto principal obrigatoria, titulo preenchido sem contorno, exatamente uma marca. Nao invente fatos. Varie a geometria em relacao as anteriores.")
        result=openrouter_v2.gerar(ctx)
        spec=result["spec"]
        items=spec["elementos"]
        if not any(e.get("tipo")=="foto" and e.get("ref")=="principal" for e in items):
            raise ValueError("foto principal ausente")
        if name=="duas_imagens" and not any(e.get("tipo")=="foto" and e.get("ref")=="secundaria" for e in items):
            raise ValueError("segunda foto ausente")
        if not any(e.get("papel")=="titulo" and e.get("texto")==title and e.get("contorno",0)==0 for e in items):
            raise ValueError("titulo preenchido ausente")
        png=out/(name+".png")
        compositor_v2.render(spec,png)
        with Image.open(png) as im:
            if im.size!=(1080,1350): raise ValueError("dimensoes invalidas")
            im.verify()
        (out/(name+".json")).write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding="utf-8")
        recentes.append([{"tipo":e.get("tipo"),"x":e["x"],"y":e["y"],"w":e["w"],"h":e["h"]} for e in items])
        report.append({"caso":name,"status":"renderizado","revisao_visual":"pendente"})
    except Exception as exc:
        report.append({"caso":name,"status":"falha","erro":str(exc)[:180]})
    (out/"relatorio.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False))
if any(x["status"]!="renderizado" for x in report): raise SystemExit(1)
