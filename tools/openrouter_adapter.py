"""Complemento editorial gratuito: fontes fornecidas, JSON e revisão visual.
Magnific cuida da geração visual. Este adaptador nunca chama Gemini, busca paga,
modelo pago ou libera uma arte quando a revisão não respondeu.
"""
import json
import os
import time
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

BASE = "https://openrouter.ai/api/v1"
_catalog = None
_calls = 0
_last_call = 0.0
_blocked_until = 0.0
LAST_RESPONSE = {}
PREFERRED = ("particle-ai/particle-1:free", "nvidia/nemotron-3.5-super-vl:free", "inclusionai/ling-3.2-flash:free")


class ProviderUnavailable(RuntimeError):
    def __init__(self, message, status=None, retry_after=0):
        super().__init__(message)
        self.status, self.retry_after = status, retry_after


def _request(path, payload=None):
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise ProviderUnavailable("OpenRouter não configurado")
    req = urllib.request.Request(BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "X-Title": "Reparticao GOAT"})
    try:
        with urllib.request.urlopen(req, timeout=90 if payload else 25) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        # Never echo provider bodies, private prompts or request headers into CI.
        retry = e.headers.get("Retry-After", "")
        retry = min(86400, max(60, int(retry))) if retry.isdigit() else (3600 if e.code in (402, 429) else 0)
        raise ProviderUnavailable(f"OpenRouter indisponível (HTTP {e.code})", e.code, retry) from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise ProviderUnavailable("OpenRouter não respondeu de forma válida") from None


def _zero(value):
    try:
        return value is not None and Decimal(str(value)) == 0
    except InvalidOperation:
        return False


def models(vision=False, structured=False):
    global _catalog, _blocked_until
    if _catalog is None:
        try:
            _catalog = _request("/models").get("data", [])
        except ProviderUnavailable as e:
            _blocked_until = time.time() + (e.retry_after or 300)
            raise
    allowed = []
    for m in _catalog:
        ident = str(m.get("id", ""))
        price = m.get("pricing") or {}
        if not ident.endswith(":free") or "gemini" in ident.lower():
            continue
        if not all(_zero(price.get(x)) for x in ("prompt", "completion")):
            continue
        if vision and "image" not in (m.get("architecture") or {}).get("input_modalities", []):
            continue
        if structured and "response_format" not in m.get("supported_parameters", []):
            continue
        if m.get("context_length", 0) < 24000:
            continue
        allowed.append(ident)
    configured = os.environ.get("GOAT_FREE_MODEL", "").strip()
    if configured and configured != "openrouter/free":
        if configured not in allowed:
            raise ProviderUnavailable("Modelo solicitado sem preço zero ou capacidade necessária")
        return [configured]
    ranked = [m for m in PREFERRED if m in allowed]
    ranked += sorted(m for m in allowed if m not in ranked)
    if not ranked:
        raise ProviderUnavailable("Nenhum modelo gratuito compatível disponível")
    return ranked[:3]


def gerar(partes, busca=False, temp=0.6, *, structured=False):
    global _calls, _last_call, _blocked_until, LAST_RESPONSE
    if time.time() < _blocked_until:
        raise ProviderUnavailable("OpenRouter aguardando liberação do limite", 429, int(_blocked_until-time.time()))
    content = []
    for part in partes:
        if "text" in part:
            content.append({"type": "text", "text": str(part["text"])})
        elif "inline_data" in part:
            img = part["inline_data"]
            if img.get("mime_type") not in ("image/png", "image/jpeg", "image/webp"):
                raise ValueError("Formato visual não permitido")
            content.append({"type": "image_url", "image_url": {
                "url": "data:" + img["mime_type"] + ";base64," + img["data"]}})
        else:
            raise ValueError("Parte não suportada")
    if busca:
        content.append({"type": "text", "text": "Não há ferramenta de busca nesta chamada. Use exclusivamente as fontes fornecidas e verificadas. Não invente URLs ou fatos."})
    vision = any(p["type"] == "image_url" for p in content)
    error = None
    for model in models(vision, structured):
        if _calls >= int(os.environ.get("GOAT_MAX_LLM_CALLS", "45")):
            raise ProviderUnavailable("Limite de chamadas desta execução alcançado")
        wait = 3.1 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        payload = {"model": model, "messages": [{"role": "user", "content": content}],
                   "temperature": temp, "max_tokens": 5000,
                   "provider": {"require_parameters": True, "max_price": {"prompt": 0, "completion": 0}}}
        if structured:
            payload["response_format"] = {"type": "json_object"}
        _calls += 1
        _last_call = time.monotonic()
        try:
            data = _request("/chat/completions", payload)
        except ProviderUnavailable as e:
            error = e
            if e.status in (401, 402, 403, 429):
                _blocked_until = time.time() + (e.retry_after or 3600)
                raise
            continue
        actual = str(data.get("model", ""))
        if actual != model:
            raise ProviderUnavailable("Provedor respondeu com modelo diferente do solicitado")
        usage = data.get("usage") or {}
        if usage.get("cost") is not None and not _zero(usage["cost"]):
            _blocked_until = time.time() + 86400
            raise ProviderUnavailable("Custo inesperado: execução interrompida")
        choices = data.get("choices") or []
        if not choices or choices[0].get("finish_reason") != "stop":
            raise ProviderUnavailable("Resposta incompleta; não aprovar nem gravar conteúdo")
        answer = (choices[0].get("message") or {}).get("content")
        if not isinstance(answer, str) or not answer.strip():
            raise ProviderUnavailable("Resposta textual ausente")
        LAST_RESPONSE = {"model": actual, "cost": usage.get("cost"), "calls": _calls,
                         "vision": vision, "structured": structured}
        print("OpenRouter:", actual, "· visão" if vision else "· editorial", flush=True)
        return answer
    raise error or ProviderUnavailable("OpenRouter gratuito indisponível")


def json_de(text):
    raw = text.strip()
    fence = chr(96) * 3
    if raw.startswith(fence):
        raw = raw[len(fence):].lstrip()
        if raw.startswith("json"):
            raw = raw[4:].lstrip()
        if raw.endswith(fence):
            raw = raw[:-len(fence)].rstrip()
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("Esperado um objeto JSON")
    return result


def gerar_json(partes, validator=None, temp=0.3, **kwargs):
    """Uma reparação de formato no máximo; erro de provedor não é aprovação."""
    original = list(partes)
    for attempt in range(2):
        answer = gerar(partes, temp=temp, structured=True, **kwargs)
        try:
            result = json_de(answer)
            if validator and validator(result) is False:
                raise ValueError("Resposta não atende ao contrato")
            return result
        except (ValueError, TypeError, KeyError) as e:
            if attempt:
                raise ValueError("Resposta JSON inválida após uma correção") from e
            partes = original + [{"text": "A última resposta não atende ao contrato: " + str(e)[:220] +
                                  ". Corrija e devolva somente o objeto JSON solicitado. Resposta anterior: " + answer[:2500]}]
