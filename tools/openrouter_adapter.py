"""Complemento editorial gratuito: fontes fornecidas, JSON e revisão visual.
Magnific cuida da geração visual. Este adaptador nunca chama Gemini, busca paga,
modelo pago ou libera uma arte quando a revisão não respondeu.
"""
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE = "https://openrouter.ai/api/v1"
_catalog = None
_calls = 0
_last_call = 0.0
_blocked_until = 0.0
_blocked_scope = "unknown"
_blocked_status = 429
_quota = None
_quota_checked_at = 0.0
STATE_PATH = Path(os.environ.get("GOAT_PROVIDER_STATE", str(Path(__file__).resolve().parents[1] / ".goat-state" / "openrouter.json")))
LAST_RESPONSE = {}
PREFERRED = ("particle-ai/particle-1:free", "nvidia/nemotron-3.5-super-vl:free", "inclusionai/ling-3.2-flash:free")
LIMIT_SCOPES = frozenset({"upstream_provider_shared_pool", "openrouter_free_tier_per_minute",
                          "openrouter_free_tier_per_day", "unknown"})


class ProviderUnavailable(RuntimeError):
    def __init__(self, message, status=None, retry_after=0, scope="unknown", *,
                 code="provider_unavailable", diagnostics=None, finish_reason=None):
        super().__init__(message)
        self.status, self.retry_after = status, retry_after
        self.scope = scope if isinstance(scope, str) and scope in LIMIT_SCOPES else "unknown"
        self.code, self.diagnostics = code, diagnostics or {}
        self.finish_reason = finish_reason


class JSONContractError(ValueError):
    def __init__(self, code, diagnostics):
        super().__init__("Resposta JSON inválida após uma correção")
        self.code, self.diagnostics = code, diagnostics


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def _load_state():
    """Only operational counters and a not-before instant; never keys or prompts."""
    global _blocked_until, _blocked_scope, _blocked_status, _quota, _quota_checked_at
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(data, dict) or data.get("version") != 1:
        return
    deadline = data.get("blocked_until")
    if type(deadline) in (int, float) and math.isfinite(deadline) and _blocked_until < deadline < time.time() + 31536000:
        _blocked_until = deadline
        scope = data.get("limit_scope")
        _blocked_scope = scope if isinstance(scope, str) and scope in LIMIT_SCOPES else "unknown"
        status = data.get("http_status")
        _blocked_status = status if type(status) is int and 100 <= status <= 599 else None
    checked = data.get("quota_checked_at")
    quota = data.get("free_daily_requests")
    if type(checked) in (int, float) and math.isfinite(checked) and _quota_checked_at < checked <= time.time() + 60:
        if isinstance(quota, dict) and all(type(quota.get(k)) is int and 0 <= quota[k] <= 100000000 for k in ("used", "limit", "remaining")):
            _quota = {k: quota[k] for k in ("used", "limit", "remaining")}
            _quota_checked_at = checked


def _save_state():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "blocked_until": _blocked_until,
            "limit_scope": _blocked_scope, "http_status": _blocked_status,
            "quota_checked_at": _quota_checked_at, "free_daily_requests": _quota}
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(STATE_PATH)


def _remember_block(error):
    global _blocked_until, _blocked_scope, _blocked_status
    _load_state()
    deadline = time.time() + (error.retry_after or (3600 if error.status in (401, 402, 403, 429) else 300))
    if deadline >= _blocked_until:
        _blocked_until, _blocked_scope, _blocked_status = deadline, error.scope, error.status
    error.retry_after = max(1, math.ceil(_blocked_until - time.time()))
    error.retry_at = _iso(_blocked_until)
    error.scope, error.status = _blocked_scope, _blocked_status
    _save_state()


def _openrouter_status(*, refresh=False, force=False):
    """Read free quota without inference and retain waits across worker restarts."""
    global _quota, _quota_checked_at
    _load_state()
    now = time.time()
    same_day = (_quota_checked_at > 0 and int(_quota_checked_at // 86400) == int(now // 86400))
    if refresh and (force or now >= _blocked_until) and (force or not same_day or now - _quota_checked_at >= 300):
        try:
            response = _request("/key")
            data = response.get("data", {}) if isinstance(response, dict) else {}
            raw = data.get("free_model_daily_requests") if isinstance(data, dict) else None
            # Discard the rest of /key: no labels, balances, account or key IDs.
            _quota = ({k: raw[k] for k in ("used", "limit", "remaining")}
                      if isinstance(raw, dict) and all(type(raw.get(k)) is int and 0 <= raw[k] <= 100000000 for k in ("used", "limit", "remaining")) else None)
            _quota_checked_at = time.time()
            if _quota and _quota["limit"] > 0 and _quota["remaining"] == 0:
                tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
                _remember_block(ProviderUnavailable("Cota gratuita diária aguardando renovação", 429,
                    math.ceil(tomorrow.timestamp() - time.time()), "openrouter_free_tier_per_day"))
            _save_state()
        except ProviderUnavailable as error:
            _remember_block(error)
    waiting = time.time() < _blocked_until
    result = {"status": "waiting_provider" if waiting else ("quota_available" if _quota else "quota_unknown"),
              "inference_checked": False, "free_only": True}
    if _quota_checked_at:
        result["checked_at"] = _iso(_quota_checked_at)
    if _quota is not None:
        result["free_daily_requests"] = dict(_quota)
    if waiting:
        result.update(http_status=_blocked_status, limit_scope=_blocked_scope,
                      retry_after=max(1, math.ceil(_blocked_until - time.time())), retry_at=_iso(_blocked_until))
    elif _calls >= int(os.environ.get("GOAT_MAX_LLM_CALLS", "45")):
        result.update(status="waiting_run_budget", code="call_budget", retry_after=3600)
    return result


def _require_openrouter():
    state = _openrouter_status()
    if state["status"] == "waiting_provider":
        error = ProviderUnavailable("OpenRouter aguardando liberação do limite", state.get("http_status"),
                                    state["retry_after"], state["limit_scope"], code="retry_wait")
        error.retry_at = state["retry_at"]
        raise error
    if state["status"] == "waiting_run_budget":
        raise ProviderUnavailable("Limite de chamadas deste plantão; retomada no próximo", retry_after=3600, code="call_budget")


def _retry_delay(headers, status):
    """Honor both server hints; X-RateLimit-Reset is Unix milliseconds."""
    now, delays = time.time(), []
    retry = str(headers.get("Retry-After", ""))[:128]
    try:
        delays.append(int(retry) if retry.isdigit() else parsedate_to_datetime(retry).timestamp() - now)
    except (ValueError, TypeError, OverflowError):
        pass
    reset = str(headers.get("X-RateLimit-Reset", ""))[:128]
    if reset.isdigit():
        delays.append(int(reset) / 1000 - now)
    return max(0, math.ceil(max(delays))) if delays else (3600 if status in (402, 429) else 0)


def _error_scope(error):
    # Parse at most 32 KiB, keep only a fixed enum, and discard all provider text.
    try:
        body = json.loads(error.read(32768))
        metadata = body.get("error", {}).get("metadata", {})
        scope = metadata.get("limit_source")
        if scope == "openrouter_free_tier_daily":
            scope = "openrouter_free_tier_per_day"
        return scope if isinstance(scope, str) and scope in LIMIT_SCOPES else "unknown"
    except (OSError, ValueError, TypeError, AttributeError, RecursionError):
        return "unknown"
    finally:
        error.close()


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
        retry = _retry_delay(e.headers or {}, e.code)
        scope = _error_scope(e)
        raise ProviderUnavailable(f"OpenRouter indisponível (HTTP {e.code})", e.code, retry, scope) from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise ProviderUnavailable("OpenRouter não respondeu de forma válida") from None


def _zero(value):
    try:
        return value is not None and Decimal(str(value)) == 0
    except InvalidOperation:
        return False


def models(vision=False, structured=False, schema=False):
    global _catalog, _blocked_until, _blocked_scope, _blocked_status
    if _catalog is None:
        try:
            _catalog = _request("/models").get("data", [])
        except ProviderUnavailable as e:
            _remember_block(e)
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
        if schema and "structured_outputs" not in m.get("supported_parameters", []):
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


def _gerar_openrouter(partes, busca=False, temp=0.6, *, structured=False, schema=None):
    global _calls, _last_call, _blocked_until, _blocked_scope, _blocked_status, LAST_RESPONSE
    LAST_RESPONSE = {}
    _require_openrouter()
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
    candidates = models(vision, structured, schema is not None)
    if _calls >= int(os.environ.get("GOAT_MAX_LLM_CALLS", "45")):
        raise ProviderUnavailable("Limite de chamadas desta execução alcançado", code="call_budget")
    wait = 3.1 - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    # One request: OpenRouter performs the documented provider/model fallbacks.
    output_budget = max(2048, min(16384, int(os.environ.get("GOAT_MAX_OUTPUT_TOKENS", "12000"))))
    payload = {"models": candidates, "messages": [{"role": "user", "content": content}],
               "temperature": temp, "max_tokens": output_budget,
               "provider": {"require_parameters": True, "max_price": {"prompt": 0, "completion": 0}}}
    if schema is not None:
        payload["response_format"] = {"type": "json_schema", "json_schema": {
            "name": "goat_response", "strict": True, "schema": schema}}
    elif structured:
        payload["response_format"] = {"type": "json_object"}
    selected = [m for m in (_catalog or []) if m.get("id") in candidates]
    # Structured editorial decisions need visible JSON, not an unbounded hidden
    # reasoning budget. Disable optional reasoning only when every candidate's
    # current catalog metadata explicitly permits it. Vision keeps its defaults.
    if not vision and selected and all(
            "reasoning" in m.get("supported_parameters", [])
            and (m.get("reasoning") or {}).get("mandatory") is False for m in selected):
        payload["reasoning"] = {"enabled": False, "exclude": True}
    _calls += 1
    _last_call = time.monotonic()
    try:
        data = _request("/chat/completions", payload)
    except ProviderUnavailable as e:
        _remember_block(e)
        if e.status == 429:
            # A read-only quota check distinguishes daily exhaustion from a
            # provider pool limit. It never retries the failed inference.
            state = _openrouter_status(refresh=True, force=True)
            e.retry_after = state.get("retry_after", e.retry_after)
            e.retry_at = state.get("retry_at", getattr(e, "retry_at", None))
            e.scope = state.get("limit_scope", e.scope)
        raise
    actual = str(data.get("model", ""))
    if actual not in candidates:
        raise ProviderUnavailable("Provedor respondeu com modelo fora da lista autorizada", code="unexpected_model")
    usage = data.get("usage") or {}
    if not _zero(usage.get("cost")):
        error = ProviderUnavailable("Custo zero não confirmado: execução interrompida", retry_after=86400, code="unexpected_cost")
        _remember_block(error)
        raise error
    choices = data.get("choices") or []
    finish = choices[0].get("finish_reason") if choices else "unknown"
    if finish not in ("stop", "length", "content_filter", "tool_calls", "error"):
        finish = "unknown"
    answer = (choices[0].get("message") or {}).get("content") if choices else None
    diagnostics = {"model": actual, "finish_reason": finish,
                   "response_chars": len(answer) if isinstance(answer, str) else 0}
    for key, value in (("completion_tokens", usage.get("completion_tokens")),
                       ("reasoning_tokens", (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"))):
        if type(value) is int and value >= 0:
            diagnostics[key] = value
    if finish != "stop":
        raise ProviderUnavailable("Resposta incompleta; não aprovar nem gravar conteúdo",
                                  code="incomplete_response", diagnostics=diagnostics, finish_reason=finish)
    if not isinstance(answer, str) or not answer.strip():
        raise ProviderUnavailable("Resposta textual ausente", code="empty_response", diagnostics=diagnostics)
    LAST_RESPONSE = {"model": actual, "cost": usage.get("cost"), "calls": _calls,
                     "vision": vision, "structured": structured}
    print("OpenRouter:", actual, "· visão" if vision else "· editorial", flush=True)
    return answer


# Router: existing Groq Free organization first; OpenRouter free as independent backup.
try:
    from . import groq_adapter
except ImportError:
    import groq_adapter

def provider_status(*, refresh=False, force=False):
    if groq_adapter.available():
        return {"status":"quota_available","provider":"groq","free_only":True,
                "inference_checked":False,"openrouter":_openrouter_status(refresh=False),
                "groq_text":bool(groq_adapter.candidates()),"groq_vision":bool(groq_adapter.candidates(True))}
    state = _openrouter_status(refresh=refresh, force=force)
    if groq_adapter.configured() and state["status"].startswith("waiting_"):
        retry = min(state.get("retry_after",300),groq_adapter.next_retry())
        state.update(provider="groq/openrouter",retry_after=retry,retry_at=_iso(time.time()+retry),limit_scope="unknown")
    return state

def require_available():
    if groq_adapter.available():
        return
    state = provider_status()
    if state["status"].startswith("waiting_"):
        error = ProviderUnavailable("Provedores gratuitos aguardando liberação",state.get("http_status"),
                                    state.get("retry_after",300),state.get("limit_scope","unknown"),code="retry_wait")
        error.retry_at = state.get("retry_at")
        raise error

def gerar(partes, busca=False, temp=0.6, *, structured=False, schema=None):
    global LAST_RESPONSE
    vision = any("inline_data" in p for p in partes)
    errors = []
    request_parts = list(partes)
    if busca:
        request_parts.append({"text":"Use somente as fontes fornecidas e verificadas. Não invente URLs ou fatos."})
    if sum("inline_data" in p for p in partes) <= 3:
        for model in groq_adapter.candidates(vision):
            try:
                answer = groq_adapter.request(model,request_parts,temp=temp,schema=schema,
                    structured=structured,error_type=ProviderUnavailable)
                LAST_RESPONSE = {"model":model,"provider":"groq","vision":vision,"structured":structured}
                return answer
            except ProviderUnavailable as error:
                errors.append(error)
                print(str(error),flush=True)
    try:
        return _gerar_openrouter(partes,busca=busca,temp=temp,structured=structured,schema=schema)
    except ProviderUnavailable as error:
        # Preserve the most actionable failure, not an unrelated daily wait.
        if errors and error.code == "retry_wait":
            raise errors[-1] from None
        raise

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


def gerar_json(partes, validator=None, temp=0.3, schema=None, **kwargs):
    """Uma reparação de formato no máximo; erro de provedor não é aprovação."""
    original = list(partes)
    for attempt in range(2):
        try:
            answer = gerar(partes, temp=temp, structured=True, schema=schema, **kwargs)
        except ProviderUnavailable as e:
            if attempt or e.code != "incomplete_response" or e.finish_reason != "length":
                raise
            partes = original + [{"text": "A saída anterior atingiu o limite. Retorne somente o JSON final completo, "
                "com campos concisos e todos os dados obrigatórios. Não acrescente explicações fora do JSON. "
                "Preserve fontes, datas e pendências; não invente conteúdo para completar campos."}]
            continue
        try:
            result = json_de(answer)
            if validator and validator(result) is False:
                raise ValueError("Resposta não atende ao contrato")
            return result
        except (ValueError, TypeError, KeyError) as e:
            if attempt:
                diagnostics = {"response_chars": len(answer)}
                code = "invalid_json" if isinstance(e, json.JSONDecodeError) else "invalid_contract"
                if isinstance(e, json.JSONDecodeError):
                    diagnostics.update(json_line=e.lineno, json_column=e.colno)
                else:
                    diagnostics["validator_sha256"] = hashlib.sha256(str(e).encode()).hexdigest()
                raise JSONContractError(code, diagnostics) from e
            partes = original + [{"text": "A última resposta não atende ao contrato: " + str(e)[:220] +
                                  ". Corrija e devolva somente o objeto JSON solicitado. Resposta anterior: " + answer[:12000]}]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Disponibilidade gratuita, sem chamadas de geração")
    parser.add_argument("--status", type=Path, required=True)
    args = parser.parse_args()
    status = provider_status(refresh=True)
    args.status.parent.mkdir(parents=True, exist_ok=True)
    args.status.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False), flush=True)
