---
name: "canal-goat-artes"
description: "Use para criar artes do Canal GOAT no padrão da marca: agenda do dia, agenda de jogo único, tarjas de vídeo, telas de transmissão e pré-jogo, header do YouTube e posts."
---

# Artes do Canal GOAT

Guia para produzir as artes do Canal GOAT no padrão atual da marca. Responda sempre em português.

## Arquivos incluídos

Na pasta `arquivos/` desta skill:
- **Marca:** `logo-goat-amarelo.png` e `bodinho.png`.
- **Fundos:** `fundo-estadio-pb.png` (estádio em preto e branco, usado no header).
- **Modelos de referência:** `modelo-agenda-do-dia.png`, `modelo-agenda-jogo-unico.png`, `modelo-tarja-aspas-tela-cheia.png`, `modelo-tarja-aspas-tela-dividida.png`, `modelo-tarja-para-videos.png` e `modelo-header-youtube.png`. Siga esses modelos ao montar cada peça.
- **Fontes:** `fontes/` com Barlow Condensed (300, 500, 600, 700) e Inter Tight (400, 500, 700, 800).

Use esses arquivos direto da skill. Só peça ao usuário o que não estiver aqui.

## Antes de começar

Peça ao usuário o que faltar. Nunca invente nada disso:
- **Modelo atualizado:** se a peça mudou desde os modelos em `arquivos/`, peça o mais recente.
- **Dados do dia:** horários, confrontos, campeonato e programa.
- **Fotos:** uma por card ou peça, com o nome da equipe ou do atleta.

Dados reais (placar, estatística, frase de atleta) só entram se o usuário passar. Em amostras, use "Nome Sobrenome", números de exemplo e o selo "DADOS ILUSTRATIVOS".

Antes de entregar uma peça nova ou um modelo novo, mostre uma prévia para aprovação.

## Sistema visual

**Cores**
- Amarelo GOAT: #FFD318. É sempre esse amarelo, sem variações.
- Preto: #08080A, com superfícies em #121214 e #141416.
- Branco: #F5F5F2. Textos secundários em rgba(245,245,242,0.62).
- Vermelho: #E5484D, só para o selo AO VIVO.
- O amarelo é detalhe: o X do confronto, o dia da semana, o campeonato, um filete, um ponto. Nunca use como fundo de bloco grande nas peças do dia a dia.

**Tipografia**
- **Barlow Condensed:** agendas e tarjas de vídeo. Títulos em 600–700, maiúsculas. Rótulos pequenos com espaçamento largo entre letras.
- **Inter Tight:** telas de transmissão, pré-jogo, thumbs, Smart TV, header do YouTube e apresentações. Títulos em 800 com espaçamento negativo; textos em 400–500.

**Marca**
- O logo GOAT e o bodinho se revezam: cada arte usa só um dos dois, nunca os dois juntos.
- No feed, alterne: um post com o logo, o seguinte com o bodinho.
- Não repita o logo dentro da mesma peça.

**Fotos**
- Fotos precisam ter destaque. Não cubra o rosto nem a jogada com caixas de texto.
- A transição entre foto e fundo é sempre um degradê bem suave, sem emenda visível.
- Em peças com vários atletas, todos ficam proporcionalmente do mesmo tamanho: mesmo tamanho de rosto, olhos na mesma linha e corte do tronco no mesmo ponto. Se alguém precisar de destaque, ele vai para o primeiro plano, não fica maior.
- Equalize as fotos antes de montar. Preset GOAT_SPORTS_EDITORIAL:
  - contraste ×1,075
  - saturação ×0,94
  - nitidez ×1,06
  - realces levemente quentes (R +0,012, B −0,004)
  - sombras levemente frias (R −0,006, B +0,010)
- Se uma foto ficar opaca ou destoar, iguale brilho, contraste e saturação à média das outras.
- Fotos de baixa resolução: avise o usuário e peça versões maiores.
- Fotos com marca d'água (Getty e outras): recorte para a marca não aparecer ou peça outra foto.

## Peças

### Agenda do dia (feed 1080×1350)

**Fundo e cabeçalho**
- **Fundo:** preto com estádio bem desfocado e escuro.
- **Título:** "AGENDA" em Barlow Condensed 700 e "DO DIA" em 300, centralizados no topo.
- **Data:** em uma linha, com o dia da semana em amarelo e o resto em cinza claro. Exemplo: "TERÇA-FEIRA 17 DE NOVEMBRO".

**Cards**
- Um por transmissão, 910×111, cantos de 16px, fundo cinza-escuro com leve degradê e filete amarelo de 3px à esquerda.
- Os cards ficam centralizados na vertical entre a data e o logo.
- Dentro de cada card:
  - **Horário:** em Barlow Condensed 600, maiúsculo. Exemplos: "21H", "23H30", "16H30".
  - **Divisória:** um filete fino entre o horário e o resto.
  - **Rótulo:** amarelo e pequeno, com espaçamento largo. Exemplos: "CONCACAF NATIONS LEAGUE", "REPRISE · BRASILEIRÃO SÉRIE B", "PROGRAMA ESPECIAL SÉRIE B".
  - **Confronto:** em branco, com o X em amarelo.
  - **Foto:** à direita, ocupando cerca de 42% do card, com o rosto à direita e degradê suave para o fundo à esquerda.
- Programa sem foto: card sem imagem e título sem X.

**Rodapé:** logo GOAT pequeno, centralizado.

### Agenda de jogo único (feed)
- **Foto:** do jogo ocupando a arte inteira, com degradê escuro na base.
- **Topo:** "AGENDA DO DIA" e a data, em letras pequenas.
- **Base:** o campeonato em rótulo amarelo pequeno e depois "22H | CANADÁ X GUATEMALA" numa linha, com o X amarelo. Ajuste o tamanho para caber na largura.
- **Logo:** pequeno, abaixo da linha do jogo.

### Tarjas de vídeo (9:16)

As três tarjas usam Barlow Condensed em maiúsculas, num bloco escuro translúcido com cantos arredondados e um filete amarelo grosso no topo.

- **Aspas em tela cheia:**
  - Bloco na altura do peito do personagem, sem cobrir o rosto.
  - Aspas amarelas grandes: a de abertura no canto superior esquerdo, a de fechamento no canto inferior direito.
  - Frase em branco, em duas linhas.
  - Crédito ou contexto em amarelo, numa linha menor abaixo da frase.
- **Aspas em tela dividida:**
  - Dois vídeos empilhados, com a tarja de aspas ocupando a largura toda na divisão.
  - Legenda da fala em amarelo, logo acima da tarja, em duas linhas.
- **Tarja para vídeos:** o mesmo bloco com filete amarelo, só com o texto em branco, em duas linhas, sem aspas.
- **Logo:** pequeno no canto superior esquerdo.

### Telas de transmissão e pré-jogo (1920×1080, Inter Tight)
- **Placar e intervalo:** placar e caracteres em vidro escuro translúcido com borda fina.
- **Pré-jogo:** fundo com foto bem desfocada. Modelos disponíveis:
  - últimos 5 jogos
  - destaques (um atleta de cada time frente a frente, com tabela de comparação no centro)
  - classificação
  - escalações em campinho
  - confronto direto
  - ficha do jogo
  - desfalques
  - enquete do chat
  - contagem regressiva
- **Cabeçalho das telas:** rótulo amarelo pequeno e título grande em branco. O logo ou o bodinho fica no canto superior direito.

### Thumb de jogo ao vivo (YouTube 1280×720)
- Fundo preto com a foto à direita, saindo em degradê suave.
- Selo vermelho "AO VIVO", o campeonato e o confronto.
- Não coloque data, horário nem "transmissão completa".

### Header do YouTube (2560×1440)
- Tudo o que importa fica dentro da área visível em todos os aparelhos: 1546×423, centralizada (x 507–2053, y 508–931).
- Fundo: estádio em preto e branco, levemente escurecido, com granulado e vinheta.
- **Logo e texto à esquerda:**
  - Logo GOAT.
  - Frase "PAIXÃO PELO ESPORTE" em branco e "NÃO SE EXPLICA, SE TRANSMITE." em amarelo, em Inter Tight 700–800, grande e legível.
  - Botão "INSCREVA-SE" com o ícone do YouTube.
- **Atletas à direita:** recortados do peito para cima, todos do mesmo tamanho, com Cristiano Ronaldo sempre em primeiro plano.
- Sem contorno brilhante nos atletas, só uma sombra suave para separar quem está atrás.
- Entregue também um mockup com o header aplicado na página do canal.

## Fluxo de trabalho

1. **Confira os dados:** horários, nomes e campeonatos, e pergunte o que faltar.
2. **Prepare as fotos:** recorte quando precisar, equalize pelo preset e confira a resolução.
3. **Monte a peça** seguindo as medidas acima.
4. **Revise:** amarelo #FFD318, logo ou bodinho (nunca os dois), degradês sem emenda, ninguém fora de proporção, texto dentro da área segura.
5. **Entregue** o PNG em tamanho final. Quando for substituição, mande o arquivo completo, nunca só um trecho.