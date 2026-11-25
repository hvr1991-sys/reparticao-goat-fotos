# Repartição GOAT · execução editorial e artes

Executor do [painel GOAT](https://reparticao-goat.lovable.app/). Este repositório público guarda o código, a skill visual original e os recursos visuais autorizados. Instruções privadas dos agentes e aprendizados são lidos do backend autenticado em cada rodada.

## Provedores e identidade visual

- **Magnific** é o provedor de geração visual para cenários adequados ao briefing. Fotos de atletas, apresentadores, uniformes, escudos e patrocinadores continuam reais.
- **OpenRouter gratuito** faz planejamento, texto e revisão visual. O catálogo precisa confirmar preço zero, capacidade necessária e modelo `:free`; o modelo efetivo e o custo da resposta também são conferidos. Gemini não participa do fluxo ativo.
- `kit/skill-original/` preserva os 18 arquivos recebidos, conferidos por SHA-256. `OVERRIDES.md` registra orientações posteriores, como usar sempre o logo oficial GOAT.
- Texto, logo e composição são montados pelo renderizador. Magnific não substitui a tipografia nem o fundo fixo dos modelos de agenda.

## Fluxo dos nove cargos

Pesquisa → evolução → **aprovação humana da pauta** → produção → pente fino → **aprovação final do Gestor**.

`tools/editorial_round.py` executa pesquisa, coordenação, desenvolvimento, roteiros e revisão. Os três designers usam `tools/designer_openrouter.py`. Cada cargo recebe suas instruções originais e os aprendizados ativos. Os agentes não podem marcar uma peça como aprovada ou publicá-la em redes sociais.

A entrega visual exige foto com origem rastreada, conferência da foto, renderização, revisão da imagem final e da legenda com crédito. Todas as páginas precisam passar antes do envio dos mesmos bytes ao painel. Uma falha de provedor, data vencida, fonte ausente ou revisão negativa mantém uma pendência explícita.

## Execução automática

O workflow **Processar pedidos da Repartição** executa somente em `main`, com autenticação OIDC do GitHub. `config/runtime.json` controla a rodada dos agentes; `enabled: false` pausa essa rodada, mantendo a fila legada de pedidos.

Cada execução mantém plantão de aproximadamente 50 minutos, consulta a fila a cada 20 segundos e inicia a rodada editorial em intervalos de 30 minutos. Ao terminar, solicita o próximo plantão. O cron de dez minutos serve como reserva; a disponibilidade dos runners pode atrasar o início.

A configuração atual limita a produção a três cards por rodada. Magnific tem limites de geração por execução e por dia; seu diário persistido permite retomar tarefas conhecidas sem gerar outra vez. Respostas de limite do OpenRouter respeitam os tempos de espera informados pelo serviço. Não há fallback pago, recarga automática implementada ou troca automática para Gemini.

Antes da rodada, o executor consulta a cota gratuita por `GET /api/v1/key`, sem inferência. A espera é salva em `.goat-state/openrouter.json` e restaurada no próximo plantão. Quando a cota diária chega a zero, aguarda a renovação do dia UTC; outros limites respeitam `Retry-After` e `X-RateLimit-Reset`. Os nove cargos ficam em `aguardando`, com horário em Brasília. Pedidos novos permanecem pendentes e uma rodada interrompida não é marcada como concluída. O executor volta a conferir a disponibilidade automaticamente, enquanto mantém a fila de arquivos e pedidos em funcionamento.

O painel distingue atividade recente, espera e ausência de atualização pelos registros reais. Estar na fila não significa que uma arte já tenha sido aprovada.

## Fotos e arquivos

- Fotos oficiais aprovadas ficam em `fotos/`, com origem, crédito, dimensões e hash.
- Fotos privadas da equipe ficam cifradas no repositório; a cópia decifrada é temporária e ignorada pelo Git.
- A mesma fotografia não pode ocupar dois slots da mesma peça nem ser reutilizada indevidamente no mesmo dia.
- Nunca remover marcas d'água nem redesenhar atletas. O preset `GOAT_SPORTS_EDITORIAL` aplica apenas ajustes globais e enquadramento.
- Artes enviadas e seus dados de origem ficam em `arts/`. O estado temporário do renderizador fica fora do histórico do Git.

## Verificação e operação

**GOAT consolidated release verification** é a conferência de liberação. Ela verifica os arquivos originais, quatro composições, autenticação Magnific e planejamento/revisões reais do OpenRouter. Em `main`, lê o contexto privado e executa uma rodada dos nove cargos em memória, sem gravar no banco. O artifact público contém somente amostras controladas, contagens, hashes e diagnósticos sanitizados.

Quando a alteração é apenas editorial, **GOAT authenticated editorial verification** confere essa etapa em `main` sem repetir chamadas visuais já verificadas. A verificação completa permanece disponível por execução manual; uma liberação combina a evidência visual válida com a conferência editorial correspondente.

As verificações editoriais agora são manuais, para não consumir cota gratuita a cada alteração. O artifact `goat-provider-status` do plantão registra apenas contadores gratuitos e a eventual espera; não contém chaves, saldos, identidade da conta, prompts ou conteúdo privado. Uma cota disponível não comprova disponibilidade de inferência do provedor.

Testes antigos de Gemini e rotas alternativas foram desativados e mantidos no histórico. Uma resposta simulada não comprova funcionamento dos provedores. Uma aprovação técnica de amostra não substitui a aprovação editorial humana.

Para renderizar uma peça localmente, use as dependências do workflow e um navegador Chrome/Chromium disponível:

```bash
python3 kit/render.py spec.json saida.png
```

O backend `rg-jobs`, sua versão anterior e o procedimento de reversão estão preservados no repositório privado do painel. Nenhum segredo deve ser incluído neste repositório, nos artifacts ou nos logs.
