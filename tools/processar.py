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
import io, json, os, re, subprocess, sys, time, urllib.parse, urllib.request
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
    """Troca caminhos relativos de foto por absolutos, só dentro de fotos/."""
    base = (ROOT / "fotos").resolve()

    def fix(v):
        if isinstance(v, str) and v.startswith("equipe:"):
            return v  # foto da equipe: o kit/render.py resolve a partir de equipe/private/
        p = (ROOT / v).resolve()
        if base not in p.parents or not p.exists():
            raise ValueError(f"foto fora de fotos/ ou inexistente: {v}")
        return str(p)

    for k in ("foto", "fundo"):
        if spec.get(k):
            spec[k] = fix(spec[k])
    for j in spec.get("jogos", []) or []:
        if j.get("foto"):
            j["foto"] = fix(j["foto"])
    return spec


def arte(job, token):
    card = job["card_id"]
    p = job.get("payload") or {}
    n = int(p.get("n") or 1)
    if not UUID.match(card) or not 1 <= n <= 6:
        return "erro", {"erro": "card ou n inválido"}
    spec = resolver(dict(p.get("spec") or {}))
    (ROOT / "arts").mkdir(exist_ok=True)
    out = ROOT / "arts" / (f"{card}.png" if n == 1 else f"{card}-{n}.png")
    tmp = Path("/tmp") / f"spec-{job['id']}.json"
    tmp.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    env = {**os.environ, "RG_EXIGIR_EQUIPE": "1"}
    if p.get("edicao_gestor"):
        env["RG_SEM_CONFERENCIA"] = "1"  # edição direta do Gestor no painel: a decisão é dele
    r = subprocess.run([sys.executable, str(ROOT / "kit" / "render.py"), str(tmp), str(out)], capture_output=True, text=True, env=env)
    if r.returncode != 0 or not out.exists():
        return "erro", {"erro": (r.stderr or r.stdout)[-800:]}
    req = urllib.request.Request(f"{UPLOAD}?card={card}&n={n}", data=out.read_bytes(), method="POST",
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "image/png"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            up = json.load(resp)
    except Exception as e:
        return "erro", {"erro": f"arte montada, mas o envio ao painel falhou: {e}", "arquivo": str(out.relative_to(ROOT))}
    return "feito", {"arquivo": str(out.relative_to(ROOT)), "art_path": up.get("path")}


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


def equipe_privada():
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


def designers_gemini():
    """Designers no Gemini: produz as artes dos cards em produção (se houver GEMINI_API_KEY)."""
    # Gemini pausado pelo Gestor: para religar, devolva GEMINI_API_KEY ao passo "Plantão" do workflow.
    if not os.environ.get("GEMINI_API_KEY"):
        return False
    sys.path.insert(0, str(ROOT / "tools"))
    import gemini
    req = urllib.request.Request(JOBS_URL + "?acao=producao&n=3", headers={"Authorization": "Bearer " + oidc()})
    with urllib.request.urlopen(req, timeout=60) as r:
        lote = json.load(r)
    cards = lote.get("cards") or []
    if not cards:
        return False
    token = oidc()

    def baixar_fotos(card_id, itens, tag):
        pasta = f"{card_id}-{tag}"
        (ROOT / "jobs").mkdir(exist_ok=True)
        (ROOT / "jobs" / f"{pasta}.json").write_text(json.dumps({"id": pasta, "fotos": itens}, ensure_ascii=False), encoding="utf-8")
        meta = ROOT / "fotos" / pasta / "meta.json"
        if meta.exists():
            meta.unlink()
        subprocess.run([sys.executable, str(ROOT / "tools" / "baixar.py")], check=False)
        if not meta.exists():
            return f"fotos/{pasta}", []
        m = json.loads(meta.read_text(encoding="utf-8"))
        return f"fotos/{pasta}", [(f"fotos/{pasta}/{f['arquivo']}", f) for f in m.get("fotos", []) if f.get("ok")]

    def montar(card_id, spec):
        status, result = arte({"id": f"g-{card_id[:8]}", "card_id": card_id, "payload": {"n": 1, "spec": spec}}, oidc())
        png = ROOT / result["arquivo"] if result.get("arquivo") else None
        return status, result, png

    def informar(body):
        salvar_no_repo()
        req = urllib.request.Request(JOBS_URL + "?acao=card", data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": "Bearer " + oidc(), "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()

    for c in cards:
        print("Gemini produzindo:", c["title"], flush=True)
        gemini.produzir(c, lote.get("docs") or [], baixar_fotos, montar, informar)
    return True


def vigiar(minutos):
    """Fica de plantão: olha a fila a cada 30 s e processa o que chegar."""
    fim = time.time() + minutos * 60
    fontes_privadas()
    equipe_privada()
    proxima_producao = 0
    while time.time() < fim:
        try:
            jobs = chamar("GET")
        except Exception as e:
            print("fila indisponível:", e, flush=True)
            jobs = []
        if jobs:
            res = processar(jobs)
            ok = salvar_no_repo()
            if not ok:
                for r in res:
                    if r["status"] == "feito":
                        r["status"], r["result"] = "erro", {"erro": "falha ao salvar no repositório", **(r["result"] or {})}
            try:
                chamar("POST", res)
            except Exception as e:
                print("falha ao informar resultados:", e, flush=True)
            continue
        if time.time() >= proxima_producao:
            try:
                if designers_gemini():
                    continue
            except Exception as e:
                print("designers Gemini indisponíveis:", e, flush=True)
            proxima_producao = time.time() + 120
        time.sleep(30)


if __name__ == "__main__":
    vigiar(float(sys.argv[1]) if len(sys.argv) > 1 else 50)
