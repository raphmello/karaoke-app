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

Sobem três serviços: `caddy` (porta 8080, a única exposta), `api` e `worker` (com a GPU). O banco SQLite e as músicas ficam no volume `karaoke-data`. A interface chega na fase 3; por enquanto o app é só a API, em `http://localhost:8080/api/...`.

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
