# karaoke-app

Karaokê local: busca no YouTube, voz removida, tom ajustável e letra destacada palavra por palavra. A arquitetura está em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Pré-requisitos

Docker Desktop com o motor WSL 2 e uma GPU NVIDIA. Para conferir que a GPU chega aos containers:

```bash
docker run --rm --gpus all ubuntu nvidia-smi
```

## Processar uma música (fase 1)

```bash
docker compose build
docker compose run --rm worker process <ID ou URL do vídeo>
```

O resultado fica no volume `karaoke-data`, em `media/<video_id>/`, com o layout descrito na arquitetura. Rodar de novo o mesmo vídeo não refaz nada, e uma execução interrompida retoma da etapa em que parou.

Se a letra não for encontrada, o comando para antes de baixar o áudio e sai com código 2. Para transcrever a voz com o Whisper:

```bash
docker compose run --rm worker process <vídeo> --transcribe
```

## Testes

```bash
docker compose run --rm --entrypoint uv worker run --frozen --group dev pytest
```
