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
import json, os, re, sys, unicodedata, hashlib
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.photo_policy import biblioteca_verified, photo_digest
from tools.openrouter_adapter import gerar_json, ProviderUnavailable
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
    return biblioteca_verified(ROOT)


def _bate(palavras, texto):
    return any(re.search(rf"(^|-){re.escape(p)}(-|$)", texto) for p in palavras)


def candidatas(confronto, fotos, usadas, n=4):
    """As melhores fotos da biblioteca para o jogo (time da casa vale mais), sem repetir no dia."""
    partes = [p.strip() for p in re.split(r"\s+X\s+", confronto.upper(), maxsplit=1)]
    a = palavras_time(partes[0]) if partes else set()
    b = palavras_time(partes[1]) if len(partes) > 1 else set()
    notas = []
    for f in fotos:
        if f["arquivo"] in usadas or f["sha256"] in usadas:
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
    """Revisão visual gratuita obrigatória. Falha ou ausência nunca escolhe a primeira foto."""
    if not cands:
        return None, "sem foto verificada na biblioteca"
    if not os.environ.get("OPENROUTER_API_KEY"):
        return None, "revisão indisponível: OpenRouter gratuito não configurado"
    partes = []
    for i, path in enumerate(cands, 1):
        partes += [{"text": f"Foto candidata {i}:"}, _miniatura(path, 768)]
    partes.append({"text": f"""Você revisa fotos do Canal GOAT. Escolha uma foto para {confronto} ({campeonato}).
O card usa uma faixa horizontal de 382×111px à direita, rosto principal visível e desobstruído.
Reprove fotos de costas, árbitro/torcida, fotografia aberta demais, placar, texto ou gráfico incorporado,
arte pronta, marca d'água, clube diferente dos dois informados ou outra modalidade.
Nunca redesenhe pessoas, uniformes, escudos ou patrocinadores. Nunca remova marcas d'água.
Use somente as imagens fornecidas. Incerteza significa reprovação.
Retorne JSON {{"ok": true/false, "foto": número de 1 a {len(cands)} ou 0 se reprovou todas, "motivo": "curto"}}.
Não basta a foto estar disponível: você precisa realmente avaliá-la."""})
    try:
        def valid(response):
            return (type(response.get("ok")) is bool and type(response.get("foto")) is int
                    and 0 <= response["foto"] <= len(cands) and isinstance(response.get("motivo"), str))
        response = gerar_json(partes, validator=valid, temp=0.1)
        number = response["foto"]
        if response["ok"] is True and 1 <= number <= len(cands):
            return cands[number - 1], f"revisão visual: {response['motivo']}"
        return None, f"revisão reprovou as {len(cands)} candidatas: {response['motivo']}"
    except (ProviderUnavailable, ValueError, TypeError, KeyError, OSError):
        return None, "revisão indisponível: nenhuma foto liberada"


def foco(arquivo, altura=111):
    """Enquadra o rosto principal no card (área da foto 382 x altura do card); sem rosto, o terço de cima."""
    sys.path.insert(0, str(ROOT / "kit"))
    try:
        from render import foco_rosto
        f = foco_rosto(ROOT / arquivo, caixa=(382, altura), centro=0.62)
        return "60% 25%" if f == "50% 14%" else f
    except Exception:
        return "60% 25%"


def horario(hhmm):
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2})(?::\d{2})?)?", str(hhmm or ""))
    if not match or int(match[1]) > 23 or int(match[2] or 0) > 59:
        raise ValueError("Transmissão sem horário válido: revisar agenda cadastrada")
    hour, minute = int(match[1]), int(match[2] or 0)
    return f"{hour}H" + (f"{minute:02d}" if minute else "")


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


def _foto_escalado(nome, usadas):
    """Escolha determinística de foto real da equipe, sem repetir os bytes no mesmo dia."""
    key = hashlib.sha256(norm(nome).encode()).hexdigest()[:16]
    for path in sorted((ROOT / "equipe" / "private").glob(f"{key}-*.jpg")):
        digest = photo_digest(path)
        if digest not in usadas:
            return "equipe:" + path.name, digest
    return None, None


def montar(dia, transmissoes, rodizio, used_photo_hashes=None, used_photo_files=None, used_photo_urls=None):
    d = date.fromisoformat(dia)
    known_urls = set(used_photo_urls or ())
    fotos = [f for f in biblioteca() if f.get("url_imagem") not in known_urls and f.get("pagina") not in known_urls]
    n_cards = len([t for t in transmissoes if (t.get("kind") or "").lower() != "outro"])
    usadas, equipe_usada, jogos, pendencias = set(used_photo_hashes or ()) | set(used_photo_files or ()), set(), [], []
    if n_cards == 0:
        pendencias.append("Nenhuma transmissão válida cadastrada")
    for t in sorted(transmissoes, key=lambda x: x.get("time") or ""):
        kind = (t.get("kind") or "").lower()
        if kind == "outro":
            continue
        titulo = str(t.get("title") or "").upper()
        comp = str(t.get("competition") or "").upper()
        if kind == "programa":
            nome, _, sobre = titulo.partition(" · ")
            rotulo = f"PROGRAMA · PRÉ-JOGO DE {sobre}" if " X " in sobre else "PROGRAMA"
            card = {"rotulo": rotulo, "horario": horario(t.get("time")), "confronto": nome or comp}
            pessoa = escolher_equipe(t.get("participantes"), rodizio, equipe_usada)
            foto, digest = _foto_escalado(pessoa, usadas) if pessoa else (None, None)
            if foto:
                card.update(foto=foto, broadcast_id=t.get("id"), equipe_nome=pessoa)
                equipe_usada.add(pessoa)
                usadas.add(digest)
            else:
                pendencias.append(f"Programa {nome or comp}: falta foto real da pessoa escalada")
            jogos.append(card)
            continue
        confronto = re.sub(r"\s*\(.*?\)", "", titulo).strip()
        card = {"rotulo": comp, "horario": horario(t.get("time")), "confronto": confronto}
        foto, motivo = escolher_foto(confronto, comp, candidatas(confronto, fotos, usadas))
        if not foto and os.environ.get("OPENROUTER_API_KEY") and "indisponível" not in motivo:
            from tools import fotos_oficiais
            for time_ in [p.strip() for p in re.split(r"\s+X\s+", confronto, maxsplit=1)]:
                fresh = set(fotos_oficiais.buscar(time_, comp, f"{confronto} · {time_}"))
                novas = [item["arquivo"] for item in biblioteca()
                         if item["arquivo"] in fresh and item["sha256"] not in usadas
                         and item.get("url_imagem") not in known_urls and item.get("pagina") not in known_urls]
                if novas:
                    foto, motivo = escolher_foto(confronto, comp, novas[:4])
                    if foto or "indisponível" in motivo:
                        break
        print(f"  {confronto}: {foto or '-'} ({motivo})", file=sys.stderr, flush=True)
        if foto:
            usadas.update((foto, photo_digest(ROOT / foto)))
            card["foto"], card["foco"] = foto, foco(foto, 111)
        else:
            pendencias.append(f"{confronto}: {motivo}")
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
        j.pop("equipe_nome", None)
    return s


if __name__ == "__main__":
    dados = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    spec, titulo, pend = montar(dados["dia"], dados["transmissoes"], dados.get("rodizio", []))
    print(titulo)
    print(json.dumps(spec, ensure_ascii=False, indent=1))
    if pend:
        print("SEM FOTO NA BIBLIOTECA:", pend)
    if len(sys.argv) > 2 and not pend:
        sys.path.insert(0, str(ROOT / "kit"))
        import render
        s = spec_para_kit(spec)
        for j in s["jogos"]:
            if j.get("foto") and not j["foto"].startswith("equipe:"):
                j["foto"] = str(ROOT / j["foto"])
        render.render(render.resolver_equipe(s) if hasattr(render, "resolver_equipe") else s, sys.argv[2])
        print("prévia:", sys.argv[2])
