#!/usr/bin/env python3
"""Robô da agenda do dia (GitHub Actions). Sem Claude.

Para cada dia pedido (padrão: amanhã e depois de amanhã, no fuso de São Paulo):
 1. busca transmissões, rodízio da equipe e se a agenda já existe (rg-jobs ?acao=agenda-dados);
 2. monta o spec com tools/agenda.py (fotos da biblioteca escolhidas pelo Gemini, equipe pelo rodízio);
 3. o kit monta a arte e faz a conferência automática;
 4. o Gemini faz o pente fino olhando o PNG;
 5. modo "amostra": só salva a prévia em previas/ (nada vai ao painel);
    modo "valer": cria o card, envia a arte e manda para a Mesa do Gestor (ou deixa em produção com a nota).

Uso: python tools/agenda_robo.py amostra|valer [AAAA-MM-DD ...]
"""
import json, os, subprocess, sys, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "kit"))
import agenda  # noqa: E402
import processar  # noqa: E402

SP = timezone(timedelta(hours=-3))


def api(acao, body=None, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{processar.JOBS_URL}?acao={acao}" + (f"&{q}" if q else "")
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 method="POST" if body is not None else "GET",
                                 headers={"Authorization": "Bearer " + processar.oidc(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def render(spec, out, sem_conferencia=False):
    s = agenda.spec_para_kit(spec)
    tmp = Path("/tmp") / f"agenda-{out.stem}.json"
    tmp.write_text(json.dumps(processar.resolver(s), ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "kit" / "render.py"), str(tmp), str(out)], capture_output=True, text=True,
                       env={**os.environ, "RG_EXIGIR_EQUIPE": "1", **({"RG_SEM_CONFERENCIA": "1"} if sem_conferencia else {})})
    return r.returncode == 0 and out.exists(), (r.stderr or r.stdout)[-600:]


def pente_fino(png, dia, titulo, transmissoes):
    """Gemini confere a arte inteira contra a agenda cadastrada."""
    if not os.environ.get("GEMINI_API_KEY"):
        return True, "sem Gemini: só a conferência automática do kit", 4
    import gemini
    lista = "\n".join(f"- {t.get('time')} · {t.get('competition')} · {t.get('title')} ({t.get('kind')})" for t in transmissoes)
    try:
        r = gemini.json_de(gemini.gerar([gemini.imagem(png), {"text": f"""Você é o braço direito (pente fino) do Canal GOAT. Revise esta arte "{titulo}", post do dia {dia}.
Transmissões cadastradas (a verdade; itens "outro" não entram na arte):
{lista}
Reprove se: algum horário, confronto ou campeonato diferente do cadastrado; dia da semana/data errados; texto cortado ou saindo da arte;
foto com placar, texto, marca d'água ou de time que não é do jogo; erro de português.
Responda só ```json {{"ok": true/false, "nota": 1-5, "review": "uma linha", "corrigir": "o que está errado, se houver"}}```"""}], temp=0.1))
        return bool(r.get("ok")), (r.get("review") or "") + (f" · corrigir: {r['corrigir']}" if r.get("corrigir") and not r.get("ok") else ""), int(r.get("nota") or (4 if r.get("ok") else 2))
    except Exception as e:
        return True, f"pente fino do Gemini indisponível ({str(e)[:80]}); passou na conferência do kit", 4


def legenda(titulo, spec):
    linhas = [f"{j['horario']} · {j['confronto'].title()} ({j['rotulo'].title()})" for j in spec["jogos"]]
    return f"{spec['data_dia_semana'].title()} de futebol no GOAT! ⚽️\n\n" + "\n".join(linhas) + "\n\nTudo ao vivo e de graça no Canal GOAT. 🐐"


def um_dia(dia, modo):
    dados = api("agenda-dados", dia=dia)
    trans = dados.get("transmissoes") or []
    if not [t for t in trans if (t.get("kind") or "") != "outro"]:
        print(dia, "sem transmissões cadastradas", flush=True)
        return
    if modo == "valer" and dados.get("existentes"):
        print(dia, "agenda já existe:", [c["title"] for c in dados["existentes"]], flush=True)
        return
    spec, titulo, pend = agenda.montar(dia, trans, dados.get("rodizio") or [])
    previa = ROOT / "previas" / f"agenda-{dia}.png"
    previa.parent.mkdir(exist_ok=True)
    ok_kit, erro = render(spec, previa)
    if not ok_kit:
        print(dia, "kit reprovou:", erro, flush=True)
        if modo != "valer":
            render(spec, previa, sem_conferencia=True)  # amostra: mostra mesmo assim, com o card sem foto
    ok, review, nota = pente_fino(previa, dia, titulo, trans) if ok_kit else (False, f"conferência do kit: {erro}", 1)
    print(dia, titulo, "| pente fino:", "OK" if ok else "REPROVADO", "|", review, "| sem foto:", pend, flush=True)
    (ROOT / "previas" / f"agenda-{dia}.json").write_text(json.dumps({"titulo": titulo, "ok": ok, "review": review, "sem_foto": pend, "spec": spec}, ensure_ascii=False, indent=1), encoding="utf-8")
    if modo != "valer":
        return
    criado = api("agenda-criar", {"dia": dia, "titulo": titulo, "legenda": legenda(titulo, spec),
                                   "brief": f"Entrega: véspera · Post: {titulo.split('· ')[-1]}\nAgenda montada pelo robô com as transmissões cadastradas."})
    if not criado.get("ok"):
        print(dia, "não criou:", criado, flush=True)
        return
    cid = criado["id"]
    if ok_kit:
        status, result = processar.arte({"id": f"ag-{dia}", "card_id": cid, "payload": {"n": 1, "spec": agenda.spec_para_kit(spec)}}, processar.oidc())
        if status != "feito":
            ok, review = False, f"envio da arte falhou: {result}"
    fontes = []
    for j in spec["jogos"]:
        f = j.get("foto") or ""
        if f.startswith("fotos/"):
            meta = json.loads((ROOT / f.rsplit("/", 1)[0] / "meta.json").read_text(encoding="utf-8"))
            for m in meta.get("fotos", []):
                if m["arquivo"] == f.rsplit("/", 1)[1]:
                    fontes.append({"label": f"{j['confronto'].title()} · {m.get('credito', '')}", "url": m.get("pagina") or m.get("url_imagem", "")})
    equipe = [{"nome": j["foto"][len("equipe:"):], "broadcast_id": j.get("broadcast_id"), "dia": dia}
              for j in spec["jogos"] if str(j.get("foto", "")).startswith("equipe:")]
    nota_txt = "Agenda feita pelo robô" + (f" · sem foto na biblioteca: {', '.join(pend)}" if pend else "")
    api("agenda-pronta", {"id": cid, "ok": ok and ok_kit, "score": nota, "review": f"Post: {titulo.split('· ')[-1]} · {review}",
                          "note": nota_txt if ok else f"{nota_txt} · Ajuste: {review}", "photo_sources": fontes,
                          "equipe": equipe if ok else [],
                          "log": f"{titulo}: {'na Mesa do Gestor' if ok and ok_kit else 'ficou em produção para ajuste'}"})


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "amostra"
    dias = sys.argv[2:] or [(datetime.now(SP).date() + timedelta(days=d)).isoformat() for d in (1, 2)]
    processar.fontes_privadas()
    processar.equipe_privada()
    for dia in dias:
        try:
            um_dia(dia, modo)
        except Exception as e:
            print(dia, "erro:", e, flush=True)
    run = lambda *a: subprocess.run(list(a), cwd=ROOT, check=False)
    run("git", "add", "previas", "arts", "fotos", "jobs", "tools/clubes.json")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode != 0:
        run("git", "commit", "-q", "-m", f"agenda do dia ({modo})")
        for _ in range(3):
            if run("git", "pull", "--rebase", "-q").returncode == 0 and run("git", "push", "-q").returncode == 0:
                break


if __name__ == "__main__":
    main()
