# Spike da fase 0

Mede, no PC de destino (RTX 4060 Ti, 8 GB), o que a [arquitetura](../../docs/ARCHITECTURE.md) precisa decidir antes de qualquer código do app:

- separação de voz: BS-RoFormer, MelBand RoFormer e `htdemucs_ft`, em qualidade, tempo e VRAM;
- alinhamento da letra com stable-ts: Whisper turbo e large-v3 (faster-whisper) sobre a voz isolada, mais o mix original como controle;
- Rubber Band R3 em ±4 semitons;
- tempo total por música.

Seis músicas (três em português e três em inglês) estão em [`songs.json`](songs.json). Tudo que é baixado ou gerado fica em `work/`, que não vai para o git porque contém áudio e letras com direitos autorais.

## Pré-requisitos

Docker Desktop com o motor WSL 2 e acesso à GPU. Para conferir:

```bash
docker run --rm --gpus all ubuntu nvidia-smi
```

## Como rodar

Todos os comandos rodam a partir de `spikes/phase0`.

```bash
docker compose build
docker compose run --rm spike python env_info.py     # 0. ambiente
docker compose run --rm spike python fetch.py        # 1. busca no YouTube, letra no LRCLIB, download
docker compose run --rm spike python speed.py        # 2a. separação: velocidade por sobreposição e precisão
docker compose run --rm spike python musdb_eval.py   # 2b. separação: SDR no MUSDB18 (stems verdadeiros)
docker compose run --rm spike python separate.py     # 2c. separação: tempo e VRAM nas 6 músicas
docker compose run --rm spike python align.py        # 3. alinhamento: tempo, VRAM e erro contra o LRC
docker compose run --rm spike python pitch.py        # 4. Rubber Band ±4 semitons
docker compose run --rm spike python pitch_options.py  # 4b. tom: R3 e R2 com os stems em paralelo
docker compose run --rm spike python sync.py         # 6. sincronização: LRC como esqueleto + palavras por linha
docker compose run --rm spike python report.py       # 5. tabelas e página de evidências
python scripts/serve.py                              # página em http://localhost:8765/evidence/index.html
```

Os modelos ficam no volume Docker `spike-models` e são baixados uma vez.

## Tom em tempo real (spike 0c)

A página `realtime/index.html` muda o tom ao vivo no navegador com o [rubberband-web](https://github.com/delude88/rubberband-web). Ela usa os stems da etapa 2c, o render R3 da etapa 4 como comparação e o tom original detectado pelo essentia. Para prepará-la, rode a partir de `spikes/phase0`:

```bash
docker run --rm --entrypoint python -v "$PWD:/spike" karaoke-worker /spike/scripts/keys.py
npm pack rubberband-web@0.2.1 && tar xzf rubberband-web-0.2.1.tgz && mkdir -p work/vendor && cp package/public/rubberband-processor.js work/vendor/ && rm -r package rubberband-web-0.2.1.tgz
python scripts/serve.py
```

Depois abra `http://localhost:8765/realtime/index.html`. O primeiro comando usa a imagem do worker da fase 1, que tem o essentia. O arquivo do rubberband-web fica em `work/` e não vai para o git, porque é código GPL de terceiros.

## Saídas

- `work/results/*.json`: medições brutas de cada etapa.
- `work/results/tables.md`: tabelas usadas no [RESULTS.md](RESULTS.md).
- `work/evidence/index.html`: página local para ouvir e comparar os modelos, com prévia do karaokê palavra por palavra.
- `realtime/index.html`: tom em tempo real, com medição de CPU e atraso.

As duas páginas precisam do `scripts/serve.py`, que aceita Range; o servidor padrão do Python não deixa o navegador pular dentro do áudio.
