"""Experimental GOAT designer: original orchestration with free OpenRouter.
Magnific visual resources are optional and not yet wired into this module.
No production activation.
"""
import base64, json, re
from pathlib import Path
try:
    from .openrouter_adapter import gerar
except ImportError:
    from openrouter_adapter import gerar
ROOT = Path(__file__).resolve().parent.parent

def json_de(txt):
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", txt) or re.search(r"(\{[\s\S]*\})", txt)
    if not m:
        raise ValueError("OpenRouter não devolveu JSON")
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
- Tipografia da marca: Barlow Condensed para feed; Inter Tight quando a skill especificar.
"""


def planejar(card, docs, fix=None):
    doc = "\n\n".join(d["content"] for d in docs if d["id"] in ("goat-designer", card.get("designer")))
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
    return r.get("ok") is True, str(r.get("motivo", ""))


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
                    informar({"id": cid, "brief": plano.get("brief", ""), "note": ((card.get("note") or "") + " · Foto pendente: nenhuma foto oficial limpa encontrada (designer OpenRouter).").strip(" ·"),
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
            spec["marca"] = "logo"
            status, result, png = montar(cid, spec)
            if status != "feito":
                fix = f"o kit deu erro: {result.get('erro', '')[:300]}"
                ultima = result
                continue
            ok, corrigir = revisar_arte(png, card)
            ultima = result
            if ok:
                informar({"id": cid, "brief": plano.get("brief", ""), "photo_sources": fontes, "stage": "pente",
                          "note": "Arte feita pelo designer (OpenRouter)" + ("" if ok else f" · revisar: {corrigir}"),
                          "designer": designer, "task": f"Entregou: {card['title']}"[:120],
                          "log": f"Arte pronta (OpenRouter) para o pente fino: {card['title']}"})
                return
            fix = corrigir
        informar({"id": cid, "note": (card.get("note") or "") + f" · Designer OpenRouter não conseguiu montar: {json.dumps(ultima, ensure_ascii=False)[:300]}",
                  "designer": designer, "task": "Erro na arte", "log": f"Erro na arte (OpenRouter): {card['title']}"})
    except Exception as e:
        print("openrouter erro", cid, e, flush=True)
        if "HTTP 402" in str(e) or "HTTP 429" in str(e):
            # sem crédito/limite no Google: não mexe no card, só avisa no livro de ponto
            informar({"id": cid, "designer": designer, "task": "Aguardando crédito do OpenRouter",
                      "log": "Designer OpenRouter parado: o provedor gratuito está indisponível ou no limite (HTTP 402/429). Tento de novo em 40 min."})
            return
        informar({"id": cid, "note": ((card.get("note") or "") + f" · Designer OpenRouter falhou: {str(e)[:200]}").strip(" ·"), "designer": designer, "task": "Erro na arte",
                  "log": f"Designer OpenRouter falhou em {card['title']}: {str(e)[:150]}"})
