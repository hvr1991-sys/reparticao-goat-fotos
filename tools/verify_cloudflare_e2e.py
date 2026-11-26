"""Isolated real Cloudflare editorial + official photo + GOAT render. No backend writes."""
import copy, json, os, re, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image
from tools import designer_openrouter as designer, magnific_adapter, processar
from tools.openrouter_adapter import json_de
from tools.photo_policy import biblioteca_verified
from kit.render import render

OUT=Path("/tmp/goat-cloudflare-e2e")
OUT.mkdir(parents=True,exist_ok=True)
REPORT={"ok":False,"published":False,"backend_writes":0,"calls":[],"stages":{}}
def save():
    (OUT/"summary.json").write_text(json.dumps(REPORT,ensure_ascii=False,indent=2))
def stage(name,ok):
    REPORT["stages"][name]=bool(ok)
    save()
    print("STAGE",name,ok,flush=True)
def generate(parts,validator=None,temp=.3,**kwargs):
    original=list(parts)
    planning=getattr(validator,"__name__","")=="_validate_plan"
    for attempt in range(2):
        if len(REPORT["calls"])>=8 or sum(c.get("neurons",0) for c in REPORT["calls"])>=500:
            raise RuntimeError("Test call/consumption limit")
        content=[]
        for p in parts:
            if "text" in p: content.append({"type":"text","text":p["text"]})
            elif "inline_data" in p:
                i=p["inline_data"]
                content.append({"type":"image_url","image_url":{"url":"data:"+i["mime_type"]+";base64,"+i["data"]}})
            else: raise ValueError("Unsupported input")
        # One verified candidate: use its metadata for planning; review the actual photo separately.
        if planning:
            content="\n\n".join(p["text"] for p in content if p["type"]=="text")
            content+="\nHa exatamente uma foto oficial P001. Retorne JSON com brief, legenda, spec (tipo manchete, foto P001, titulo lista de objetos texto/amarelo, marca logo), foto_obrigatoria true, pendencia vazia, recurso_visual null. Titulo: uma ou duas linhas, cada uma com no maximo 22 caracteres contando espacos. Conte antes de responder."
        vision=not planning and any(p["type"]=="image_url" for p in content)
        model="@cf/meta/llama-4-scout-17b-16e-instruct" if vision else "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
        account=os.environ["CLOUDFLARE_ACCOUNT_ID"]
        assert re.fullmatch(r"[a-fA-F0-9]{32}",account)
        endpoint="https://api.cloudflare.com/client/v4/accounts/"+account+"/ai/v1/chat/completions"
        payload={"model":model,"messages":[{"role":"user","content":content}],"temperature":temp,"max_tokens":2500 if planning else 600,"response_format":{"type":"json_object"}}
        req=urllib.request.Request(endpoint,data=json.dumps(payload).encode(),headers={"Authorization":"Bearer "+os.environ["CLOUDFLARE_API_TOKEN"],"Content-Type":"application/json"})
        record={"model":model,"vision":vision,"images":0 if planning else sum(p["type"]=="image_url" for p in content),"phase":getattr(validator,"__name__","")}
        REPORT["calls"].append(record)
        try:
            with urllib.request.urlopen(req,timeout=90) as response:
                record["http"]=response.status
                data=json.load(response)
        except urllib.error.HTTPError as e:
            record["http"]=e.code
            save()
            raise RuntimeError("Cloudflare HTTP "+str(e.code)) from None
        usage=data.get("usage") or {}
        record["neurons"]=float(usage.get("neurons",0))
        choice=data["choices"][0]
        record["finish"]=choice.get("finish_reason")
        answer=choice["message"]["content"]
        save()
        try:
            if record["finish"]!="stop": raise ValueError("Incomplete")
            result=json_de(answer)
            if validator and validator(result) is False: raise ValueError("Contract")
            if planning:
                spec=result["spec"]
                if spec.get("tipo")!="manchete" or spec.get("foto")!="P001":
                    raise ValueError("Use tipo manchete e foto P001")
                lines=spec.get("titulo")
                if not isinstance(lines,list) or not 1<=len(lines)<=2 or any(not isinstance(x,dict) or not isinstance(x.get("texto"),str) or not 1<=len(x["texto"].strip())<=22 or type(x.get("amarelo",False)) is not bool for x in lines):
                    raise ValueError("Titulo exige 1 ou 2 linhas de ate 22 caracteres, contando espacos, com texto e amarelo booleano")
            record["valid"]=True
            save()
            return result
        except (ValueError,TypeError,KeyError) as e:
            record["valid"]=False
            record["validation_error"]=str(e)[:180] if not isinstance(e,json.JSONDecodeError) else "Invalid JSON syntax"
            record["response_chars"]=len(answer) if isinstance(answer,str) else 0
            save()
            if attempt: raise
            parts=original+[{"text":"Corrija o contrato: "+record["validation_error"]+". Devolva somente um objeto JSON completo, sem markdown. Respeite literalmente os dados fornecidos. Resposta anterior: "+str(answer)[:3500]}]
    raise RuntimeError("Invalid JSON")

def main():
    designer.gerar_json=generate
    today=datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    photo=next(p for p in biblioteca_verified(designer.ROOT) if p["arquivo"]=="fotos/399ca7c2-a821-42d7-8509-02ed455f5125-j112/1.jpg")
    photo={**photo,"id":"P001"}
    card={"id":"cloudflare-e2e-public","designer":"goat-designer","kind":"manchete","format":"Arte feed","league":"BRASILEIRAO","title":"Inter intensificou treinos na reta final do Brasileirão","pub_date":today,"due_date":today,"why":"Teste de produção com notícia oficial de arquivo, não notícia atual.","brief":"Notícia de arquivo: o Internacional trabalhou forte para a reta final do Brasileirão. Use somente esse fato, no passado ou com indicação de arquivo, sem datas de próximos jogos nem atletas. Manchete curta, foto oficial P001, logo GOAT, sem recurso visual novo, sem publicação. Legenda com crédito SC Internacional e indicação de arquivo. Não é amostra fictícia.","note":"Homologação sem publicação; fatos da manchete da matéria oficial de arquivo.","sources":[{"label":"SC Internacional","url":photo["pagina"]}],"_photo_candidates":[photo],"_lessons":[]}
    (OUT/"pauta.json").write_text(json.dumps({k:v for k,v in card.items() if not k.startswith("_")},ensure_ascii=False,indent=2))
    stage("official_source_and_photo",True)
    # Magnific auth only; this real photo dominates the composition and requires no synthetic background.
    try:
        magnific_adapter.verificar()
        stage("magnific_auth",True)
    except Exception as e:
        stage("magnific_auth",False)
        REPORT["magnific_error_type"]=type(e).__name__
    docs=[]
    fix=None
    for attempt in range(2):
        plan=designer.planejar(card,docs,fix)
        if plan.get("pendencia"): raise RuntimeError("Editorial plan returned a pending item")
        if plan.get("recurso_visual"): raise RuntimeError("Unnecessary new visual generation refused")
        spec=copy.deepcopy(plan["spec"])
        if spec.get("tipo")!="manchete" or spec.get("foto")!="P001": raise RuntimeError("Wrong format or photo")
        spec["marca"]="logo"
        spec.pop("fundo",None)
        card["legenda"]=plan["legenda"]
        (OUT/"plan.json").write_text(json.dumps(plan,ensure_ascii=False,indent=2))
        stage("editorial_plan",True)
        selected=designer._resolve_photos(spec,card["_photo_candidates"])
        assert len(selected)==1 and selected[0]["sha256"]==photo["sha256"]
        ok,reason=designer.foto_ok(designer.ROOT/photo["arquivo"],card)
        stage("photo_review",ok)
        if not ok: raise RuntimeError("Photo review rejected")
        png=OUT/("candidate-"+str(attempt+1)+".png")
        try:
            render(processar.resolver(spec),png)
        except SystemExit as e:
            fix=str(e)[:500]
            REPORT["render_rejection"]=fix
            stage("goat_render",False)
            continue
        with Image.open(png) as im: assert im.size==(1080,1350); im.verify()
        stage("goat_render",True)
        ok,reason=designer.revisar_arte(png,card,spec,docs)
        stage("art_review",ok)
        REPORT["art_review_reason"]=reason[:500]
        (OUT/"spec.json").write_text(json.dumps(spec,ensure_ascii=False,indent=2))
        if ok:
            (OUT/"arte-final.png").write_bytes(png.read_bytes())
            REPORT["ok"]=True
            break
        fix=reason
    save()
    return 0 if REPORT["ok"] else 1
if __name__=="__main__":
    try: status=main()
    except (Exception,SystemExit) as e:
        REPORT["error_type"]=type(e).__name__
        REPORT["error"]=str(e)[:300] if isinstance(e,(RuntimeError,SystemExit)) else "Technical or contract failure"
        status=1
    finally:
        save()
        print(json.dumps(REPORT,ensure_ascii=False),flush=True)
    raise SystemExit(status)
