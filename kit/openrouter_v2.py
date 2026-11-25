"""Experimental free-only provider; no paid fallback or publication."""
import json
import os
import urllib.request
import urllib.error
import diretor_v2

MODEL = "openrouter/free"
URL = "https://openrouter.ai/api/v1/chat/completions"

class ProviderUnavailable(RuntimeError):
    pass

def gerar(contexto, *, transport=None):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ProviderUnavailable("OPENROUTER_API_KEY indisponivel")
    payload = {
        "model": MODEL,
        "messages": [
            {"role":"system","content":"Atue como diretor de arte GOAT. Retorne apenas um objeto JSON compacto conforme o contrato, sem explicacoes, sem raciocinio textual e sem repetir o contexto. Use apenas os elementos necessarios. As regras do gestor prevalecem sobre referencias e briefing. Nunca publique."},
            {"role":"user","content":json.dumps(contexto,ensure_ascii=False)}
        ],
        "max_tokens": 8000,
        "temperature": 0.2,
        "response_format": {"type":"json_object"},
        "provider": {"require_parameters":True}
    }
    req = urllib.request.Request(URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},method="POST")
    try:
        with (transport or urllib.request.urlopen)(req,timeout=90) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        raise ProviderUnavailable("OpenRouter HTTP "+str(exc.code)) from None
    except (OSError,ValueError) as exc:
        raise ProviderUnavailable("OpenRouter indisponivel ou resposta invalida") from None
    try:
        if not data.get("choices"):
            raise ValueError("provedor retornou zero choices")
        choice=data["choices"][0]
        if choice.get("finish_reason")=="length":
            raise ValueError("resposta truncada")
        text = choice["message"]["content"]
        if not isinstance(text,str):
            raise ValueError("conteudo ausente")
        text=text.strip()
        if text.startswith("```json") and text.endswith("```"):
            text=text[7:-3].strip()
        return diretor_v2.aceitar(text,contexto)
    except (KeyError,IndexError,TypeError,ValueError) as exc:
        # No raw provider output or credentials in public logs.
        if isinstance(exc,json.JSONDecodeError):
            reason=f"JSON invalido na linha {exc.lineno}, coluna {exc.colno}"
        elif isinstance(exc,ValueError):
            reason=str(exc)[:180] if contexto.get("briefing",{}).get("ilustrativo") else "validacao de campos"
        else:
            reason=type(exc).__name__
        raise ProviderUnavailable("composicao recusada: "+reason) from None
