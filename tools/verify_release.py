"""Homologação consolidada com provedores reais e nenhuma escrita no Supabase.

Sem --live: verifica os arquivos originais e renderiza as quatro prévias.
Com --live: consulta Magnific sem gerar novamente e usa OpenRouter real para
planejamento, seleção/revisão da foto e revisão da arte ilustrativa.
Em main: lê contexto original uma vez e roda a edição dos agentes em dry_run.
Somente contagens, hashes e a fixture pública controlada vão para o artifact.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from kit.verify_renderer import main as verify_renderer
from kit.render import render
from tools import designer_openrouter as designer
from tools import editorial_round, magnific_adapter, openrouter_adapter, processar
from tools.photo_policy import biblioteca_verified

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "kit" / "skill-original"
PREVIOUS_TASK = "0fa0735a-9e87-47c5-ac2a-330cbb83e7ec"
PHOTO = "fotos/399ca7c2-a821-42d7-8509-02ed455f5125-j112/1.jpg"
HEADLINES = ["SUA PAIXÃO", "PELO JOGO"]
ERROR_CODES = frozenset({"provider_unavailable", "incomplete_response", "unexpected_model",
    "unexpected_cost", "empty_response", "call_budget", "retry_wait", "invalid_json", "invalid_contract"})
FINISH_REASONS = frozenset({"stop", "length", "content_filter", "tool_calls", "error", "unknown"})


class ReleaseFailure(RuntimeError):
    """A bounded message that may be included in a public verification artifact."""


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _provider_record(phase):
    actual = openrouter_adapter.LAST_RESPONSE
    return {"phase": phase, **{key: actual.get(key) for key in ("model", "cost", "calls", "vision", "structured")}}


def _safe_error_metadata(source):
    """Only provider enums, counts, a catalog model ID and a validator hash are public."""
    get = source.get if isinstance(source, dict) else lambda key, default=None: getattr(source, key, default)
    result = {}
    code = get("code")
    if isinstance(code, str) and code in ERROR_CODES:
        result["code"] = code
    finish = get("finish_reason")
    if isinstance(finish, str) and finish in FINISH_REASONS:
        result["finish_reason"] = finish
    raw = get("diagnostics")
    diagnostics = {}
    if isinstance(raw, dict):
        for key in ("completion_tokens", "reasoning_tokens", "response_chars", "json_line", "json_column"):
            value = raw.get(key)
            if type(value) is int and 0 <= value <= 1_000_000_000:
                diagnostics[key] = value
        value = raw.get("finish_reason")
        if isinstance(value, str) and value in FINISH_REASONS:
            diagnostics["finish_reason"] = value
        value = raw.get("model")
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}/[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
            diagnostics["model"] = value
        value = raw.get("validator_sha256")
        if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
            diagnostics["validator_sha256"] = value
    if diagnostics:
        result["diagnostics"] = diagnostics
    return result


def _public_error(error, stage=None):
    # Never emit arbitrary exception text: validation errors can include private data.
    # Renderer fixtures contain only the public controlled sample and source assets.
    if stage == "renderer":
        return {"type": type(error).__name__, "reason": str(error)[:2000],
                "error_sha256": digest(str(error))}
    if isinstance(error, ReleaseFailure):
        return {"type": type(error).__name__, "reason": str(error)[:320]}
    if isinstance(error, openrouter_adapter.ProviderUnavailable):
        return {"type": type(error).__name__, "reason": "OpenRouter gratuito indisponível; nenhuma aprovação presumida",
                "http_status": error.status, "retry_after": error.retry_after, "scope": error.scope,
                **_safe_error_metadata(error)}
    if isinstance(error, magnific_adapter.MagnificUnavailable):
        code = re.search(r"HTTP (\d{3})", str(error))
        return {"type": type(error).__name__, "reason": "Consulta Magnific indisponível; nenhuma nova geração enviada",
                "http_status": int(code[1]) if code else None}
    return {"type": type(error).__name__, "reason": "Falha técnica ou de contrato; etapa não homologada",
            "error_sha256": digest(str(error)), **_safe_error_metadata(error)}


def magnific_check(summary):
    auth = magnific_adapter.verificar()
    task = magnific_adapter.consultar(PREVIOUS_TASK)
    state = str(task.get("status", "")).upper()
    summary["magnific"] = {**auth, "existing_task_status": state,
                           "existing_task_has_result": bool(task.get("generated")),
                           "new_generations": 0, "stock_downloads": 0}
    if state != "COMPLETED" or not task.get("generated"):
        raise ReleaseFailure("A tarefa Magnific previamente concluída não retornou resultado disponível")


def _controlled_card(photo):
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    publication = today + timedelta(days=3)
    return {
        "id": "11111111-1111-4111-8111-111111111111",
        "designer": "goat-designer-brasil", "stage": "producao", "kind": "manchete",
        "format": "Arte feed", "league": "GERAL", "title": "SUA PAIXÃO / PELO JOGO",
        "pub_date": publication.isoformat(), "due_date": (publication - timedelta(days=1)).isoformat(),
        "why": "Prévia ilustrativa de composição, sem notícia, citação ou estatística real.",
        "brief": (
            "AMOSTRA TÉCNICA ILUSTRATIVA. Use tipo manchete, foto P001 (foto real de treino, fonte SC Internacional), "
            "ilustrativo:true, marca:logo. Título ditado, manter literalmente duas linhas: SUA PAIXÃO / PELO JOGO. "
            "Nenhum jogo, horário, competição, placar, nome de atleta ou fala atribuída. "
            "Sem apoio, sobretítulo, números ou dados extras. Não gerar fundo nem outro recurso visual. "
            "Use a fotografia real dominante; foco sugerido 38% 30%; texto abaixo do rosto. "
            "Liberdade de composição dentro da skill, Barlow Condensed, amarelo oficial. "
            "Legenda neutra de exemplo com crédito SC Internacional. Não publicar."
        ),
        "note": "Selo DADOS ILUSTRATIVOS obrigatório. Nenhum dado do modelo de referência pode virar fato desta peça.",
        "sources": [{"label": photo["credito"], "url": photo["pagina"]}],
        "_photo_candidates": [{**photo, "id": "P001"}], "_lessons": [],
    }


def _check_fixture_plan(plan):
    spec = plan.get("spec") or {}
    lines = spec.get("titulo")
    actual = [line.get("texto") if isinstance(line, dict) else line for line in lines] if isinstance(lines, list) else []
    if actual != HEADLINES:
        raise ReleaseFailure("O planejamento alterou o título literal da fixture")
    if spec.get("tipo") != "manchete" or spec.get("foto") != "P001" or spec.get("ilustrativo") is not True:
        raise ReleaseFailure("O planejamento não respeitou formato, foto autorizada ou selo ilustrativo")
    if plan.get("pendencia") or plan.get("recurso_visual"):
        raise ReleaseFailure("O planejamento retornou pendência ou geração desnecessária para a fixture")
    if plan.get("foto_obrigatoria") is not True or spec.get("marca", "logo") != "logo":
        raise ReleaseFailure("O planejamento não preservou a foto real e a marca oficial")
    if any(spec.get(key) for key in ("jogo", "numeros", "apoio", "sobretitulo", "fundo")):
        raise ReleaseFailure("O planejamento acrescentou conteúdo fora da fixture autorizada")
    if any(isinstance(line, dict) and type(line.get("amarelo", False)) is not bool for line in lines):
        raise ReleaseFailure("Cor do título não foi expressa como booleano literal")
    return spec


def designer_check(output, summary):
    photo = next((item for item in biblioteca_verified(ROOT) if item["arquivo"] == PHOTO), None)
    if photo is None:
        raise ReleaseFailure("A foto oficial da fixture não passou na conferência de origem e integridade")
    card = _controlled_card(photo)
    # No private agent prompts are used or persisted in this publicly reproducible fixture.
    docs = []
    plan = designer.planejar(card, docs)
    summary["provider_calls"].append(_provider_record("fixture_plan"))
    card["legenda"] = plan["legenda"]
    spec = copy.deepcopy(_check_fixture_plan(plan))
    spec["marca"] = "logo"
    selected = designer._resolve_photos(spec, card["_photo_candidates"])
    if len(selected) != 1 or selected[0]["sha256"] != photo["sha256"]:
        raise ReleaseFailure("O plano resolveu uma fotografia diferente da autorizada")
    ok_photo, photo_reason = designer.foto_ok(ROOT / photo["arquivo"], card)
    summary["provider_calls"].append(_provider_record("fixture_photo_review"))
    summary["designer"] = {"photo_sha256": photo["sha256"], "photo_review_ok": ok_photo,
                           "photo_review_reason": photo_reason[:400], "art_review_ok": False,
                           "agent_private_context_used": False, "supabase_writes": 0, "published": False}
    if ok_photo is not True:
        raise ReleaseFailure("A revisão visual real reprovou a fotografia da fixture; consultar motivo no resumo")
    png = output / "live-post.png"
    geometry = render(processar.resolver(spec), png)
    summary["designer"]["layout"] = geometry
    approved_bytes = digest(png.read_bytes())
    ok_art, art_reason = designer.revisar_arte(png, card, spec, docs)
    summary["provider_calls"].append(_provider_record("fixture_art_review"))
    summary["designer"].update(art_review_ok=ok_art, art_review_reason=art_reason[:500],
                               image_sha256=approved_bytes)
    if digest(png.read_bytes()) != approved_bytes:
        raise ReleaseFailure("A imagem mudou durante a revisão final")
    # Whitelist the public controlled fixture. Never persist arbitrary model fields.
    allowed = ("tipo", "foto", "titulo", "ilustrativo", "marca", "foco", "alinhamento", "layout", "deslocar_y", "tamanho_titulo")
    _save(output / "live-plan.json", {"fixture": "amostra técnica controlada; dados ilustrativos", "legenda": plan["legenda"],
        "spec": {key: spec[key] for key in allowed if key in spec},
        "photo_sha256": photo["sha256"], "photo_review_ok": ok_photo, "art_review_ok": ok_art})
    if ok_art is not True:
        raise ReleaseFailure("A revisão visual real reprovou a arte da fixture; consultar motivo no resumo")


def private_context_check(summary):
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        summary["original_agents"] = {"status": "skipped_branch_isolation", "context_read": False,
            "supabase_writes": 0, "note": "A branch não acessa o contexto privado; a rodada dos nove cargos é exigida em main."}
        return
    # This is the only Supabase operation allowed by this program.
    snapshot = processar.api("contexto")
    if not isinstance(snapshot, dict):
        raise ReleaseFailure("O backend não retornou contexto original válido")
    docs = {item.get("id"): item.get("content") for item in snapshot.get("docs", []) if isinstance(item, dict)}
    if any(not isinstance(docs.get(agent), str) or not docs[agent].strip() for agent in editorial_round.AGENTS):
        raise ReleaseFailure("As instruções originais dos nove cargos não estão completas")
    context_summary = {
        "status": "running_dry_run", "context_read": True, "dry_run": True, "supabase_writes": 0,
        "docs_count": len(editorial_round.AGENTS),
        "doc_sha256": {agent: digest(docs[agent].encode()) for agent in editorial_round.AGENTS},
        "lessons_count": len(snapshot.get("lessons", [])), "lessons_sha256": digest(snapshot.get("lessons", [])),
        "cards_count": len(snapshot.get("cards", [])), "news_count": len(snapshot.get("news", [])),
    }
    summary["original_agents"] = context_summary

    def real_generator(parts, validator=None, temp=.3, **kwargs):
        answer = openrouter_adapter.gerar_json(parts, validator=validator, temp=temp, **kwargs)
        summary["provider_calls"].append(_provider_record("original_agents_dry_run"))
        return answer

    def no_backend_writes(action, body=None):
        # executar receives a snapshot; no additional backend action is necessary.
        raise ReleaseFailure("A rodada em dry_run tentou executar uma operação de backend")

    result = editorial_round.executar(snapshot, transport=no_backend_writes, dry_run=True, generator=real_generator)
    statuses = {}
    for agent in result.get("agents", []):
        state = str(agent.get("status", "unknown"))
        statuses[state] = statuses.get(state, 0) + 1
    errors = result.get("errors", [])
    # No action payloads, request descriptions, story titles or model prompts leave memory.
    context_summary.update(status="passed" if result.get("ok") is True else "failed",
        agents_count=len(result.get("agents", [])), agent_status_counts=statuses,
        proposed_actions_count=len(result.get("actions", [])), errors_count=len(errors),
        error_fingerprints=[{"agent": item.get("agent") if item.get("agent") in editorial_round.AGENTS else "unknown",
                             "reason_sha256": digest(str(item.get("reason", ""))),
                             **_safe_error_metadata(item)} for item in errors])
    if result.get("ok") is not True or len(result.get("agents", [])) != 9:
        raise ReleaseFailure("A rodada real em memória dos cargos originais apresentou pendências; ativação bloqueada")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--editorial-only", action="store_true",
                        help="Confere somente os cargos originais; a parte visual exige evidência separada.")
    parser.add_argument("--output", type=Path, default=Path("/tmp/goat-release-verification"))
    args = parser.parse_args()
    if args.editorial_only and (not args.live or os.environ.get("GITHUB_REF") != "refs/heads/main"):
        parser.error("A conferência editorial isolada exige --live e a branch main autenticada")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = {"ok": False, "live_requested": args.live,
        "started_at": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(),
        "commit": os.environ.get("GITHUB_SHA"), "branch": os.environ.get("GITHUB_REF_NAME"),
        "skill_sha256": digest((SKILL / "SKILL.md").read_bytes()),
        "provider_calls": [], "supabase_writes": 0, "new_visual_generations": 0, "stages": {}, "failures": [],
        "scope": ("Conferência editorial autêntica isolada; a liberação completa exige também evidência visual anterior."
                  if args.editorial_only else "Renderização real + provedores reais. Aprovação técnica não publica artes nem ativa produção.")}

    def renderer_check():
        renderer = verify_renderer(output / "renderer")
        summary["renderer"] = {"status": "passed", "previews": list(renderer["previews"]),
                               "source_files_verified": renderer["source_files_verified"]}

    checks = [("renderer", renderer_check)]
    if args.editorial_only:
        checks = [("original_agents", lambda: private_context_check(summary))]
        for stage in ("renderer", "magnific", "designer"):
            summary[stage] = {"status": "not_run_editorial_only"}
    elif args.live:
        checks.extend([
            ("magnific", lambda: magnific_check(summary)),
            ("designer", lambda: designer_check(output, summary)),
            ("original_agents", lambda: private_context_check(summary)),
        ])
    else:
        summary["provider_status"] = "not_run_offline"
        summary["original_agents"] = {"status": "not_run_offline", "supabase_writes": 0}

    # Independent read-only checks all run. A failed fixture/provider must not hide
    # whether the original private context and agents are intact; every gate remains required.
    for stage, check in checks:
        try:
            check()
        except Exception as error:
            public_error = _public_error(error, stage)
            summary["stages"][stage] = {"status": "failed", "error": public_error}
            summary["failures"].append({"stage": stage, "error": public_error})
            summary.setdefault(stage, {})["status"] = "failed"
        else:
            state = summary.setdefault(stage, {}).get("status", "passed")
            summary["stages"][stage] = {"status": state}
        # Keep partial evidence if the runner is interrupted during a later provider call.
        _save(output / "summary.json", summary)

    summary["ok"] = not summary["failures"]
    if summary["failures"]:
        # Retain the first-error keys for existing consumers, alongside the full stage list.
        summary["failed_stage"] = summary["failures"][0]["stage"]
        summary["error"] = summary["failures"][0]["error"]
    summary["ended_at"] = datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat()
    _save(output / "summary.json", summary)
    print(json.dumps({"ok": summary["ok"], "failed_stage": summary.get("failed_stage"),
                      "failed_stages": [item["stage"] for item in summary["failures"]],
                      "error": summary.get("error"), "summary": str(output / "summary.json")}, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
