# karaoke-app

Karaokê local: busca no YouTube, voz removida, tom ajustável e letra destacada palavra por palavra. A arquitetura está em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Pré-requisitos

Docker Desktop com o motor WSL 2 e uma GPU NVIDIA. Para conferir que a GPU chega aos containers:

```bash
docker run --rm --gpus all ubuntu nvidia-smi
```

## Subir o app (fase 2)

Crie o `.env` a partir do exemplo e defina o PIN do host:

```bash
cp .env.example .env
```

```bash
docker compose up -d --build
```

Sobem três serviços: `caddy` (porta 8080, a única exposta, com o frontend compilado na imagem), `api` e `worker` (com a GPU). O banco SQLite e as músicas ficam no volume `karaoke-data`.

## Uma noite de karaokê

1. No `.env`, defina `HOST_PIN` e `PUBLIC_BASE_URL=http://<IP do PC>:8080` (o endereço que os celulares usam).
2. Em `http://<IP do PC>:8080/` fica a lista das salas abertas. Qualquer pessoa cria uma em **Criar sala**: um nome, se quiser uma senha (sem senha, a sala é pública) e o apelido, e já entra nela como dono. O admin (**Acessar como admin**, com o PIN do host) também cria salas, sem ser dono de nenhuma.
3. No aparelho ligado à TV, o dono da sala ou o admin abre a lista e toca em **Abrir como TV**: a TV já abre pronta, com o som ligado, e mostra o QR Code. Só eles veem esse botão; a senha da sala serve só para entrar como convidado. Quem abre o endereço `/tv/<código>` direto, ou recarrega a página da TV, toca uma vez em **Toque para começar**, porque o navegador não toca som sem um toque.
4. Cada convidado lê o QR (ou entra pela lista, com **Entrar na sala**), escolhe um apelido, digita a senha se a sala tiver uma, busca e adiciona músicas, já no tom em que quer começar. Antes de adicionar, **▶ Ouvir** toca uma prévia (do acervo, direto do PC; da busca, repassada do YouTube pela API). A fila toca em ordem, sozinha.

Várias salas podem ficar abertas ao mesmo tempo, cada uma com a sua fila e a sua TV; o acervo é um só. Quem cria uma sala vira o dono dela: o dono muda o tom, remove e reordena qualquer música da sala, controla o player pelo celular e pode **Excluir sala**. O admin exclui qualquer sala. Uma sala expira 24 h depois de criada; a tela mostra quanto falta, e o aviso fica amarelo na última meia hora. Quando a sala é excluída ou expira, a música que estiver tocando vai até o fim e as telas levam de volta à lista (**Ver salas**). Uma senha esquecida não se recupera: o admin exclui a sala, ou ela expira.

Na TV, os botões **−½ tom**, **+½ tom** e **Voltar ao tom original** mudam o tom ao vivo (as setas ↑ e ↓ também; espaço pausa). O dono de cada música muda o tom dela pelo celular, e só ele (ou o dono da sala, ou o host) pode removê-la. Quando a letra não é encontrada, o celular do dono pergunta se ela deve ser transcrita; um "não" tira a música da fila sem baixar nada. Entre uma música e outra, a TV mostra o próximo cantor, a música, o tom e o QR, e a próxima começa depois de 5 s.

O `/host` tem três abas:

- **Salas:** criar e excluir salas e, na sala escolhida, **Abrir como TV**, tocar, pausar e pular (entre músicas, pular passa a próxima), voz guia e atraso da TV, e as sub-abas **Fila** (reordenar, remover e tentar de novo uma música que falhou) e **Adicionar Música**. Na lista, **Gerenciar** abre a sala direto aqui. O celular do convidado tem a mesma Sala (o dono da sala também tem o player), e a TV, as mesmas abas no menu ☰ à direita, com **Ver salas** para trocar de sala.
- **Gerenciar Acervo:** trocar a letra (colando LRC ou texto; só o alinhamento roda de novo), reprocessar etapas, remover e desfazer a remoção, e ver o histórico de cada música.
- **Painel:** os jobs, com "Tentar de novo" para os que falharam, e o disco, com aviso quando o espaço estiver acabando.

Para mexer no frontend sem reconstruir a imagem, com a pilha no ar:

```bash
cd web && pnpm install && pnpm dev
```

O Vite abre em `http://localhost:5173/` (a lista de salas) e repassa `/api`, `/media` e `/ws` para o Caddy.

## Acesso de fora de casa (Cloudflare Tunnel)

Com o túnel, o app fica em `https://karaoke.<seu-domínio>` sem abrir portas no roteador; a rede de casa continua funcionando.

1. No painel da Cloudflare: **Zero Trust > Networks > Tunnels > Create a tunnel > Cloudflared**. Dê um nome e copie o token.
2. Em **Public Hostname**, adicione `karaoke.<seu-domínio>` com o serviço `HTTP` e a URL `caddy:8080`.
3. No `.env`: `CLOUDFLARE_TUNNEL_TOKEN=<token>` e `PUBLIC_BASE_URL=https://karaoke.<seu-domínio>`. O QR da TV passa a levar sempre a esse endereço.
4. Suba com o túnel:

```bash
docker compose --profile remote up -d
```

Use um PIN de host forte: 5 tentativas erradas do mesmo endereço bloqueiam o login dele por 10 minutos (vale também para os PINs da TV e as senhas das salas). Uma sala sem senha fica aberta a quem tiver o endereço; com o túnel, crie as salas com senha. Como qualquer um com o endereço cria salas, cada endereço cria no máximo 3 por hora, e com 20 salas abertas só o admin cria outra; o admin exclui as que não reconhecer. Áudios e letras (`/media`) só abrem para o host e para convidados de uma sala aberta.

Para o PC ficar sempre pronto: no Windows, desligue a suspensão no plano de energia e deixe o Docker Desktop iniciar com o Windows; os containers voltam sozinhos (`restart: unless-stopped`).

## API à mão

Um roteiro mínimo com `curl`:

```bash
curl -c host.txt -H 'content-type: application/json' -d '{"pin":"<seu PIN>"}' http://localhost:8080/api/host/login
curl -b host.txt -H 'content-type: application/json' -d '{"name":"Sexta"}' http://localhost:8080/api/rooms   # com senha: {"name":"Sexta","password":"..."}
curl http://localhost:8080/api/rooms
curl -c ana.txt -H 'content-type: application/json' -d '{"nickname":"Ana"}' http://localhost:8080/api/rooms/<código>/join
curl -b ana.txt -H 'content-type: application/json' -d '{"video_id":"<ID ou URL>"}' http://localhost:8080/api/rooms/<código>/queue
curl -b ana.txt http://localhost:8080/api/rooms/<código>/queue
```

O worker pega o job e processa a música; o progresso aparece em `docker compose logs -f worker`. Reiniciar a API desloga o host (o PIN entra de novo).

Se o banco se perder, `rebuild-index` recria a tabela de músicas a partir das pastas do volume:

```bash
docker compose exec worker karaoke rebuild-index
```

## Processar uma música à mão (fase 1)

```bash
docker compose run --rm worker process <ID ou URL do vídeo>
```

O resultado fica no volume `karaoke-data`, em `media/<video_id>/`, com o layout descrito na arquitetura. Rodar de novo o mesmo vídeo não refaz nada, e uma execução interrompida retoma da etapa em que parou.

Se a letra não for encontrada, o comando para antes de baixar o áudio e sai com código 2. Para transcrever a voz com o Whisper:

```bash
docker compose run --rm worker process <vídeo> --transcribe
```

## Testes

```bash
docker compose run --rm --no-deps --entrypoint uv worker run --frozen --group dev pytest
```

```bash
cd web && pnpm test
```
