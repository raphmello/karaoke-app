# Changelog

As mudanças de cada release do Karaokê, da mais nova para a mais antiga. As versões seguem o formato `ANO.MAJOR.MINOR`, e cada release tem um branch `release/<versão>` e uma tag `v<versão>`.

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
