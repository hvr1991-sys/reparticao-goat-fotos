# Repartição GOAT · fotos e kit do designer

Repositório privado usado pelo agente **goat-designer** da Repartição GOAT.

## Como funciona
1. O designer acha a foto oficial no site ou perfil do clube e grava um pedido em `jobs/<id-do-card>.json`:
   ```json
   {"id": "<id-do-card>", "fotos": [{"url": "https://site-do-clube/...", "credito": "Foto: Nome / Clube", "rotulo": "Atleta"}]}
   ```
   A URL pode ser da imagem ou da página da notícia (o robô usa a imagem principal da página).
2. O GitHub Actions (`Baixar fotos`) baixa as imagens para `fotos/<id>/` e grava `meta.json` com origem, tamanho e erros.
3. O designer confere cada foto (sem marca d'água, resolução boa, foto do clube), monta a arte com `kit/render.py` e entrega no painel.

## Regras
- Só fotos de canais oficiais dos clubes ou enviadas pela equipe do Canal GOAT.
- Só fotos sem marca d'água. Nunca recortar, borrar ou editar para esconder marca d'água.
- A foto não é redesenhada: só recorte de enquadramento e o ajuste global GOAT_SPORTS_EDITORIAL.

## Kit
`kit/render.py` monta as peças da skill `canal-goat-artes` (agenda, jogo único, manchete, chamada, estatísticas) com o logo oficial e a Barlow Condensed:
```bash
pip install playwright pillow numpy && python3 -m playwright install chromium
python3 kit/render.py spec.json saida.png
```
