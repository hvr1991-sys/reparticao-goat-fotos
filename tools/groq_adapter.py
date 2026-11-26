"""Groq fallback for GOAT. Use only the existing Free-tier organization.
No paid-tier switching, tool calls, secret logging, or silent image omission.
"""
import json, math, os, time, urllib.request, urllib.error
from pathlib import Path

MODELS_TEXT = ("openai/gpt-oss-20b", "openai/gpt-oss-120b")
MODEL_VISION = "qwen/qwen3.8-27b"
STATE = Path(os.environ.get("GOAT_GROQ_STATE", ".goat-state/groq.json"))
BASE = "https://api.groq.com/openai/v1"
BLOCKS = {}
CALLS = 0

def configured():
    return bool(os.environ.get("GROQ_API_KEY")) and os.environ.get("GOAT_GROQ_FREE_ONLY") == "1"

def load():
    try:
        saved = json.loads(STATE.read_text())
        for name, until in saved.items():
            if name in (*MODELS_TEXT, MODEL_VISION) and type(until) in (int,float) and math.isfinite(until):
                BLOCKS[name] = max(BLOCKS.get(name, 0), until)
    except (OSError, ValueError, TypeError, AttributeError):
        pass

def block(name, seconds):
    BLOCKS[name] = time.time() + max(5, min(int(seconds), 86400))
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(BLOCKS))
    tmp.chmod(0o600)
    tmp.replace(STATE)

def candidates(vision=False):
    load()
    if not configured():
        return []
    if CALLS >= int(os.environ.get("GOAT_GROQ_MAX_CALLS", "30")):
        return []
    names = (MODEL_VISION,) if vision else MODELS_TEXT
    return [n for n in names if BLOCKS.get(n, 0) <= time.time()]

def available():
    return bool(candidates() or candidates(True))

def next_retry():
    load()
    delays = [v-time.time() for v in BLOCKS.values() if v > time.time()]
    return max(5, math.ceil(min(delays))) if delays else 300

def request(model, parts, *, temp, schema, structured, error_type):
    global CALLS
    images = sum("inline_data" in p for p in parts)
    if images > 3:
        raise error_type("Groq: limite visual de três imagens; revisão integral preservada", code="provider_unavailable")
    messages = []
    for part in parts:
        if "text" in part:
            messages.append({"type":"text","text":str(part["text"])})
        elif "inline_data" in part:
            image = part["inline_data"]
            if image.get("mime_type") not in ("image/png","image/jpeg","image/webp"):
                raise ValueError("Formato de imagem inválido")
            messages.append({"type":"image_url","image_url":{"url":"data:"+image["mime_type"]+";base64,"+image["data"]}})
        else:
            raise ValueError("Parte não suportada")
    # Text-only models get a plain string; multimodal requests preserve ordering.
    content = messages if images else "\n".join(p["text"] for p in messages)
    if schema is not None:
        instruction = "\nContrato JSON obrigatório:\n"+json.dumps(schema,ensure_ascii=False)
        if images:
            content.append({"type":"text","text":instruction})
        else:
            content += instruction
    if structured and not images:
        content += "\nRetorne exclusivamente um objeto JSON válido."
    if structured and images:
        content.append({"type":"text","text":"Retorne exclusivamente um objeto JSON válido."})
    # JSON-object mode plus the original role validators; complex anyOf schemas
    # are not assumed to be supported by every provider.
    payload = {"model":model,"messages":[{"role":"user","content":content}],
               "temperature":temp,"max_completion_tokens":int(os.environ.get("GOAT_GROQ_OUTPUT_TOKENS","2500"))}
    if structured:
        payload["response_format"] = {"type":"json_object"}
    if model.startswith("openai/gpt-oss"):
        payload["reasoning_effort"] = "low"
    elif model == MODEL_VISION:
        payload["reasoning_effort"] = "none"
    req = urllib.request.Request(BASE+"/chat/completions",data=json.dumps(payload).encode(),
        headers={"Authorization":"Bearer "+os.environ["GROQ_API_KEY"],"Content-Type":"application/json"})
    CALLS += 1
    try:
        with urllib.request.urlopen(req,timeout=90) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            retry = int(float(exc.headers.get("retry-after","60")))
        except (ValueError, TypeError):
            retry = 60
        exc.close()
        if status in (401,403,404):
            retry = 3600
        elif status == 413:
            retry = 5
        elif status != 429:
            retry = 60
        # Never log provider response bodies or credentials.
        if status != 400 and status != 413:
            block(model,retry)
        raise error_type(f"Groq indisponível (HTTP {status})",status,retry) from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        block(model,60)
        raise error_type("Groq não respondeu de forma válida",retry_after=60) from None
    if data.get("model") != model:
        raise error_type("Groq retornou modelo não autorizado",code="unexpected_model")
    choices = data.get("choices") or []
    choice = choices[0] if choices else {}
    answer = (choice.get("message") or {}).get("content")
    if choice.get("finish_reason") != "stop":
        raise error_type("Resposta Groq incompleta",code="incomplete_response",finish_reason=choice.get("finish_reason"))
    if not isinstance(answer,str) or not answer.strip():
        raise error_type("Resposta Groq vazia",code="empty_response")
    print("Groq:",model,"· visão" if images else "· editorial",flush=True)
    return answer
