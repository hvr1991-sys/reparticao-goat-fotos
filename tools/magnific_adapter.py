"""Recursos visuais pelo Magnific, usando a chave já configurada.
A API recebe apenas pedido de cenário/texture sem atletas, escudos, logos ou texto.
Fotos reais e os modelos oficiais da skill nunca são enviados para redesenho.
"""
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://api.magnific.com/v1"
MODEL = "flux-2-turbo"
TASK_PATH = "/ai/text-to-image/" + MODEL
INDEX = ROOT / "fotos" / "_magnific_tasks.json"
MAX_BYTES = 16 * 1024 * 1024
_created = 0


class MagnificUnavailable(RuntimeError):
    pass


def _request(path, payload=None):
    key = os.environ.get("MAGNIFIC_API_KEY", "")
    if not key:
        raise MagnificUnavailable("Magnific não configurado")
    req = urllib.request.Request(BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"x-magnific-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise MagnificUnavailable(f"Magnific indisponível (HTTP {e.code})") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise MagnificUnavailable("Magnific sem resposta válida; não reenviar geração automaticamente") from None


def verificar():
    """Consulta autenticada, sem geração nem download de stock."""
    data = _request("/resources?term=football&limit=1")
    if not isinstance(data.get("data"), (list, dict)):
        raise MagnificUnavailable("Resposta inesperada do Magnific")
    return {"provider": "Magnific", "authenticated": True, "generation_requested": False}


def consultar(task_id):
    import re
    if not re.fullmatch(r"[0-9a-f-]{36}", task_id):
        raise ValueError("Identificador de tarefa inválido")
    return _request(TASK_PATH + "/" + task_id).get("data", {})


def _read():
    if not INDEX.exists():
        return {}
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise MagnificUnavailable("Registro Magnific inválido; não criar outra geração") from None


def _save(state):
    INDEX.parent.mkdir(exist_ok=True)
    tmp = INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(INDEX)


def gerar_fundo(prompt, card_id, *, timeout=150):
    """Uma criação por identidade; retoma task_id, nunca repete POST incerto."""
    global _created
    if not isinstance(prompt, str) or not 12 <= len(prompt) <= 1600:
        raise ValueError("Descrição do cenário inválida")
    final_prompt = (
        "GOAT sports editorial background only. Dark charcoal #08080A, restrained "
        "yellow #FFD318 accents, photographic stadium atmosphere, natural light. "
        "No people, no athletes, no faces, no players, no shirts, no team crests, no "
        "sponsors, no logos, no letters, no typography, no numbers, no scoreboard. "
        "Leave generous dark negative space for deterministic typography. Scene: " + prompt
    )
    fingerprint = hashlib.sha256((MODEL + "\n" + str(card_id) + "\n" + final_prompt).encode()).hexdigest()
    state = _read()
    entry = state.get(fingerprint)
    if entry and entry.get("status") == "completed":
        asset = ROOT / entry["arquivo"]
        if asset.exists() and hashlib.sha256(asset.read_bytes()).hexdigest() == entry["sha256"]:
            return entry["arquivo"]
        # Re-download an existing task instead of charging again.
    if not entry:
        today = datetime.now(timezone.utc).date().isoformat()
        used_today = sum(x.get("created_at", "").startswith(today) for x in state.values())
        if _created >= int(os.environ.get("GOAT_MAX_VISUAL_PER_RUN", "2")) or used_today >= int(os.environ.get("GOAT_MAX_VISUAL_PER_DAY", "8")):
            raise MagnificUnavailable("Limite de gerações visuais alcançado; tarefa preservada")
        entry = {"status": "submitting", "created_at": datetime.now(timezone.utc).isoformat(), "model": MODEL}
        state[fingerprint] = entry
        _save(state)  # Persist before POST: an uncertain response is never blindly retried.
        _created += 1
        data = _request(TASK_PATH, {"prompt": final_prompt, "output_format": "png", "enable_safety_checker": True})
        task_id = (data.get("data") or {}).get("task_id")
        if not task_id:
            entry["status"] = "uncertain"
            _save(state)
            raise MagnificUnavailable("Magnific não devolveu identificador; geração não será repetida")
        entry.update({"task_id": task_id, "status": "pending"})
        _save(state)
    if not entry.get("task_id"):
        raise MagnificUnavailable("Criação anterior sem confirmação; verificar tarefa no Magnific")
    deadline = time.monotonic() + min(timeout, 180)
    while time.monotonic() < deadline:
        task = consultar(entry["task_id"])
        status = str(task.get("status", "")).upper()
        if status in ("FAILED", "ERROR", "CANCELLED"):
            entry["status"] = "failed"
            _save(state)
            raise MagnificUnavailable("Magnific não concluiu este recurso; não criar duplicata")
        if status == "COMPLETED":
            generated = task.get("generated") or []
            if not generated or not isinstance(generated[0], str):
                raise MagnificUnavailable("Magnific terminou sem uma imagem válida")
            url = generated[0]
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise MagnificUnavailable("Endereço de imagem inválido")
            # Signed provider CDN URLs are used only in memory, never written to repo/log.
            req = urllib.request.Request(url, headers={"User-Agent": "GOAT-Visual/2"})
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read(MAX_BYTES+1)
            if len(raw) > MAX_BYTES:
                raise MagnificUnavailable("Recurso visual excedeu o tamanho permitido")
            with Image.open(io.BytesIO(raw)) as im:
                im.verify()
            dest = ROOT / "fotos" / ("magnific-" + fingerprint[:20])
            dest.mkdir(parents=True, exist_ok=True)
            path = dest / "1.png"
            with Image.open(io.BytesIO(raw)) as im:
                im.convert("RGB").save(path, "PNG")
            relative = str(path.relative_to(ROOT))
            (dest / "meta.json").write_text(json.dumps({
                "tipo": "fundo_gerado", "provider": "Magnific", "model": MODEL,
                "task_id": entry["task_id"], "fotos": [],
                "uso": "cenário; não retrata pessoa, jogo ou fato real"
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            entry.update({"status": "completed", "arquivo": relative,
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            _save(state)
            return relative
        if status not in ("CREATED", "IN_PROGRESS", "PROCESSING", "PENDING"):
            raise MagnificUnavailable("Estado de tarefa Magnific desconhecido")
        time.sleep(4)
    raise MagnificUnavailable("Magnific ainda processando; próxima rodada consultará a mesma tarefa")


def preparar(plano, card):
    """Retorna arquivo apenas para um recurso visual explicitamente pedido no plano."""
    visual = plano.get("recurso_visual")
    if not visual:
        return None
    spec = plano.get("spec") or {}
    if spec.get("foto") or spec.get("fotos"):
        raise ValueError("O fundo gerado ficaria oculto pela foto; usar a foto real sem nova geração")
    if spec.get("tipo") in ("agenda", "jogo_unico"):
        # The original agenda stadium / real match photo have priority over generic backgrounds.
        raise ValueError("Agenda deve usar o modelo original e foto real; não gerar fundo substituto")
    if not isinstance(visual, dict) or visual.get("tipo") != "fundo":
        raise ValueError("Magnific só pode gerar cenário independente neste fluxo")
    return gerar_fundo(visual.get("prompt", ""), card["id"])
