"""Experimental art direction adapter. No provider calls or publishing."""
import json
from pathlib import Path
import compositor_v2 as c

def preparar(briefing, skill, ensinamentos, referencias, fotos, recentes=()):
    if not isinstance(briefing,dict) or not briefing.get("titulo"):
        raise ValueError("briefing exige titulo")
    if not isinstance(skill,str) or not skill.strip():
        raise ValueError("skill original obrigatoria; nao substituir por resumo")
    rules=json.loads(Path(__file__).with_name("direcao_criativa_v2.json").read_text(encoding="utf-8"))
    for a in fotos.values():
        c.asset(a)
    return {
        "instrucoes": [
            "Planeje uma composicao original a partir do briefing. Devolva apenas JSON, nunca HTML ou codigo.",
            "A ordem das camadas e a ordem da lista elementos. Respeite a skill e as orientacoes mais recentes do gestor.",
            "Use somente fotos registradas no acervo recebido. Nao invente dados nem fontes.",
            "Varie a disposicao de elementos em relacao as composicoes recentes.",
            "Se for agenda de jogo unico, encaminhe ao modelo oficial; nao use composicao livre.",
            "Nao confunda referencias visuais com regras obrigatorias."
        ],
        "contrato": {
            "tipo":"composicao_livre","marca":"logo","canvas":[1080,1350],
            "elementos":"2 a 32; x,y,w,h inteiros; camadas na ordem da lista",
            "tipos":{
                "foto":{"ref":"chave do acervo","foco":"50% 25%","rostos_protegidos":"caixas conhecidas em coordenadas do canvas"},
                "texto":{"papel":"titulo|apoio|sobretitulo|dado|jogo","texto":"texto literal","tamanho":"24-180","peso":[400,500,600,700,800],"alinhamento":["esquerda","centro","direita"],"cor":["amarelo","branco","preto","cinza"],"contorno":"0-5, apenas titulo"},
                "forma":{"cor":"paleta oficial","opacidade":"0-100","raio":"0-100"},
                "degrade":{"direcao":["base","topo","esquerda","direita"],"intensidade":"0-100"},
                "marca":{"quantidade":1}
            }
        },
        "regras":rules,"skill_original":skill,"ensinamentos":ensinamentos,
        "referencias":referencias,"briefing":briefing,"fotos":fotos,"recentes":list(recentes)[-12:]
    }

def aceitar(resposta, contexto):
    if not isinstance(resposta,str) or len(resposta)>60000:
        raise ValueError("resposta invalida")
    spec=json.loads(resposta)
    if not isinstance(spec,dict):
        raise ValueError("esperado objeto JSON")
    briefing=contexto["briefing"]
    if briefing.get("finalidade")=="agenda_jogo_unico" or (briefing.get("finalidade")=="agenda" and len(briefing.get("jogos",[]))==1):
        raise ValueError("encaminhar ao renderizador oficial jogo_unico")
    # Never let model replace provenance, purpose, or factual source metadata.
    spec["fotos"]=contexto["fotos"]
    spec["finalidade"]=briefing.get("finalidade","editorial")
    spec["fonte_dado"]=briefing.get("fonte_dado")
    spec["ilustrativo"]=bool(briefing.get("ilustrativo",False))
    spec["marca"]="logo"
    c.build(spec)
    return {"spec":spec,"status":"revisao_pendente","publicar":False}
