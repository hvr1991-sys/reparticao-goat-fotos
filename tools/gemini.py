#!/usr/bin/env python3
"""Designers da Repartição GOAT rodando no Google Gemini (economiza créditos do Claude).

Chamado pelo plantão (tools/processar.py). Para cada card em "producao" que precisa de arte:
 1. Gemini (com busca do Google) escreve o briefing, escolhe o tipo de peça e indica fotos
    de fontes OFICIAIS (site/sala de imprensa do clube ou da liga).
 2. O robô baixa as fotos (tools/baixar.py) e o Gemini confere cada uma olhando a imagem
    (foto limpa, sem marca d'água, sem texto/arte de terceiros, tema certo).
 3. O kit (kit/render.py) monta a arte; o Gemini revisa o PNG e corrige o spec uma vez se precisar.
 4. A arte vai ao painel e o card segue para o pente fino (braço direito, no Claude).
Nada é publicado em rede social. Chave: secret GEMINI_API_KEY do repositório.
"""
import base64, json, os, re, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://generativelanguage.googleapis.com/v1beta"
KEY = os.environ.get("GEMINI_API_KEY", "")
_modelo = None


def _req(path, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{API}/{path}", data=data, method="POST" if data else "GET",
                               headers={"x-goog-api-key": KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.load(resp)


def modelos():
    """GEMINI_MODEL (se definido) primeiro; depois os Flash disponíveis, do mais novo ao mais antigo."""
    global _modelo
    if _modelo is not None:
        return _modelo
    nomes = []
    try:
        for m in _req("models?pageSize=200").get("models", []):
            n = m["name"].split("/", 1)[1]
            if "generateContent" in m.get("supportedGenerationMethods", []) and "flash" in n \
                    and not re.search(r"image|tts|audio|live|thinking|exp", n):
                nomes.append(n)
    except Exception as e:
        print("lista de modelos indisponível:", e, flush=True)
    def chave(n):
        v = [int(x) for x in re.findall(r"\d+", n)[:2]] or [0]
        return (0 if "lite" in n else 1, 0 if "preview" in n else 1, v)
    nomes.sort(key=chave, reverse=True)
    if os.environ.get("GEMINI_MODEL"):
        nomes.insert(0, os.environ["GEMINI_MODEL"])
    _modelo = nomes or ["gemini-2.5-flash", "gemini-2.0-flash"]
    print("Gemini, ordem de modelos:", _modelo[:6], flush=True)
    return _modelo


def gerar(partes, busca=False, temp=0.6):
    """Tenta os modelos em ordem; se a busca do Google exigir cobrança, tenta sem busca."""
    global _modelo
    ultimo = None
    for usar_busca in ([True, False] if busca else [False]):
        for nome in list(modelos()):
            body = {"contents": [{"role": "user", "parts": partes}], "generationConfig": {"temperature": temp}}
            if usar_busca:
                body["tools"] = [{"google_search": {}}]
            try:
                out = _req(f"models/{nome}:generateContent", body)
            except urllib.error.HTTPError as e:
                det = e.read().decode(errors="ignore")[:300]
                ultimo = f"{nome}{' +busca' if usar_busca else ''}: HTTP {e.code} {det}"
                print("Gemini recusou:", ultimo, flush=True)
                if e.code in (400, 402, 403, 404, 429):
                    continue
                raise
            cand = (out.get("candidates") or [{}])[0]
            txt = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
            if txt:
                if nome != _modelo[0]:
                    _modelo = [nome] + [m for m in _modelo if m != nome]
                return txt
    raise RuntimeError(f"nenhum modelo do Gemini respondeu ({ultimo})")


def json_de(txt):
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", txt) or re.search(r"(\{[\s\S]*\})", txt)
    if not m:
        raise ValueError("Gemini não devolveu JSON")
    return json.loads(m.group(1))


def imagem(path):
    mime = "image/png" if str(path).lower().endswith(".png") else "image/jpeg"
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(Path(path).read_bytes()).decode()}}


def modelos_txt():
    linhas = []
    for f in sorted((ROOT / "modelos").glob("*/*.txt")):
        linhas.append(f"- {f.parent.name}/{f.stem}: {f.read_text(encoding='utf-8').strip()[:300]}")
    return "\n".join(linhas) or "(nenhuma nota de modelo)"


REGRAS = """Você é designer do Canal GOAT (@canalgoatbr), canal que TRANSMITE as competições (não é portal de notícia).
Regras fixas:
- Escreva em português do Brasil. Nunca invente número, placar, horário, frase ou fato: use só o que está no card,
  nas fontes ou no que você confirmar na busca (cite a fonte). Se não tiver dado confirmado, faça uma peça sem números.
- Texto da arte é para o DIA DO POST (pub_date): use dia da semana + data (ex.: SEX 27.11), nunca "hoje/amanhã" relativo à produção.
- Estilo do feed: frases curtas e emocionadas em caixa alta ("O DRAGÃO ESTÁ NA FRENTE!", "QUE DEFESAÇA!"), voz de torcedor.
- Nunca termos depreciativos. Amarelo #FFD318 só como detalhe (o kit já cuida disso).
- Fotos: só de fontes OFICIAIS (site/sala de imprensa do clube ou da liga, posts públicos dos perfis oficiais).
  Nada de agência (Getty, AP, Reuters, Imago...), nada com marca d'água, placar, texto ou arte pronta.
- Tipografia da marca: Helvetica Neue Medium e Bold (o kit aplica).
"""


def planejar(card, docs, fix=None):
    doc = "\n\n".join(d["content"][:6000] for d in docs if d["id"] == "goat-designer")
    kit = (ROOT / "kit" / "render.py").read_text(encoding="utf-8")
    pedido = f"""{REGRAS}
Instruções do agente designer (siga):
{doc}

Notas dos modelos de arte enviados pelo Gestor:
{modelos_txt()}

Motor de artes (kit/render.py) — use EXATAMENTE os tipos e campos que as funções leem:
```python
{kit}
```

CARD A PRODUZIR:
{json.dumps({k: card.get(k) for k in ("title", "league", "kind", "format", "why", "brief", "note", "ceo_comment", "sources", "pub_date", "due_date")}, ensure_ascii=False, indent=1)}
Transmissões do dia do post (dados reais, use na agenda do dia): {json.dumps(card.get("transmissoes") or [], ensure_ascii=False)}
{('ATENÇÃO, ajuste pedido pelo Gestor (prioridade): ' + card['ceo_comment']) if card.get('ceo_comment') else ''}
{('CORREÇÃO pedida na revisão da arte anterior: ' + fix) if fix else ''}

Responda SÓ com um bloco ```json com:
{{
 "brief": "começa com 'Entrega: DIA dd.mm · Post: DIA dd.mm' e descreve a peça (3-6 linhas)",
 "fotos": [{{"url": "página oficial ou imagem", "credito": "clube ou liga", "rotulo": "tema"}}],   // 0 a 4 candidatas; [] se a peça não usa foto
 "spec": {{ ... spec do kit, com "marca": "logo"; onde entra foto use "FOTO" (o robô troca pela foto aprovada) ... }},
 "foto_obrigatoria": true/false
}}"""
    return json_de(gerar([{"text": pedido}], busca=True))


def foto_ok(path, card):
    r = json_de(gerar([imagem(path), {"text": f"""Avalie esta foto para uma arte do Canal GOAT sobre: "{card['title']}" ({card.get('league')}).
Reprove se: marca d'água ou crédito de agência visível; placar, texto, logos de arte pronta ou faixa de patrocinador sobreposta;
não for do tema/atleta/clube certo; baixa qualidade. Responda só ```json {{"ok": true/false, "motivo": "curto"}}```"""}], temp=0.1))
    return bool(r.get("ok")), str(r.get("motivo", ""))


def revisar_arte(png, card):
    r = json_de(gerar([imagem(png), {"text": f"""Revise esta arte do Canal GOAT (post {card.get('pub_date')}) sobre "{card['title']}".
Reprove se: texto cortado ou saindo da arte; erro de português; data/dia errados para o post; foto cobrindo rosto com texto;
informação que parece inventada. Responda só ```json {{"ok": true/false, "corrigir": "o que mudar no spec, curto"}}```"""}], temp=0.1))
    return bool(r.get("ok")), str(r.get("corrigir", ""))


def produzir(card, docs, baixar_fotos, montar, informar):
    """baixar_fotos(card_id, itens, tag) -> (pasta, [arquivos]); montar(card_id, spec) -> (status, result, png)."""
    cid, designer = card["id"], card["designer"]
    try:
        fix, ultima = None, None
        for tentativa in range(2):
            plano = planejar(card, docs, fix)
            spec = dict(plano.get("spec") or {})
            fontes, escolhida = [], None
            if plano.get("fotos"):
                pasta, arquivos = baixar_fotos(cid, plano["fotos"][:4], f"g{tentativa}")
                for i, (arq, meta) in enumerate(arquivos):
                    if meta.get("baixa_resolucao"):
                        continue
                    ok, motivo = foto_ok(ROOT / arq, card)
                    print(f"  foto {arq}: {'ok' if ok else 'reprovada'} {motivo}", flush=True)
                    if ok:
                        escolhida = arq
                        fontes = [{"label": meta.get("credito") or "fonte oficial", "url": meta.get("pagina") or meta.get("url_imagem", "")}]
                        break
            uso_foto = any(v == "FOTO" for v in spec.values()) or any((j or {}).get("foto") == "FOTO" for j in spec.get("jogos", []) or [])
            if uso_foto and not escolhida:
                if plano.get("foto_obrigatoria") or spec.get("tipo") in ("chamada", "jogo_unico"):
                    informar({"id": cid, "brief": plano.get("brief", ""), "note": ((card.get("note") or "") + " · Foto pendente: nenhuma foto oficial limpa encontrada (designer Gemini).").strip(" ·"),
                              "designer": designer, "task": "Foto pendente", "log": f"Foto pendente: {card['title']}"})
                    return
            for k in list(spec):
                if spec[k] == "FOTO":
                    if escolhida:
                        spec[k] = escolhida
                    else:
                        spec.pop(k)
            for j in spec.get("jogos", []) or []:
                if j.get("foto") == "FOTO":
                    if escolhida:
                        j["foto"] = escolhida
                    else:
                        j.pop("foto")
            spec.setdefault("marca", "logo")
            status, result, png = montar(cid, spec)
            if status != "feito":
                fix = f"o kit deu erro: {result.get('erro', '')[:300]}"
                ultima = result
                continue
            ok, corrigir = revisar_arte(png, card)
            ultima = result
            if ok or tentativa == 1:
                informar({"id": cid, "brief": plano.get("brief", ""), "photo_sources": fontes, "stage": "pente",
                          "note": "Arte feita pelo designer (Gemini)" + ("" if ok else f" · revisar: {corrigir}"),
                          "designer": designer, "task": f"Entregou: {card['title']}"[:120],
                          "log": f"Arte pronta (Gemini) para o pente fino: {card['title']}"})
                return
            fix = corrigir
        informar({"id": cid, "note": (card.get("note") or "") + f" · Designer Gemini não conseguiu montar: {json.dumps(ultima, ensure_ascii=False)[:300]}",
                  "designer": designer, "task": "Erro na arte", "log": f"Erro na arte (Gemini): {card['title']}"})
    except Exception as e:
        print("gemini erro", cid, e, flush=True)
        informar({"id": cid, "note": ((card.get("note") or "") + f" · Designer Gemini falhou: {str(e)[:200]}").strip(" ·"), "designer": designer, "task": "Erro na arte",
                  "log": f"Designer Gemini falhou em {card['title']}: {str(e)[:150]}"})
