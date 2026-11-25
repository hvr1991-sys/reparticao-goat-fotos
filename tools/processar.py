#!/usr/bin/env python3
"""Processa a fila de pedidos da Repartição GOAT (roda no GitHub Actions).

A rodada agendada grava pedidos na tabela rg_jobs do Supabase; este script busca a fila
(função rg-jobs, com token OIDC do GitHub) e faz:

- kind "fotos": payload {"fotos": [{url, credito, rotulo}, ...]}
  Baixa com tools/baixar.py para fotos/<card>-j<id>/ (meta.json com origem e tamanho).
- kind "arte":  payload {"n": 1, "spec": {...spec do kit/render.py...}}
  Caminhos de foto no spec são relativos ao repositório (ex.: "fotos/<pasta>/1.png").
  Monta a arte em arts/<card>-<n>.png e envia ao painel (rg-arte-upload).

Fica de plantão por ~50 minutos olhando a fila a cada 30 s. Os resultados só são
informados ao Supabase depois do git push, para a rodada já achar os arquivos aqui.
"""
import copy, hashlib, io, json, os, re, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
UPLOAD = "https://llmigqclpddpzcvpeufi.supabase.co/functions/v1/rg-arte-upload"


def oidc():
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"] + "&audience=reparticao-goat"
    req = urllib.request.Request(url, headers={"Authorization": "bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["value"]


def fotos(job):
    card, jid = job["card_id"], job["id"]
    pasta = f"{card}-j{jid}"
    itens = (job.get("payload") or {}).get("fotos") or []
    (ROOT / "jobs").mkdir(exist_ok=True)
    (ROOT / "jobs" / f"{pasta}.json").write_text(json.dumps({"id": pasta, "fotos": itens[:6]}, ensure_ascii=False), encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "tools" / "baixar.py")], check=False)
    meta = ROOT / "fotos" / pasta / "meta.json"
    if not meta.exists():
        return "erro", {"erro": "o robô não gerou meta.json", "pasta": f"fotos/{pasta}"}
    m = json.loads(meta.read_text(encoding="utf-8"))
    return "feito", {"pasta": f"fotos/{pasta}", "fotos": m.get("fotos", [])}


def resolver(spec):
    """Resolve only local authorized photos; never accept model-invented file/URL paths."""
    spec = copy.deepcopy(spec)
    base = (ROOT / "fotos").resolve()

    def fix(value):
        if isinstance(value, str) and value.startswith("equipe:"):
            return value
        if not isinstance(value, str):
            raise ValueError("caminho de imagem inválido")
        path = (ROOT / value).resolve()
        if base not in path.parents or not path.is_file():
            raise ValueError("foto fora da biblioteca autorizada ou inexistente")
        return str(path)

    for key in ("foto", "fundo", "foto2", "foto_superior", "foto_inferior"):
        if spec.get(key):
            spec[key] = fix(spec[key])
    if isinstance(spec.get("fotos"), list):
        spec["fotos"] = [fix(x) for x in spec["fotos"]]
    for item in spec.get("jogos") or []:
        if item.get("foto"):
            item["foto"] = fix(item["foto"])
    return spec


def renderizar_arte(card_id, spec, n=1, edicao_gestor=False):
    """Render locally. This function has no network/upload/database side effects."""
    if not UUID.fullmatch(str(card_id)) or not 1 <= n <= 6:
        return "erro", {"erro": "card ou página inválido"}, None
    folder = ROOT / ".goat-state" / "previews"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{card_id}-{n}.png"
    tmp = folder / f"{card_id}-{n}.json"
    try:
        resolved = resolver(spec)
        tmp.write_text(json.dumps(resolved, ensure_ascii=False), encoding="utf-8")
        env = {**os.environ, "RG_EXIGIR_EQUIPE": "1"}
        if edicao_gestor:
            env["RG_SEM_CONFERENCIA"] = "1"
        result = subprocess.run([sys.executable, str(ROOT / "kit" / "render.py"), str(tmp), str(out)],
                                capture_output=True, text=True, env=env, timeout=90)
        if result.returncode != 0 or not out.exists():
            return "erro", {"erro": (result.stderr or result.stdout)[-700:]}, None
        return "feito", {"arquivo": str(out.relative_to(ROOT)), "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}, out
    except Exception as e:
        return "erro", {"erro": str(e)[:400]}, None


def publicar_arte(png, card_id, n=1, token=None):
    """Upload exactly the bytes that were reviewed; never re-render here."""
    if not UUID.fullmatch(str(card_id)) or not 1 <= n <= 6:
        return "erro", {"erro": "card ou página inválido"}
    data = Path(png).read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 8 * 1024 * 1024:
        return "erro", {"erro": "PNG inválido ou maior que8MB"}
    request = urllib.request.Request(f"{UPLOAD}?card={card_id}&n={n}", data=data, method="POST",
        headers={"Authorization": "Bearer " + (token or oidc()), "Content-Type": "image/png"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            uploaded = json.load(response)
        if uploaded.get("ok") is not True or not uploaded.get("path"):
            raise ValueError("o painel não confirmou o arquivo")
    except Exception as e:
        return "erro", {"erro": f"envio da arte revisada falhou ({type(e).__name__})"}
    (ROOT / "arts").mkdir(exist_ok=True)
    target = ROOT / "arts" / (f"{card_id}.png" if n == 1 else f"{card_id}-{n}.png")
    target.write_bytes(data)
    return "feito", {"arquivo": str(target.relative_to(ROOT)), "art_path": uploaded["path"],
                     "sha256": hashlib.sha256(data).hexdigest()}


def arte(job, token):
    payload = job.get("payload") or {}
    n = int(payload.get("n") or 1)
    status, result, png = renderizar_arte(job["card_id"], payload.get("spec") or {}, n,
                                       edicao_gestor=payload.get("edicao_gestor") is True)
    if status != "feito":
        return status, result
    if payload.get("edicao_gestor") is not True:
        # Queued automated artwork must pass the same visual gate as the designer.
        try:
            import designer_openrouter
            snapshot = api("contexto")
            card = next(c for c in snapshot["cards"] if c["id"] == job["card_id"])
            card["_lessons"] = snapshot.get("lessons") or []
            ok, reason = designer_openrouter.revisar_arte(png, card, payload.get("spec"), snapshot.get("docs"))
            if not ok:
                return "erro", {"erro": "revisão visual: " + reason[:500]}
        except Exception as e:
            return "erro", {"erro": "revisão obrigatória indisponível: " + str(e)[:300]}
    return publicar_arte(png, job["card_id"], n, token)


JOBS_URL = "https://llmigqclpddpzcvpeufi.supabase.co/functions/v1/rg-jobs"


def chamar(method, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(JOBS_URL, data=data, method=method,
                                 headers={"Authorization": "Bearer " + oidc(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


MODELOS_BASE = "https://llmigqclpddpzcvpeufi.supabase.co/storage/v1/object/public/rg-modelos/"
TIPOS = {"agenda-do-dia", "jogo-unico", "manchete", "chamada", "estatisticas", "carrossel", "story", "tarja-video", "outros"}


def modelo(job):
    """Copia um modelo enviado pelo CEO (Supabase) para modelos/<tipo>/ no repositório."""
    p = job.get("payload") or {}
    tipo, path, nota = p.get("tipo"), str(p.get("path") or ""), p.get("nota")
    if tipo not in TIPOS or not re.match(r"^modelos/[A-Za-z0-9._-]+$", path):
        return "erro", {"erro": "tipo ou arquivo inválido"}
    with urllib.request.urlopen(MODELOS_BASE + path, timeout=60) as r:
        data = r.read()
    nome = path.split("/", 1)[1]
    dest = ROOT / "modelos" / tipo
    dest.mkdir(parents=True, exist_ok=True)
    (dest / nome).write_bytes(data)
    if nota:
        (dest / (nome.rsplit(".", 1)[0] + ".txt")).write_text(str(nota) + "\n", encoding="utf-8")
    return "feito", {"arquivo": f"modelos/{tipo}/{nome}"}


PASTA_TIPO = {"agenda": "agenda-do-dia", "jogo_unico": "jogo-unico", "manchete": "manchete", "chamada": "chamada", "estatisticas": "estatisticas"}


def referencia(job):
    """Arte marcada com ⭐ pelo Gestor vira modelo oficial: imagem + spec + nota em modelos/<tipo>/."""
    p = job.get("payload") or {}
    card = str(job.get("card_id") or "")
    if not UUID.match(card):
        return "erro", {"erro": "card inválido"}
    spec = p.get("spec") or {}
    pasta = ROOT / "modelos" / PASTA_TIPO.get(spec.get("tipo"), "outros")
    pasta.mkdir(parents=True, exist_ok=True)
    src = ROOT / "arts" / f"{card}.png"
    url = p.get("url")
    dest = pasta / f"REFERENCIA-{card[:8]}.png"
    if src.exists():
        dest.write_bytes(src.read_bytes())
    elif url and str(url).startswith("https://llmigqclpddpzcvpeufi.supabase.co/"):
        with urllib.request.urlopen(url, timeout=60) as r:
            dest.write_bytes(r.read())
    else:
        return "erro", {"erro": "arte não encontrada"}
    (pasta / f"REFERENCIA-{card[:8]}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    (pasta / f"REFERENCIA-{card[:8]}.txt").write_text(
        f"⭐ REFERÊNCIA DO GESTOR — {p.get('titulo','')}. Copie este padrão (texto curto, posição, foto, linha do jogo). O spec exato está no .json ao lado.",
        encoding="utf-8")
    return "feito", {"modelo": str(dest.relative_to(ROOT))}


# ---- fotos da equipe: criptografadas em equipe/enc/ (repositório público), abertas em equipe/private/ ----
EQUIPE_ENC = ROOT / "equipe" / "enc"
EQUIPE_PRIV = ROOT / "equipe" / "private"
_EQUIPE_KEY = {"v": None}


def _chave_equipe():
    if not _EQUIPE_KEY["v"]:
        req = urllib.request.Request(JOBS_URL + "?acao=chave-equipe", headers={"Authorization": "Bearer " + oidc()})
        with urllib.request.urlopen(req, timeout=60) as r:
            _EQUIPE_KEY["v"] = json.load(r).get("chave")
    return _EQUIPE_KEY["v"]


def _miniatura(arquivo):
    from PIL import Image
    im = Image.open(EQUIPE_PRIV / arquivo).convert("RGB")
    im.thumbnail((360, 360))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    req = urllib.request.Request(f"{JOBS_URL}?acao=equipe-thumb&arquivo={arquivo}", data=buf.getvalue(), method="POST",
                                 headers={"Authorization": "Bearer " + oidc(), "Content-Type": "image/jpeg"})
    with urllib.request.urlopen(req, timeout=60) as r:
        json.load(r)


def equipe_privada(upload_thumbs=True):
    """Abre as fotos da equipe e manda ao painel as miniaturas que faltam."""
    try:
        chave = _chave_equipe()
        if not chave:
            print("sem chave das fotos da equipe", flush=True)
            return
        EQUIPE_PRIV.mkdir(parents=True, exist_ok=True)
        for enc in sorted(EQUIPE_ENC.glob("*.enc")):
            out = EQUIPE_PRIV / enc.name[:-4]
            if not out.exists():
                subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-in", str(enc), "-out", str(out), "-pass", "env:EQ_KEY"],
                               check=True, env={**os.environ, "EQ_KEY": chave})
        print("fotos da equipe prontas:", len(list(EQUIPE_PRIV.glob("*.jpg"))), flush=True)
        if not upload_thumbs:
            return
        req = urllib.request.Request(JOBS_URL + "?acao=equipe-pendentes", headers={"Authorization": "Bearer " + oidc()})
        with urllib.request.urlopen(req, timeout=60) as r:
            pend = json.load(r)
        for arq in pend:
            if (EQUIPE_PRIV / arq).exists():
                _miniatura(arq)
    except Exception as e:
        print("sem fotos da equipe:", e, flush=True)


def equipe_nova(job):
    """Foto enviada pelo painel: baixa do espaço privado, criptografa no repositório e gera a miniatura."""
    from PIL import Image, ImageOps
    p = job.get("payload") or {}
    arquivo, path = str(p.get("arquivo", "")), str(p.get("path", ""))
    if not re.fullmatch(r"[0-9a-f]{16}-\d+\.jpg", arquivo):
        return "erro", {"erro": "arquivo inválido"}
    req = urllib.request.Request(f"{JOBS_URL}?acao=equipe-url&path={urllib.parse.quote(path)}", headers={"Authorization": "Bearer " + oidc()})
    with urllib.request.urlopen(req, timeout=60) as r:
        url = json.load(r).get("url")
    if not url:
        return "erro", {"erro": "foto não encontrada no espaço privado"}
    with urllib.request.urlopen(url, timeout=120) as r:
        raw = r.read()
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    im.thumbnail((1800, 1800))
    EQUIPE_PRIV.mkdir(parents=True, exist_ok=True)
    EQUIPE_ENC.mkdir(parents=True, exist_ok=True)
    im.save(EQUIPE_PRIV / arquivo, "JPEG", quality=90)
    subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt", "-in", str(EQUIPE_PRIV / arquivo),
                    "-out", str(EQUIPE_ENC / (arquivo + ".enc")), "-pass", "env:EQ_KEY"],
                   check=True, env={**os.environ, "EQ_KEY": _chave_equipe()})
    _miniatura(arquivo)
    return "feito", {"arquivo": arquivo}


def processar(jobs):
    token = oidc()
    res = []
    for job in jobs:
        try:
            if job["kind"] == "modelo":
                status, result = modelo(job)
            elif job["kind"] == "equipe":
                status, result = equipe_nova(job)
            elif job["kind"] == "referencia":
                status, result = referencia(job)
            else:
                if not UUID.match(str(job.get("card_id", ""))):
                    raise ValueError("card_id inválido")
                status, result = fotos(job) if job["kind"] == "fotos" else arte(job, token)
        except Exception as e:
            status, result = "erro", {"erro": str(e)[:500]}
        print(job["id"], job["kind"], status, flush=True)
        res.append({"id": job["id"], "status": status, "result": result})
    return res


def salvar_no_repo():
    run = lambda *a: subprocess.run(list(a), cwd=ROOT, check=False)
    run("git", "add", "fotos", "arts", "jobs", "modelos", "equipe/enc")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        return True
    run("git", "commit", "-q", "-m", "pedidos processados")
    for _ in range(3):
        if subprocess.run(["git", "pull", "--rebase", "-q"], cwd=ROOT).returncode == 0 and \
           subprocess.run(["git", "push", "-q"], cwd=ROOT).returncode == 0:
            return True
        time.sleep(5)
    return False


def fontes_privadas():
    """Fontes licenciadas (Helvetica Neue): ficam criptografadas em kit/fonts/enc/ no repositório público.
    O robô pega a chave no Supabase (token OIDC) e descriptografa para kit/fonts/private/ (fora do git)."""
    try:
        req = urllib.request.Request(JOBS_URL + "?acao=chave-fontes", headers={"Authorization": "Bearer " + oidc()})
        with urllib.request.urlopen(req, timeout=60) as r:
            chave = json.load(r).get("chave")
        if not chave:
            print("sem chave das fontes", flush=True)
            return
        dest = ROOT / "kit" / "fonts" / "private"
        dest.mkdir(parents=True, exist_ok=True)
        for enc in sorted((ROOT / "kit" / "fonts" / "enc").glob("*.enc")):
            out = dest / enc.name[:-4]
            subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-in", str(enc), "-out", str(out), "-pass", "env:FONT_KEY"],
                           check=True, env={**os.environ, "FONT_KEY": chave})
        print("fontes privadas prontas:", [f.name for f in dest.iterdir()], flush=True)
    except Exception as e:
        print("sem fontes privadas:", e, flush=True)


def api(acao, body=None, **params):
    query = urllib.parse.urlencode({"acao": acao, **params})
    request = urllib.request.Request(JOBS_URL + "?" + query,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
        method="POST" if body is not None else "GET",
        headers={"Authorization": "Bearer " + oidc(), "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def runtime_config():
    path = ROOT / "config" / "runtime.json"
    return json.loads(path.read_text()) if path.exists() else {"enabled": False}


def designers_goat(max_cards=3):
    """Three original designers, real skill, reviewed photos, Magnific visual resources."""
    if not os.environ.get("OPENROUTER_API_KEY"):
        return {"results": [], "error": "OpenRouter não configurado"}
    sys.path.insert(0, str(ROOT / "tools"))
    import designer_openrouter
    lote = api("producao", n=max_cards)
    cards = lote.get("cards") or []
    results = []

    def baixar_fotos(card_id, items, tag):
        import baixar
        suffix = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()[:12]
        folder = ROOT / "fotos" / f"{card_id}-{tag}-{suffix}"
        folder.mkdir(parents=True, exist_ok=True)
        meta = folder / "meta.json"
        if not meta.exists():
            photos = []
            for n, item in enumerate(items[:4], 1):
                try:
                    photos.append({"ok": True, **baixar.baixar(item, folder, n)})
                except Exception:
                    photos.append({"ok": False, "pagina": item.get("url"), "erro": "foto oficial indisponível"})
            meta.write_text(json.dumps({"id": folder.name, "fotos": photos}, ensure_ascii=False, indent=2))
        data = json.loads(meta.read_text())
        return str(folder.relative_to(ROOT)), [(str((folder / f["arquivo"]).relative_to(ROOT)), f)
            for f in data["fotos"] if f.get("ok") is True]

    def informar(body):
        # Includes the Magnific task ledger, even when a task is pending/uncertain.
        if not salvar_no_repo():
            raise RuntimeError("Falha ao preservar arquivos e tarefas no repositório")
        result = api("card", body)
        if result.get("ok") is not True:
            raise RuntimeError("O painel não confirmou a atualização do card")

    def publicar(card_id, png, n):
        return publicar_arte(png, card_id, n)

    used_by_day = {}
    for card in cards:
        card["_lessons"] = lote.get("lessons") or []
        card["_equipe"] = card.get("equipe") or lote.get("equipe") or []
        recent = used_by_day.setdefault(card.get("pub_date"), {"hashes": [], "files": [], "urls": []})
        for kind in recent:
            key = "used_photo_" + kind
            card[key] = list(set(card.get(key) or []) | set(recent[kind]))
        result = designer_openrouter.produzir(card, lote.get("docs") or [], baixar_fotos,
                                             renderizar_arte, informar, publicar=publicar)
        results.append({"id": card["id"], "designer": card["designer"], **result})
        if result.get("status") == "delivered":
            for sidecar in (ROOT / "arts").glob(card["id"] + "*.json"):
                for photo in json.loads(sidecar.read_text()).get("photo_sources") or []:
                    for kind, field in (("hashes", "sha256"), ("files", "arquivo"), ("urls", "url")):
                        if photo.get(field):
                            recent[kind].append(photo[field])
        if result.get("status") == "waiting_provider":
            # Release visible statuses for the rest; their lease expires normally.
            for remaining in cards[len(results):]:
                informar({"id": remaining["id"], "designer": remaining["designer"], "awaiting": True,
                          "task": "Aguardando provedor", "log": "Rodada suspensa: provedor indisponível."})
            break
    return {"results": results, "claimed": len(cards)}


def rodada_goat():
    """One coherent round. Human approval stages remain human."""
    if not runtime_config().get("enabled"):
        return {"enabled": False}
    sys.path.insert(0, str(ROOT / "tools"))
    import editorial_round
    report = editorial_round.executar(transport=api, phases=("research", "coordinate", "develop", "reels"))
    produced = designers_goat(int(runtime_config().get("max_designers_per_round", 3)))
    quality = editorial_round.executar(transport=api, phases=("quality",))
    successful = sum(x.get("status") == "delivered" for x in produced.get("results", []))
    blocked = max(0, produced.get("claimed", len(produced.get("results", []))) - successful)
    summary = f"Rodada concluída: {successful} artes entregues, {blocked} pendências de produção. Aprovação final permanece com o Gestor."
    if report.get("errors") or quality.get("errors") or produced.get("error"):
        summary += " Há tarefas aguardando dados, revisão ou provedor; consulte os registros."
    # Completing an operational request does not mean its artwork was approved.
    receipt = editorial_round.concluir_pedidos(report.get("requests") or [], summary, api)
    if receipt.get("ok") is not True or any(r.get("status") not in ("applied", "already_applied") for r in receipt.get("results", [])):
        raise RuntimeError("O painel não confirmou o encerramento da rodada; pedido será retomado")
    print(summary, flush=True)
    return {"editorial": report, "production": produced, "quality": quality}


def vigiar(minutos):
    """Maintain existing job queue; run the nine-role round at a bounded interval."""
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise RuntimeError("Produção só pode executar na branch main")
    fim = time.time() + minutos * 60
    equipe_privada()
    next_round = 0
    while time.time() < fim:
        try:
            jobs = chamar("GET")
            if jobs:
                results = processar(jobs)
                if not salvar_no_repo():
                    for result in results:
                        if result["status"] == "feito":
                            result["status"] = "erro"
                            result["result"] = {"erro": "falha ao preservar resultado no repositório"}
                chamar("POST", results)
            if time.time() >= next_round:
                next_round = time.time() + 1800
                rodada_goat()
        except Exception as e:
            print("Rodada com pendência:", str(e)[:300], flush=True)
        time.sleep(20)


if __name__ == "__main__":
    vigiar(float(sys.argv[1]) if len(sys.argv) > 1 else 50)
