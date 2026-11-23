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
import json, os, re, subprocess, sys, time, urllib.request
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
    r = subprocess.run([sys.executable, str(ROOT / "kit" / "render.py"), str(tmp), str(out)], capture_output=True, text=True)
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


def processar(jobs):
    token = oidc()
    res = []
    for job in jobs:
        try:
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
    run("git", "add", "fotos", "arts", "jobs")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        return True
    run("git", "commit", "-q", "-m", "pedidos processados")
    for _ in range(3):
        if subprocess.run(["git", "pull", "--rebase", "-q"], cwd=ROOT).returncode == 0 and \
           subprocess.run(["git", "push", "-q"], cwd=ROOT).returncode == 0:
            return True
        time.sleep(5)
    return False


def vigiar(minutos):
    """Fica de plantão: olha a fila a cada 30 s e processa o que chegar."""
    fim = time.time() + minutos * 60
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
        time.sleep(30)


if __name__ == "__main__":
    vigiar(float(sys.argv[1]) if len(sys.argv) > 1 else 50)
