# Changelog

As mudanças de cada release do Karaokê, da mais nova para a mais antiga. As versões seguem o formato `ANO.MAJOR.MINOR`, e cada release tem um branch `release/<versão>` e uma tag `v<versão>`.

## [2026.1.10] - 2026-10-18

### Mudanças

- **Remover, no acervo, apaga de vez:** a pasta da música sai do disco, e a confirmação diz quanto libera ("Remover e liberar 55 MB (não dá para desfazer)"). O histórico fica; adicionada de novo, a música é preparada do zero. Uma música tocando numa sala ou sendo preparada não é removida, e o app diz por quê.
- Saíram o "Mostrar removidas", o "Desfazer remoção" e o "Apagar de vez" separado, e com eles `GET /api/library?removed=true`, `POST /api/songs/{video_id}/restore` e `POST /api/songs/{video_id}/purge`. `DELETE /api/songs/{video_id}` devolve os bytes liberados.
- **Removidas antes desta versão:** continuam ocupando o disco até o host apagá-las, de uma vez, no Painel → Disco → **Apagar de vez**.

## [2026.1.9] - 2026-10-18

### Novidades

- **Progresso fiel ao tempo, com o tempo que falta:** cada música em preparação ganha uma barra que anda junto com o trabalho de verdade, nunca volta para trás e diz a etapa, a porcentagem e quanto falta ("falta ~2 min", "quase pronta"). A separação e o alinhamento contam por dentro, e o tempo que falta aprende o ritmo deste PC com as últimas músicas preparadas. A TV que espera a próxima música mostra a barra grande.
- **Apagar de vez, para liberar o disco:** no acervo, com "Mostrar removidas", cada música removida ganha **Apagar de vez**, que diz quanto libera (cerca de 50 a 60 MB por música) e pede confirmação. O histórico fica; adicionada de novo, a música é preparada do zero. Uma música numa fila ou sendo preparada nunca é apagada.
- **Adicionar de novo tenta outra vez:** adicionar uma música que não deu para preparar retoma a preparação do ponto em que parou. Se você já tinha essa música na fila da sala, ela continua no mesmo lugar, sem uma repetida no fim.
- **Cards na lista de adicionar:** cada música da busca e do acervo é um card próprio, e onde a lista é estreita (o celular, o menu da TV) **Ouvir** e **Adicionar** ficam embaixo, para o nome e o artista usarem a largura toda.

### Correções

- **Falha passageira no YouTube ou no LRCLIB:** uma música que falha nos metadados, na letra ou no download tenta de novo sozinha, até 3 vezes, da etapa em que parou. O LRCLIB fora do ar é esperado por cerca de um minuto (antes, uns 7 s); se continuar fora, a música diz isso com uma mensagem clara.
- **Aviso da música que não deu para preparar:** quando as tentativas acabam, a TV mostra no alto "Não deu para preparar …", sem cobrir a letra. Na TV do admin, com **Tentar de novo**; nas outras, dizendo que o admin pode tentar de novo no Painel ou que dá para adicionar a música de novo. No celular, a música que falhou diz "Adicione de novo para tentar outra vez".

## [2026.1.8] - 2026-10-13

### Documentação

- A arquitetura registra a decisão sobre o acesso de fora de casa: Cloudflare Tunnel nomeado, com domínio próprio. A questão ainda aparecia como em aberto, embora a fase 2 já esteja concluída assim.

## [2026.1.7] - 2026-10-12

### Correções

- **Letra fora de sincronia no início:** quando o LRC põe uma linha num trecho em que ninguém canta (em Battle Symphony, a primeira linha a 2 s, numa introdução só instrumental), o alinhamento confere cada linha contra a voz isolada e leva essa linha para onde o canto começa, antes da linha seguinte. No acervo, isso corrige a primeira linha de Battle Symphony (agora a 27,8 s) e a do Numb em 4K (agora a 22,85 s); nenhuma linha das outras 23 músicas muda. Para as músicas já processadas, reprocesse a etapa de alinhamento.
- **Música reprocessada não chegava à TV:** o navegador guardava o áudio e a letra por um dia no mesmo endereço, e a TV continuava com a cópia antiga depois de um reprocessamento. Agora os endereços levam a versão da música, e a TV busca os arquivos novos assim que a música fica pronta de novo.

## [2026.1.6] - 2026-10-12

### Novidades

- **Qualquer pessoa cria uma sala:** o botão **Criar sala** aparece sempre na lista, mesmo sem nenhuma sala aberta. Quem ainda não está em nenhuma sala informa também um apelido e vira o dono da sala.
- **Criar a sala já abre a TV:** o toque em **Criar sala** liga o som e abre a TV da sala nova na mesma página, pronta para tocar. O celular entra pelo QR ou por **Entrar na sala**.
- **Abrir como TV sem a tela de Iniciar:** o toque no botão já liga o som, e a TV abre na mesma página, sem recarregar. Só quem abre `/tv/<código>` direto, ou recarrega a página, toca uma vez em **Toque para começar**.
- **Quem abre a TV:** quem sabe a senha da sala (digitada numa janelinha ao tocar em **Abrir como TV**), o dono da sala, sem digitar a senha, e o admin. Numa sala sem senha, qualquer pessoa.

### Mudanças

- **O PIN da TV (`TV_PIN`) saiu:** a TV de uma sala abre pela senha dela, pelo dono ou pelo admin. A linha `TV_PIN` do `.env` passa a ser ignorada, e TVs abertas com esse PIN precisam ser abertas de novo.
- **Limite de criação de salas:** fora o admin, cada endereço cria no máximo 10 salas por hora, e com 20 salas abertas só o admin cria outra.

## [2026.1.5] - 2026-10-12

### Novidades

- **Várias salas ao mesmo tempo**, cada uma com a sua fila e a sua TV; o acervo continua um só.
  - O endereço principal (`/`) abre a **lista de salas**, com nome, quem criou, 🔒 nas que têm senha e quanto falta para expirar. Dela se entra numa sala (**Entrar na sala**), se abre a TV (**Abrir como TV**), se cria e se exclui uma sala.
  - **Criar sala:** o admin ou qualquer convidado de uma sala aberta, com um nome e uma senha opcional. Sem senha, a sala é pública. Quem cria é o dono da sala.
  - **Senha da sala:** pedida ao entrar como convidado e ao abrir a TV. As tentativas erradas contam no mesmo bloqueio dos PINs.
  - **A TV de cada sala** fica em `/tv/<código>`. Abrem a TV: a senha da sala, o dono (só com um toque em **Iniciar**), o PIN da TV ou o do admin. Numa sala sem senha, só o dono e o admin abrem a TV.
  - **O dono da sala** muda o tom, remove e reordena qualquer música dela, e controla o player (tocar, pausar, pular, voz guia e atraso) pelo celular.
  - **Excluir sala:** o dono exclui a dele; o admin, qualquer uma.
  - **Expiração:** a sala expira 24 h depois de criada. As telas mostram quanto falta, em amarelo na última meia hora. Excluída ou expirada, a música que estiver tocando vai até o fim e as telas levam de volta à lista.
  - **Ver salas** em todas as telas de uma sala, para trocar de sala.
- **`/host` gerencia todas as salas:** criar, excluir, escolher uma e controlar a fila e o player dela. Na lista, **Gerenciar** abre a sala direto no `/host`.

### Mudanças

- O endereço principal não redireciona mais para `/tv`: abre a lista de salas.
- A sala que estava aberta na atualização virou uma sala do admin, sem senha, que expira 24 h depois.
- O banco ganha a migração `0002` (dono, senha e expiração das salas; um convidado por sala para o mesmo celular).

### Correções

- A API não registra mais um erro quando fecha as conexões de uma sala excluída ou expirada.

## [2026.1.4] - 2026-10-09

### Novidades

- **Menu lateral na TV:** um botão "☰ Menu" na borda direita. Aberto, ele fica ao lado da TV, que encolhe sem esconder a letra, o QR e os controles; no celular, cobre a tela.
  - **Sala**, com as sub-abas **Fila** e **Adicionar Música**, liberada pelo PIN da TV.
  - **Gerenciar Acervo** e **Painel** pedem o PIN do admin na própria aba; **Sair do admin** volta a bloqueá-las e mantém a TV na sala.
- **A TV adiciona músicas** e é dona delas: remove e muda o tom das que adicionou, que aparecem na fila como adicionadas por "TV".
- **Menus coerentes:** o `/host` e o celular do convidado usam a mesma aba Sala, com Fila e Adicionar Música. "Acervo" passou a se chamar "Gerenciar Acervo" no admin.
- Adicionar uma música não pula mais para a fila: aparece só a confirmação.

### Correções

- A música que está tocando fica fixa no topo da fila: sem botões de ordem, nada sobe acima dela, e a API recusa movê-la.

## [2026.1.3] - 2026-10-07

### Correções

- O celular que abre a TV com o PIN da TV e também entra como convidado pelo QR (um iPhone espelhado na TV, por exemplo) agora consegue adicionar músicas. Antes, a API só via o papel de TV e recusava com "Só o host pode fazer isso.". Esse celular passa a ter os direitos da TV e os de convidado ao mesmo tempo, e continua sem poder mexer nas músicas dos outros.

## [2026.1.2] - 2026-10-02

### Mudanças

- A tela de PIN da TV agora diz "Digite o PIN para Iniciar".

## [2026.1.1] - 2026-10-02

### Novidades

- **PIN próprio para a TV** (`TV_PIN` no `.env`): ele só toca a fila. Dá para tocar, pausar, pular e mudar o tom da música que está tocando; nada do `/host` (salas, acervo, reprocessar, remover, reordenar). O PIN do admin continua abrindo a TV. As tentativas erradas nos dois PINs contam juntas para o bloqueio.
- A tela de PIN da TV agora se chama **Open Karaoke**, e o botão **Iniciar** já entra na sala com o som ligado, sem um segundo toque.
- O endereço principal abre a TV: `/` redireciona para `/tv`, e endereços desconhecidos também vão para lá.
- O `/tv` tem um link **Acessar como admin**, que leva ao `/host`.
- Este `CHANGELOG.md`.

### Correções

- O `/host` só abre com o PIN do admin; o cookie da TV não abre essa tela.

### Ao atualizar

- Defina `TV_PIN` no `.env`, diferente do `HOST_PIN`, e recrie a API (`docker compose up -d --force-recreate api`). Sem ele, só o PIN do admin abre a TV.

## [2026.1.0] - 2026-10-02

Primeira release do Karaokê: um app de karaokê caseiro que roda num PC com GPU. Ele baixa a música do YouTube, separa a voz do instrumental, alinha a letra palavra por palavra e toca na TV, com mudança de tom ao vivo. Os convidados entram pelo QR Code e escolhem as músicas pelo celular.

A arquitetura completa está em [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### Processamento das músicas (worker com GPU)

- Download com yt-dlp, separação de voz com BS-RoFormer, letra do LRCLIB (com transcrição pelo Whisper quando não há letra) e alinhamento palavra por palavra.
- Detecção do tom original e versões de reprodução em Opus.
- Cada vídeo é processado uma única vez e guardado numa pasta própria; nada é reprocessado sem pedido do host.
- Vídeos com mais de 10 minutos são recusados.

### TV (`/tv`)

- Letra rolando como um teleprompter, acesa palavra por palavra, com a imagem do vídeo ao fundo e borda opcional.
- Mudança de tom em tempo real (−6 a +6 semitons) com Rubber Band R3 no navegador. No tom original, o áudio não passa pelo ajuste, o que evita chiado em celulares.
- Voz guia e atraso da letra ajustáveis; o próximo cantor aparece num canto e numa tela entre músicas com contagem de 5 s.
- Layout próprio para celular, em pé e deitado.
- O áudio volta sozinho depois de trocar de aba no iPhone.

### Celulares e host

- Entrada pelo QR Code, como convidado ou administrador; busca, prévia e fila com permissões por dono da música.
- Tela do host (`/host`): sala, fila, acervo, troca de letra, reprocessamento, remoção e restauração de músicas, e painel de jobs e de disco.

### Infraestrutura

- Docker Compose com Caddy, API (FastAPI + SQLite), worker com GPU e, opcionalmente, Cloudflare Tunnel para acesso fora de casa.
- Login do host por PIN, com bloqueio após tentativas erradas.

[2026.1.4]: https://github.com/raphmello/karaoke-app/releases/tag/v2026.1.4
[2026.1.3]: https://github.com/raphmello/karaoke-app/releases/tag/v2026.1.3
[2026.1.2]: https://github.com/raphmello/karaoke-app/releases/tag/v2026.1.2
[2026.1.1]: https://github.com/raphmello/karaoke-app/releases/tag/v2026.1.1
[2026.1.0]: https://github.com/raphmello/karaoke-app/releases/tag/v2026.1.0
