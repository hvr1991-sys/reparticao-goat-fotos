"""OpenRouter adapter for the original GOAT designer interface.

No database access, no rendering changes, no paid fallback.
Search is deliberately not simulated: callers must supply verified sources.
"""
import json
import os
import urllib.request
import urllib.error

URL = "https://openrouter.ai/api/v1/chat/completions"


def gerar(partes, busca=False, temp=0.6):
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY ausente")
    model = os.environ.get("GOAT_FREE_MODEL", "openrouter/free")
    if model != "openrouter/free" and not model.endswith(":free"):
        raise ValueError("Modelo pago ou não autorizado")
    content = []
    for part in partes:
        if "text" in part:
            content.append({"type": "text", "text": part["text"]})
        elif "inline_data" in part:
            img = part["inline_data"]
            content.append({"type": "image_url", "image_url": {
                "url": "data:" + img["mime_type"] + ";base64," + img["data"]}})
        else:
            raise ValueError("Parte não suportada")
    if busca:
        content.append({"type": "text", "text": "Busca externa indisponível neste adaptador. Use apenas fontes verificadas fornecidas; não invente URLs ou fatos."})
    payload = {"model": model, "messages": [{"role": "user", "content": content}],
               "temperature": temp, "max_tokens": 5000}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as response:
        data = json.load(response)
    actual = data.get("model", "")
    if actual != "openrouter/free" and not actual.endswith(":free"):
        raise RuntimeError("Resposta de modelo não identificado como gratuito")
    usage = data.get("usage") or {}
    if float(usage.get("cost") or 0) > 0:
        raise RuntimeError("Custo inesperado; interromper execução")
    choices = data.get("choices") or []
    if not choices or choices[0].get("finish_reason") not in ("stop",):
        raise RuntimeError("Resposta incompleta ou indisponível")
    answer = (choices[0].get("message") or {}).get("content")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Resposta textual ausente")
    print("OpenRouter modelo:", actual, flush=True)
    return answer
