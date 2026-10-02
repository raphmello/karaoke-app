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

## Uma noite de karaokê (fase 4)

1. No `.env`, defina `HOST_PIN` e `PUBLIC_BASE_URL=http://<IP do PC>:8080` (o endereço que os celulares usam).
2. Em `http://<IP do PC>:8080/host`, entre com o PIN e abra a sala da noite.
3. No PC ligado à TV, abra `http://<IP do PC>:8080/tv`, entre com o PIN e toque em **Iniciar**. A TV mostra o QR Code.
4. Cada convidado lê o QR, escolhe um apelido, busca e adiciona músicas, já no tom em que quer começar. A fila toca em ordem, sozinha.

Na TV, os botões **−½ tom**, **+½ tom** e **Voltar ao tom original** mudam o tom ao vivo (as setas ↑ e ↓ também; espaço pausa). O dono de cada música muda o tom dela pelo celular, e só ele (ou o host) pode removê-la. Quando a letra não é encontrada, o celular do dono pergunta se ela deve ser transcrita; um "não" tira a música da fila sem baixar nada. No `/host`, o host reordena a fila, remove qualquer música e toca, pausa ou pula.

Para mexer no frontend sem reconstruir a imagem, com a pilha no ar:

```bash
cd web && pnpm install && pnpm dev
```

O Vite abre em `http://localhost:5173/tv` e repassa `/api`, `/media` e `/ws` para o Caddy.

## API à mão

Um roteiro mínimo com `curl`:

```bash
curl -c host.txt -H 'content-type: application/json' -d '{"pin":"<seu PIN>"}' http://localhost:8080/api/host/login
curl -b host.txt -H 'content-type: application/json' -d '{"name":"Sexta"}' http://localhost:8080/api/rooms
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
