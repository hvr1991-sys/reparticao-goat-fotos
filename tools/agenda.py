#!/usr/bin/env python3
"""Agenda do dia montada pelo robô, sem Claude e sem Gemini.

Lê as transmissões do dia (rg_broadcasts), escolhe as fotos dos jogos na biblioteca do
repositório (fotos/*/meta.json, todas de fontes oficiais e já conferidas) e a foto de quem
está escalado nos programas (rodízio da equipe), e monta o spec do kit (kit/render.py).

Regras (as mesmas da skill canal-goat-artes e das lições do Gestor):
- um card por transmissão, na ordem do horário; horário como 11H20 / 20H;
- todo jogo leva foto; foto não se repete no mesmo dia; o rosto/lance fica enquadrado;
- programa leva a foto de alguém escalado, pelo rodízio (quem saiu há mais tempo primeiro);
- dia com um jogo só vira o modelo de jogo único (o kit faz a troca);
- nada inventado: só o que está na agenda de transmissões.

Uso local (prévia): python3 tools/agenda.py dados.json saida.png
  dados.json = {"dia": "2026-11-28", "transmissoes": [...], "rodizio": [...]}
"""
import json, re, sys, unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIAS = ["SEGUNDA-FEIRA", "TERÇA-FEIRA", "QUARTA-FEIRA", "QUINTA-FEIRA", "SEXTA-FEIRA", "SÁBADO", "DOMINGO"]
DIAS_CURTOS = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]
MESES = ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
# nomes em português x como aparecem nas fontes oficiais (alemão/inglês)
APELIDOS = {
    "colonia": ["koln", "cologne", "1-fc-koln", "effzeh"],
    "bayern": ["bayern", "fcbayern", "fc-bayern"],
    "berlim": [],
    "hertha": ["hertha", "olympiastadion"],
    "karlsruher": ["karlsruher", "ksc"],
    "schalke": ["schalke", "s04"],
    "paderborn": ["paderborn", "scp07"],
    "estudiantes": ["estudiantes", "pincha"],
    "atletico-go": ["atletico-go", "atletico-goianiense", "dragao"],
    "nassr": ["nassr", "ronaldo"],
}
GENERICAS = {"al", "fc", "sc", "club", "de", "da", "do", "x", "clube", "esporte", "1", "04", "ac", "cf", "berlim"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def palavras_time(nome):
    """Palavras que identificam o time (sem 'AL', 'FC', país entre parênteses...)."""
    nome = re.sub(r"\(.*?\)", "", nome)
    ps = [p for p in norm(nome).split("-") if p and p not in GENERICAS and len(p) >= 3]
    extra = []
    for p in ps:
        extra += APELIDOS.get(p, [])
    if norm(nome) in APELIDOS:
        extra += APELIDOS[norm(nome)]
    return set(ps + extra)


def biblioteca():
    fotos = []
    for meta in sorted((ROOT / "fotos").glob("*/meta.json")):
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            continue
        for f in m.get("fotos", []):
            if not f.get("ok") or f.get("baixa_resolucao"):
                continue
            arq = meta.parent / f["arquivo"]
            if not arq.exists():
                continue
            texto = "-".join(norm(f.get(k, "")) for k in ("rotulo", "pagina", "credito"))
            fotos.append({"arquivo": str(arq.relative_to(ROOT)), "texto": texto, "largura": f.get("largura", 0)})
    return fotos


def _bate(palavras, texto):
    return any(re.search(rf"(^|-){re.escape(p)}(-|$)", texto) for p in palavras)


def candidatas(confronto, fotos, usadas, n=4):
    """As melhores fotos da biblioteca para o jogo (time da casa vale mais), sem repetir no dia."""
    partes = [p.strip() for p in re.split(r"\s+X\s+", confronto.upper(), maxsplit=1)]
    a = palavras_time(partes[0]) if partes else set()
    b = palavras_time(partes[1]) if len(partes) > 1 else set()
    notas = []
    for f in fotos:
        if f["arquivo"] in usadas:
            continue
        nota = (3 if _bate(a, f["texto"]) else 0) + (2 if _bate(b, f["texto"]) else 0)
        if nota >= 2:
            notas.append((nota + min(f["largura"], 2000) / 10000, f["arquivo"]))
    return [arq for _, arq in sorted(notas, reverse=True)[:n]]


def _miniatura(arquivo, lado=512):
    from PIL import Image
    import io, base64
    im = Image.open(ROOT / arquivo).convert("RGB")
    im.thumbnail((lado, lado))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}}


def escolher_foto(confronto, campeonato, cands):
    sys.path.insert(0, str(ROOT / "tools"))
    """Gemini olha as candidatas e escolhe a melhor para o card (ou nenhuma).
    Sem GEMINI_API_KEY, fica com a primeira da biblioteca."""
    import os
    if not cands:
        return None, "sem foto na biblioteca"
    if not os.environ.get("GEMINI_API_KEY"):
        return cands[0], "biblioteca (sem revisão do Gemini)"
    sys.path.insert(0, str(ROOT / "tools"))
    import gemini
    partes = []
    for i, c in enumerate(cands, 1):
        partes += [{"text": f"Foto {i}:"}, _miniatura(c)]
    partes.append({"text": f"""Você é designer do Canal GOAT. Escolha a foto para o card da agenda do jogo {confronto} ({campeonato}).
O card mostra a foto numa faixa horizontal estreita à direita (corte largo e baixo, centrado no rosto principal).
O jogador em destaque precisa estar grande, de frente e com o rosto visível; goleiro de costas, árbitro, torcida ou foto aberta demais não servem.
Reprove fotos com placar, texto, gráfico, logo de arte pronta, marca d'água, de outro clube que não seja um dos dois do jogo,
ou que não sejam de futebol/jogadores. Prefira lance de jogo ou comemoração com jogadores do time da casa (o primeiro), rosto visível.
Responda só ```json {{"foto": <número ou 0 se nenhuma serve>, "motivo": "curto"}}```"""})
    try:
        r = gemini.json_de(gemini.gerar(partes, temp=0.1))
        n = int(r.get("foto") or 0)
        if 1 <= n <= len(cands):
            return cands[n - 1], f"Gemini: {r.get('motivo', '')}"
        return None, f"Gemini reprovou as {len(cands)} candidatas: {r.get('motivo', '')}"
    except Exception as e:
        return cands[0], f"biblioteca (Gemini indisponível: {str(e)[:80]})"


def foco(arquivo, altura=160):
    """Enquadra o rosto principal no card (área da foto 422 x altura do card); sem rosto, o terço de cima."""
    sys.path.insert(0, str(ROOT / "kit"))
    try:
        from render import foco_rosto
        f = foco_rosto(ROOT / arquivo, caixa=(422, altura))
        return "60% 25%" if f == "50% 14%" else f
    except Exception:
        return "60% 25%"


def horario(hhmm):
    h, _, m = str(hhmm).partition(":")
    h = str(int(h)) if h.isdigit() else h
    return f"{h}H" if m in ("", "00") else f"{h}H{m}"


def escolher_equipe(participantes, rodizio, ja_usados):
    """Entre os escalados com foto, quem saiu há mais tempo (nunca usado primeiro)."""
    nomes = []
    for p in participantes or []:
        nome = p.get("nome") if isinstance(p, dict) else p
        if not nome:
            continue
        n = norm(nome)
        cands = [r for r in rodizio if r.get("fotos") and (norm(r["nome"]) == n or n in [norm(x) for x in (r.get("apelidos") or [])])]
        if not cands:
            cands = [r for r in rodizio if r.get("fotos") and n and n in norm(r["nome"])]
        if len(cands) == 1:
            nomes.append(cands[0])
    nomes.sort(key=lambda r: (r["nome"] in ja_usados, r.get("ultimo_uso") or ""))
    return nomes[0]["nome"] if nomes else None


def montar(dia, transmissoes, rodizio):
    d = date.fromisoformat(dia)
    fotos = biblioteca()
    n_cards = len([t for t in transmissoes if (t.get("kind") or "").lower() != "outro"])
    # mesma conta do kit (render.agenda) para a altura de cada card
    k = min(1.0, (850 - (n_cards - 1) * 20) / (n_cards * 160)) if n_cards else 1.0
    altura_card = int(160 * k)
    usadas, equipe_usada, jogos, pendencias = set(), set(), [], []
    for t in sorted(transmissoes, key=lambda x: x.get("time") or ""):
        kind = (t.get("kind") or "").lower()
        if kind == "outro":
            continue  # narração/apoio do mesmo jogo: não vira card
        titulo = str(t.get("title") or "").upper()
        comp = str(t.get("competition") or "").upper()
        if kind == "programa":
            nome, _, sobre = titulo.partition(" · ")
            rotulo = f"PROGRAMA · PRÉ-JOGO DE {sobre}" if " X " in sobre else "PROGRAMA"
            card = {"rotulo": rotulo, "horario": horario(t.get("time")), "confronto": nome or comp}
            pessoa = escolher_equipe(t.get("participantes"), rodizio, equipe_usada)
            if pessoa:
                card["foto"] = f"equipe:{pessoa}"
                card["broadcast_id"] = t.get("id")
                equipe_usada.add(pessoa)
            jogos.append(card)
            continue
        confronto = re.sub(r"\s*\(.*?\)", "", titulo).strip()
        card = {"rotulo": comp, "horario": horario(t.get("time")), "confronto": confronto}
        foto, motivo = escolher_foto(confronto, comp, candidatas(confronto, fotos, usadas))
        if not foto and __import__("os").environ.get("GEMINI_API_KEY"):
            # nada bom na biblioteca: busca no site oficial dos clubes (casa primeiro)
            import fotos_oficiais
            for time_ in [p.strip() for p in re.split(r"\s+X\s+", confronto, maxsplit=1)]:
                novas = [n for n in fotos_oficiais.buscar(time_, comp, f"{confronto} · {time_}") if n not in usadas]
                if novas:
                    foto, motivo = escolher_foto(confronto, comp, novas[:4])
                    if foto:
                        motivo = f"site oficial · {motivo}"
                        break
        print(f"  {confronto}: {foto or '-'} ({motivo})", file=sys.stderr, flush=True)
        if foto:
            usadas.add(foto)
            card["foto"], card["foco"] = foto, foco(foto, altura_card)
        else:
            pendencias.append(confronto)
        jogos.append(card)
    spec = {"tipo": "agenda", "jogos": jogos, "marca": "logo",
            "data_dia_semana": DIAS[d.weekday()], "data_resto": f"{d.day} DE {MESES[d.month - 1]}"}
    titulo = f"AGENDA GOAT · {DIAS_CURTOS[d.weekday()]} {d.day:02d}.{d.month:02d}"
    return spec, titulo, pendencias


def spec_para_kit(spec):
    """Tira os campos internos (broadcast_id) antes de mandar ao kit."""
    s = json.loads(json.dumps(spec))
    for j in s.get("jogos", []):
        j.pop("broadcast_id", None)
    return s


if __name__ == "__main__":
    dados = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    spec, titulo, pend = montar(dados["dia"], dados["transmissoes"], dados.get("rodizio", []))
    print(titulo)
    print(json.dumps(spec, ensure_ascii=False, indent=1))
    if pend:
        print("SEM FOTO NA BIBLIOTECA:", pend)
    if len(sys.argv) > 2:
        sys.path.insert(0, str(ROOT / "kit"))
        import render
        s = spec_para_kit(spec)
        for j in s["jogos"]:
            if j.get("foto") and not j["foto"].startswith("equipe:"):
                j["foto"] = str(ROOT / j["foto"])
        render.render(render.resolver_equipe(s) if hasattr(render, "resolver_equipe") else s, sys.argv[2])
        print("prévia:", sys.argv[2])
