# Changelog

As mudanças de cada release do Karaokê, da mais nova para a mais antiga. As versões seguem o formato `ANO.MAJOR.MINOR`, e cada release tem um branch `release/<versão>` e uma tag `v<versão>`.

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

[2026.1.0]: https://github.com/raphmello/karaoke-app/releases/tag/v2026.1.0
