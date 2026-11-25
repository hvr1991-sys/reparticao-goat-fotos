#!/usr/bin/env python3
"""Agenda baseada nas transmissões reais, com revisão visual gratuita obrigatória.

Cada página é renderizada e revisada antes de qualquer envio. Falta de foto,
resposta de IA ou saldo gratuito mantém a agenda pendente. Magnific continua
responsável por recursos visuais criativos; agendas usam os assets da skill.

Uso: python tools/agenda_robo.py amostra|valer [AAAA-MM-DD ...]
"""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import agenda, processar
from tools.openrouter_adapter import gerar_json, ProviderUnavailable

SP = timezone(timedelta(hours=-3))
SKILL = ROOT / "kit" / "skill-original"


def api(acao, body=None, **params):
    url = f"{processar.JOBS_URL}?" + urllib.parse.urlencode({"acao": acao, **params})
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 method="POST" if body is not None else "GET",
                                 headers={"Authorization": "Bearer " + processar.oidc(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def render(spec, out):
    prepared = agenda.spec_para_kit(spec)
    with tempfile.TemporaryDirectory(prefix="goat-agenda-spec-") as directory:
        path = Path(directory) / "spec.json"
        path.write_text(json.dumps(processar.resolver(prepared), ensure_ascii=False), encoding="utf-8")
        env = {**os.environ, "RG_EXIGIR_EQUIPE": "1"}
        env.pop("RG_SEM_CONFERENCIA", None)
        result = subprocess.run([sys.executable, str(ROOT / "kit" / "render.py"), str(path), str(out)],
                                capture_output=True, text=True, env=env, timeout=120)
    return result.returncode == 0 and out.exists(), (result.stderr or result.stdout)[-600:]


def _imagem(path):
    return {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(Path(path).read_bytes()).decode()}}


def pente_fino(png, dia, titulo, transmissoes, pagina=1, total_paginas=1):
    """A revisão visual jamais é substituída por sucesso técnico do renderizador."""
    if not os.environ.get("OPENROUTER_API_KEY"):
        return False, "Pendente: revisão visual gratuita não configurada", 1
    reference = "modelo-agenda-jogo-unico.png" if len(transmissoes) == 1 and total_paginas == 1 and (transmissoes[0].get("kind") or "").lower() != "programa" else "modelo-agenda-do-dia.png"
    truth = [{key: item.get(key) for key in ("time", "competition", "title", "kind", "participantes")} for item in transmissoes]
    instructions = (SKILL / "SKILL.md").read_text(encoding="utf-8") + "\n" + (SKILL / "OVERRIDES.md").read_text(encoding="utf-8")
    try:
        def valid(response):
            return (type(response.get("ok")) is bool and type(response.get("nota")) is int
                    and 1 <= response["nota"] <= 5 and isinstance(response.get("review"), str)
                    and isinstance(response.get("corrigir", ""), str))
        response = gerar_json([
            {"text": "Referência original de composição (seus fatos/datas são históricos e não entram na peça nova):"},
            _imagem(SKILL / "arquivos" / reference),
            {"text": "Peça produzida para revisão:"}, _imagem(png),
            {"text": f"""Você faz o pente fino do Canal GOAT. Revise {titulo}, data {dia}, página {pagina}/{total_paginas}.
A verdade para ESTA página é o cadastro abaixo. Outras páginas não estão nesta imagem:
{json.dumps(truth, ensure_ascii=False)}
Reprove horário/confronto/campeonato ou data diferentes, falta de transmissão desta página,
texto cortado/ilegível, rosto coberto, atleta/escudo incorreto, imagem com placar/texto de outra arte,
marca d'água, programa sem a foto real da pessoa escalada ou erro de português.
É permitido omitir países entre parênteses no título e usar 21H em vez de 21:00.
Confira fidelidade de geometria, fontes, hierarquia, estádio escuro, degradês e logo GOAT único.
A imagem de referência guia o formato, não autoriza reutilizar seus fatos nem suas fotos.
Regras integrais e decisões atuais:\n{instructions}
Responda JSON {{"ok": true/false, "nota": 1-5, "review": "uma linha", "corrigir": "vazio se aprovada"}}.
Incerteza significa reprovação. Não declare que avaliou uma foto que não conseguiu enxergar."""},
        ], validator=valid, temp=0.1)
        approved = response["ok"] is True and response["nota"] >= 4 and not response.get("corrigir", "").strip()
        review = response["review"] + (f" · Corrigir: {response['corrigir']}" if response.get("corrigir") else "")
        return approved, review, response["nota"]
    except (ProviderUnavailable, ValueError, TypeError, KeyError, OSError):
        return False, "Pendente: revisão visual indisponível; arte não liberada", 1


def legenda(titulo, spec):
    lines = [f"{item['horario']} · {item['confronto'].title()} ({item['rotulo'].title()})" for item in spec["jogos"]]
    return f"{spec['data_dia_semana'].title()} no GOAT! ⚽️\n\n" + "\n".join(lines) + "\n\nConfira a programação do Canal GOAT."


def _pages(spec):
    total = (len(spec["jogos"]) + 5) // 6
    return [{**spec, "jogos": spec["jogos"][index:index+6], "pagina": index // 6 + 1, "total_paginas": total}
            for index in range(0, len(spec["jogos"]), 6)]


def um_dia(dia, modo):
    datetime.fromisoformat(dia)
    dados = api("agenda-dados", dia=dia)
    trans = sorted([item for item in dados.get("transmissoes") or [] if (item.get("kind") or "").lower() != "outro"],
                   key=lambda item: item.get("time") or "")
    if not trans:
        print(dia, "sem transmissões cadastradas", flush=True)
        return
    existing = dados.get("existentes") or []
    retry = next((card for card in existing if card.get("stage") == "producao" and card.get("created_by") == "robô da agenda"), None)
    if modo == "valer" and existing and not retry:
        print(dia, "agenda já existe; preservar etapa e decisões do Gestor", flush=True)
        return
    if len(trans) > 36:
        raise ValueError("Mais de 36 transmissões: dividir em mais de uma pauta antes de produzir")
    spec, titulo, pending = agenda.montar(dia, trans, dados.get("rodizio") or [],
        used_photo_hashes=dados.get("used_photo_hashes"), used_photo_files=dados.get("used_photo_files"),
        used_photo_urls=dados.get("used_photo_urls"))
    pages = _pages(spec)
    report_dir = Path(os.environ.get("GOAT_AGENDA_REVIEW_DIR", "/tmp/goat-agenda-review"))
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {"titulo": titulo, "ok": False, "review": "", "sem_foto": pending, "spec": spec, "paginas": [], "enviadas": 0}
    report_path = report_dir / f"agenda-{dia}.json"
    with tempfile.TemporaryDirectory(prefix="goat-agenda-") as directory:
        candidates, reviews = [], []
        if not pending:
            for number, page in enumerate(pages, 1):
                png = Path(directory) / f"pagina-{number}.png"
                ok_kit, error = render(page, png)
                if not ok_kit:
                    reviews.append((False, f"Página {number}: conferência do kit reprovou: {error}", 1))
                    break
                before_review = hashlib.sha256(png.read_bytes()).hexdigest()
                result = pente_fino(png, dia, titulo, trans[(number-1)*6:number*6], number, len(pages))
                if hashlib.sha256(png.read_bytes()).hexdigest() != before_review:
                    result = (False, "Arquivo mudou durante a revisão", 1)
                reviews.append(result)
                candidates.append((png, before_review))
                preview = report_dir / f"agenda-{dia}-{number}.png"
                shutil.copyfile(png, preview)
                report["paginas"].append({"arquivo": preview.name, "ok": result[0], "sha256": before_review, "review": result[1]})
                if result[0] is not True:
                    break
        approved = not pending and len(reviews) == len(pages) and all(item[0] is True for item in reviews)
        review = " | ".join(item[1] for item in reviews) if reviews else "Pendente: " + "; ".join(pending)
        score = min((item[2] for item in reviews), default=1)
        report.update(ok=approved, review=review)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(dia, titulo, "|", "APROVADA NA REVISÃO" if approved else "PENDENTE", "|", review[:500], flush=True)
        if modo != "valer":
            return report
        created = {"ok": True, "id": retry["id"]} if retry else api("agenda-criar", {
            "dia": dia, "titulo": titulo, "legenda": legenda(titulo, spec),
            "brief": f"Entrega: véspera · Post: {titulo.split('· ')[-1]}\nAgenda a partir das transmissões cadastradas; skill original; revisão visual obrigatória."})
        if created.get("ok") is not True:
            report.update(ok=False, review="Não foi possível criar a pauta; nenhum envio realizado")
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            return report
        cid = created["id"]
        # Todas as páginas já foram aprovadas. Enviar os mesmos bytes, sem re-renderizar.
        if approved:
            for number, (png, digest) in enumerate(candidates, 1):
                if hashlib.sha256(png.read_bytes()).hexdigest() != digest:
                    approved, review = False, "Arquivo aprovado mudou antes do envio"
                    break
                status, result = processar.publicar_arte(png, cid, n=number)
                if status != "feito":
                    approved, review = False, f"Envio da página {number} não foi concluído; manter em produção"
                    break
                report["enviadas"] += 1
        sources = []
        library = {item["arquivo"]: item for item in agenda.biblioteca()}
        for item in spec["jogos"]:
            photo = library.get(item.get("foto"))
            if photo:
                sources.append({"label": f"{item['confronto'].title()} · {photo['credito']}", "url": photo["pagina"],
                                "url_imagem": photo["url_imagem"], "arquivo": photo["arquivo"], "sha256": photo["sha256"]})
            elif str(item.get("foto", "")).startswith("equipe:"):
                reference = str(item["foto"])
                filename = reference[len("equipe:"):]
                private_root = (ROOT / "equipe" / "private").resolve()
                private_photo = (private_root / filename).resolve()
                if re.fullmatch(r"[0-9a-f]{16}-\d+\.jpg", filename) and private_photo.parent == private_root and private_photo.is_file():
                    sources.append({"label": "Foto da equipe fornecida pelo Gestor", "url": "", "tipo": "equipe",
                                    "arquivo": reference, "sha256": agenda.photo_digest(private_photo)})
                else:
                    approved, review = False, "Identificação da foto da equipe indisponível; manter em produção"
        team = [{"nome": item["equipe_nome"], "broadcast_id": item.get("broadcast_id"), "dia": dia}
                for item in spec["jogos"] if item.get("equipe_nome")]
        note = "Agenda feita pelo robô" + (f" · pendências: {'; '.join(pending)}" if pending else "")
        api("agenda-pronta", {"id": cid, "ok": approved, "score": score,
            "review": f"Post: {titulo.split('· ')[-1]} · {review}", "note": note if approved else f"{note} · Ajuste: {review}",
            "photo_sources": sources, "equipe": team if approved else [],
            "log": f"{titulo}: {'na Mesa do Gestor' if approved else 'ficou em produção para ajuste'}"})
        report.update(ok=approved, review=review)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return report


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "amostra"
    if modo not in ("amostra", "valer"):
        raise ValueError("Modo deve ser amostra ou valer")
    dias = " ".join(sys.argv[2:]).split() or [(datetime.now(SP).date() + timedelta(days=day)).isoformat() for day in (1, 2)]
    for dia in dias:
        datetime.fromisoformat(dia)
    processar.equipe_privada(upload_thumbs=modo == "valer")
    for dia in dias:
        try:
            um_dia(dia, modo)
        except Exception as error:
            print(dia, "pendente:", str(error)[:350], flush=True)
    if modo != "valer":
        return
    run = lambda *args: subprocess.run(list(args), cwd=ROOT, check=False)
    run("git", "add", "arts", "fotos")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode != 0:
        run("git", "commit", "-q", "-m", "agenda com fontes verificadas e revisão visual")
        for _ in range(3):
            if run("git", "pull", "--rebase", "-q").returncode == 0 and run("git", "push", "-q").returncode == 0:
                break


if __name__ == "__main__":
    main()
