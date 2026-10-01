# Spike da fase 0: resultados e conclusões

Medido em 1º de outubro de 2026 no PC de destino: RTX 4060 Ti (8 GB), i5-12400F, 32 GB de RAM, Docker Desktop com WSL 2. Como reproduzir: [README](README.md).

**Conclusão:** o pipeline da arquitetura é viável neste PC. Uma música fica pronta em cerca de 1,5 minuto, um terço da sua própria duração, então a fila sempre anda à frente de quem está cantando. A audição confirmou a separação (BS-RoFormer) e a mudança de tom (R3). A sincronização da letra, porém, foi reprovada de ouvido e precisa de outra abordagem (veja [Audição](#audição)).

## Resumo

| Pergunta | Resultado | Recomendação |
| --- | --- | --- |
| Buscar, baixar e achar a letra funciona? | 6 de 6. yt-dlp com Deno baixa em ~2,5 s; o LRCLIB (`/api/get`, por artista, música e duração) achou letra sincronizada para todas em ~0,3 s | Manter como está |
| Qual separação de voz? | BS-RoFormer tem a melhor qualidade (16,2 dB no instrumental, MUSDB18). Com sobreposição 2 e autocast fica 3,3× mais rápido **sem perda mensurável** (16,20 contra 16,23 dB): ~66 s por música, 2,5 GB de VRAM. MelBand perde 0,6 dB e é 2× mais rápido. htdemucs_ft perde 3,3 dB e não é mais rápido que o MelBand | **BS-RoFormer, sobreposição 2, autocast**, se a sua audição confirmar. MelBand como alternativa. Descartar htdemucs_ft |
| Qual Whisper para alinhar a letra? | turbo sobre a voz isolada: 81% das linhas a até 0,5 s do LRC, 91% a até 1 s, ~7 s por música mais ~8 s para carregar, 3,9 GB de VRAM. large-v3 (faster-whisper) acerta menos (65%) e falhou por inteiro em uma música. O VAD piorou | **Whisper turbo, sem VAD** |
| Alinhar na voz isolada compensa? | Sim: 81% contra 64% no mix original. No mix, "Bohemian Rhapsody" desanda por inteiro | Manter (decisão 9 da arquitetura) |
| Os tempos do LRC servem direto? | Não. O clipe de "Ai Se Eu Te Pego" está 5,5 s deslocado da letra, e o LRC de "Evidências" tem deriva de 1,2% (foi sincronizado numa cópia mais lenta) | Manter o alinhamento no áudio real |
| Rubber Band mantém a letra sincronizada? | Sim: a duração não muda (0 ms de diferença em 24 renderizações) | Manter |
| Quanto custa mudar o tom? | R3 (`--fine`) na CPU: 34 a 261 s por tom (dois stems), ~70 a 120 s numa música de 5 minutos. R2 com os stems em paralelo: 12 s | Ver proposta 4 abaixo |
| Cabe tudo em 8 GB de VRAM? | Separação 2,5 GB + Whisper 3,9 GB + Windows 1,3 GB = 7,7 GB | Um modelo por vez, como a arquitetura já prevê |
| Tempo total por música | 92 s em média (33% da duração) com BS-RoFormer, medido; ~58 s (20%) com MelBand, estimado trocando só o tempo de separação | — |

O critério de pronto da fase 0 ("modelos escolhidos e tempo total por música medido") está atendido, com uma pendência: a audição da separação e da mudança de tom.

## Mudanças na arquitetura

As quatro propostas abaixo foram aprovadas e aplicadas ao `docs/ARCHITECTURE.md` em 1º de outubro de 2026. Na proposta 4, a escolhida foi tocar primeiro a versão R2 e trocar pela R3. Depois da audição, a proposta 3 foi substituída por uma abordagem mais forte, também aprovada e aplicada: o LRC como esqueleto de todas as linhas e o stable-ts por linha (veja [Sincronização](#sincronização-lrc-como-esqueleto-spike-0b)). Junto com ela entrou a exibição com antecedência de 1 s e a contagem regressiva.

1. **Fixar a configuração da separação.** Na tabela de stack, trocar "BS-RoFormer; Demucs `htdemucs_ft` como alternativa" por "BS-RoFormer com sobreposição 2 e autocast; MelBand RoFormer como alternativa". A configuração padrão do modelo levaria 233 s numa música de 5 minutos, contra 70 s.
2. **Fixar o modelo de alinhamento.** Na tabela de stack: "stable-ts com Whisper turbo, sem VAD". faster-whisper sai do stack.
3. **Usar o LRC para pegar linhas mal alinhadas.** Cerca de 6% das linhas (21 de 329) ficaram a mais de 2 s do LRC; a maior parte é o final lento de "Bohemian Rhapsody" e linhas curtas de 1 ou 2 palavras. Proposta para a etapa 6 do pipeline: quando houver letra sincronizada, ajustar deslocamento e deriva entre o LRC e o alinhamento e, nas linhas a mais de 2 s da reta, usar o tempo do LRC ajustado e marcar a linha como de baixa confiança. O player já acende essas linhas inteiras.
4. **Mudança de tom no meio da música.** A arquitetura fala em "alguns segundos", mas o R3 leva de 1 a 4 minutos na CPU. O render ao entrar na fila continua escondendo isso; o problema é só a troca de tom ao vivo. Duas saídas:
    - aceitar a espera, com a TV mostrando "preparando tom";
    - gerar primeiro uma versão R2 (~12 s) para tocar logo e trocá-la pela R3 quando ficar pronta. Isso pede um campo de motor em `pitch_renders`.

Também confirmados, sem mudança necessária:
- **Range no servidor de mídia é obrigatório:** sem ele, o navegador não descobre a duração do Opus nem consegue pular. A arquitetura já põe o Caddy servindo `/media` com Range.
- **WSL 2 é obrigatório para a GPU no Docker,** como a arquitetura já prevê. Com o motor Hyper-V, os containers não enxergam a placa.

Achados de implementação para a imagem do worker (não mudam a arquitetura):
- `build-essential` é necessário para compilar `diffq`.
- `audioread` precisa ser instalado à parte; o audio-separator importa mas não declara.
- O GitHub responde HTTP 500 para a configuração do BS-RoFormer; o mesmo arquivo vem do repositório do UVR.
- O PyTorch é a camada mais pesada da imagem e deve ficar numa camada própria.

## Audição

Notas do dono do projeto na página de evidências, em 1º de outubro de 2026.

| O que foi ouvido | Resultado |
| --- | --- |
| Instrumental, BS-RoFormer rápido | 5 ("limpo") nas 6 músicas |
| Instrumental, MelBand RoFormer rápido | 3 a 4, média 3,5 |
| Instrumental, htdemucs_ft | 3 nas 5 músicas avaliadas |
| Tom −4 e +4 (R3) | "natural" nas 12 avaliações |
| Alinhamento, turbo · voz isolada | "bom" em 3 músicas, "ruim" em 3 ("Tempo Perdido", "Ai Se Eu Te Pego", "Bohemian Rhapsody") |
| Alinhamento, demais variantes | também perto de metade "ruim"; "Tempo Perdido" e "Ai Se Eu Te Pego" foram "ruim" em todas |

A audição confirma o BS-RoFormer e o R3. Ela **reprova a sincronização da letra**: na percepção de quem canta, os erros confundem. A métrica deste spike compara só o início de cada linha com o LRC e não capta o que o ouvido percebe palavra a palavra.

Também foi testada a busca de letra sincronizada palavra por palavra feita por pessoas ("enhanced LRC", via Musixmatch pelo `syncedlyrics`), que serviria de gabarito: nenhuma das 6 músicas tinha.

## Sincronização: LRC como esqueleto (spike 0b)

A queixa principal na audição foi "linhas fora do lugar". O alinhamento da música inteira de uma vez deixa ~6% das linhas a segundos de onde são cantadas: um erro numa parte arrasta as seguintes. O `sync.py` testa outra abordagem:

1. **Linhas:** cada linha começa no tempo do LRC, levado para o relógio do áudio pela reta (deslocamento e deriva) ajustada contra o alinhamento da música inteira. Assim, linha nenhuma pode ficar segundos fora do lugar.
2. **Palavras:** são alinhadas só dentro da janela da própria linha, então um erro não passa para a seguinte. Três variantes:
    - palavras distribuídas pelo tamanho (controle, sem alinhador);
    - stable-ts (Whisper turbo) por linha;
    - alinhador CTC (MMS_FA do torchaudio, wav2vec2 treinado para alinhamento) por linha.
3. **Exibição:** a prévia agora mostra a linha até 1 s antes, assim que a anterior termina. Antes de uma linha que vem depois de 3 s ou mais sem canto, mostra uma contagem regressiva. Linhas de baixa confiança acendem inteiras.

Resultado objetivo:
- O esqueleto do LRC reposiciona 31 linhas que o alinhamento antigo deslocava mais de 1 s; 21 delas estavam a mais de 2 s.
- O CTC é 10× mais rápido que o stable-ts por linha: 1,9 s contra 18,9 s por música.
- Os dois alinhadores de palavras concordam (diferença de até 0,2 s) em 62% a 89% das palavras, então a escolha entre eles fica para a audição.

Os números completos estão em [Medições](#medições).

**Audição** (5 músicas, todas menos "Evidências", já com a exibição nova):

| Variante | bom | aceitável | ruim |
| --- | --- | --- | --- |
| atual (música inteira) | 2 | 1 | 2 |
| LRC + palavras distribuídas | 4 | 1 | 0 |
| **LRC + stable-ts por linha** | **5** | **0** | **0** |
| LRC + CTC por linha | 3 | 2 | 0 |

Escolha: **LRC como esqueleto + stable-ts (Whisper turbo) por linha.**
- Só a exibição nova não resolve: a variante atual, com ela, continuou "ruim" em "Tempo Perdido" e "Bohemian Rhapsody". O que resolve é o esqueleto do LRC.
- O custo é ~19 s a mais de alinhamento por música, o que leva o total de ~92 s para ~111 s (cerca de 39% da duração da música).
- O CTC foi 10× mais rápido, mas ficou "aceitável" em 2 músicas.

## Página de evidências

A página `work/evidence/index.html` toca cada música com os três modelos de separação, a voz isolada, o tom em −4, +4 e +4 em R2, e uma prévia do karaokê palavra por palavra para cada variante de alinhamento. Ao trocar de modelo, o áudio continua do mesmo ponto. As notas ficam no navegador; o botão "Exportar notas" gera um texto para colar na conversa. Para abrir:

```bash
python spikes/phase0/scripts/serve.py
```

e acesse `http://localhost:8765/evidence/index.html`. O servidor do Python sem Range não serve: a página precisa pular dentro do áudio.

## Limitações

- Seis músicas são uma amostra pequena. As tendências foram consistentes, mas casos raros podem não ter aparecido.
- O LRC é uma referência humana, por linha. O erro medido mistura erro do alinhamento e imprecisão do LRC; palavras isoladas só a audição avalia.
- O SDR vem de trechos de 7 s do MUSDB18. Alguns modelos podem ter visto parte desse conjunto no treino, o que infla os números absolutos; a comparação entre configurações do mesmo modelo continua válida.
- O tempo do Rubber Band variou bastante entre músicas ("Bohemian Rhapsody" +4 levou 261 s, contra 120 s em −4). Pode ter havido disputa de CPU com o Windows nesse intervalo.

## Medições

### Ambiente

| Item | Versão |
| --- | --- |
| GPU | NVIDIA GeForce RTX 4060 Ti (8188 MiB), driver 610.88 |
| PyTorch / CUDA / cuDNN | 2.11.0+cu128 / 12.8 / 91900 |
| torchaudio | 2.11.0+cu128 |
| audio-separator | 0.47.0 |
| onnxruntime-gpu | 1.30.0 |
| yt-dlp | 2026.8.19 |
| yt-dlp-ejs | 0.8.0 |
| stable-ts | 2.19.1 |
| openai-whisper | 20250625 |
| faster-whisper | 1.2.1 |
| ctranslate2 | 4.8.2 |
| musdb | 0.4.3 |
| numpy | 2.5.3 |
| ffmpeg | ffmpeg version 7.1.5-0+deb13u1 Copyright (c) 2000-2026 the FFmpeg developers |
| rubberband | 3.3.0 |
| deno | deno 2.9.7 (stable, release, x86_64-unknown-linux-gnu) |

### Busca, letra e download

| Música | Vídeo | Duração | Letra sincronizada | Dif. duração vídeo × letra | Achada por /api/get | Metadados | Busca da letra | Download + WAV |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Chitãozinho & Xororó — Evidências | [Y59pC4FcBxM](https://www.youtube.com/watch?v=Y59pC4FcBxM) | 299 s | 59 linhas | 0.0 s | sim | 1.2 s | 0.55 s | 3.0 s |
| Legião Urbana — Tempo Perdido | [LqmRIG1plVU](https://www.youtube.com/watch?v=LqmRIG1plVU) | 303 s | 37 linhas | 0.9 s | sim | 1.6 s | 0.25 s | 2.4 s |
| Michel Teló — Ai Se Eu Te Pego | [hcm55lU9knw](https://www.youtube.com/watch?v=hcm55lU9knw) | 165 s | 51 linhas | 0.0 s | sim | 1.4 s | 0.25 s | 2.0 s |
| Queen — Bohemian Rhapsody | [xG16sdjLtc0](https://www.youtube.com/watch?v=xG16sdjLtc0) | 354 s | 50 linhas | 0.0 s | sim | 1.1 s | 0.24 s | 3.2 s |
| Journey — Don't Stop Believin' | [1k8craCGpgs](https://www.youtube.com/watch?v=1k8craCGpgs) | 250 s | 39 linhas | 0.0 s | sim | 1.3 s | 0.26 s | 2.4 s |
| Eminem — Lose Yourself | [Wj7lL6eDOqc](https://www.youtube.com/watch?v=Wj7lL6eDOqc) | 321 s | 93 linhas | 0.0 s | sim | 1.6 s | 0.25 s | 2.9 s |

### Separação: velocidade por configuração

Trecho de 60 s de `evidencias`. A última coluna compara o instrumental com o da configuração mais lenta do mesmo modelo (sobreposição 4, float32): quanto maior, mais parecido.

| Modelo | Sobreposição | Precisão | Tempo | Velocidade × tempo real | VRAM do processo | Fidelidade à referência |
| --- | --- | --- | --- | --- | --- | --- |
| BS-RoFormer | 4 | float32 | 43.0 s | 1.4× | 3097 MiB | 131.1 dB |
| BS-RoFormer | 2 | float32 | 22.6 s | 2.7× | 3095 MiB | 42.1 dB |
| BS-RoFormer | 1 | float32 | 13.3 s | 4.5× | 3090 MiB | 35.5 dB |
| BS-RoFormer | 4 | autocast (fp16) | 25.1 s | 2.4× | 2517 MiB | 73.9 dB |
| BS-RoFormer | 2 | autocast (fp16) | 13.4 s | 4.5× | 2506 MiB | 42.1 dB |
| BS-RoFormer | 1 | autocast (fp16) | 8.0 s | 7.5× | 2501 MiB | 35.5 dB |
| BS-RoFormer | 4 | float16 nativo | 23.6 s | 2.5× | 2455 MiB | 72.7 dB |
| BS-RoFormer | 2 | float16 nativo | 12.5 s | 4.8× | 2458 MiB | 42.1 dB |
| BS-RoFormer | 1 | float16 nativo | 7.5 s | 8.0× | 2455 MiB | 35.5 dB |
| MelBand RoFormer | 4 | float32 | 19.1 s | 3.1× | 3780 MiB | 131.4 dB |
| MelBand RoFormer | 2 | float32 | 10.4 s | 5.8× | 3805 MiB | 44.8 dB |
| MelBand RoFormer | 1 | float32 | 6.5 s | 9.2× | 3820 MiB | 33.7 dB |
| MelBand RoFormer | 4 | autocast (fp16) | 11.5 s | 5.2× | 3243 MiB | 75.4 dB |
| MelBand RoFormer | 2 | autocast (fp16) | 6.4 s | 9.4× | 3239 MiB | 44.9 dB |
| MelBand RoFormer | 1 | autocast (fp16) | 4.1 s | 14.5× | 3224 MiB | 33.7 dB |
| MelBand RoFormer | 4 | float16 nativo | 11.1 s | 5.4× | 3186 MiB | 72.1 dB |
| MelBand RoFormer | 2 | float16 nativo | 6.2 s | 9.7× | 3201 MiB | 44.8 dB |
| MelBand RoFormer | 1 | float16 nativo | 3.9 s | 15.3× | 3199 MiB | 33.7 dB |

### Separação: qualidade no MUSDB18

SDR (relação sinal/distorção) contra os stems verdadeiros, em 50 trechos de 7 s do conjunto de teste do MUSDB18 (50 com voz). Quanto maior, melhor.

| Variante | Configuração | SDR instrumental (mediana) | SDR voz (mediana) |
| --- | --- | --- | --- |
| BS-RoFormer (padrão) | padrão do modelo | 16.23 dB | 11.93 dB |
| BS-RoFormer rápido | sobreposição 2, autocast (fp16) | 16.20 dB | 11.91 dB |
| BS-RoFormer ultrarrápido | sobreposição 1, autocast (fp16) | 16.18 dB | 11.65 dB |
| MelBand RoFormer (padrão) | padrão do modelo | 15.61 dB | 11.53 dB |
| MelBand RoFormer rápido | sobreposição 2, autocast (fp16) | 15.64 dB | 11.60 dB |
| MelBand RoFormer ultrarrápido | sobreposição 1, autocast (fp16) | 15.61 dB | 11.53 dB |
| htdemucs_ft | padrão do modelo | 12.89 dB | 8.43 dB |

### Separação: as 6 músicas

| Variante | Configuração | Carregar | Separar (média/música) | Velocidade × tempo real | VRAM do processo (pico) |
| --- | --- | --- | --- | --- | --- |
| BS-RoFormer rápido | sobreposição 2, autocast (fp16) | 1.4 s | 65.8 s | 4.3× | 2519 MiB |
| MelBand RoFormer rápido | sobreposição 2, autocast (fp16) | 1.8 s | 31.5 s | 8.9× | 3259 MiB |
| htdemucs_ft | padrão do modelo | 0.1 s | 53.6 s | 5.2× | 1488 MiB |

Tempo de separação por música:

| Música | BS-RoFormer rápido | MelBand RoFormer rápido | htdemucs_ft |
| --- | --- | --- | --- |
| evidencias | 69.9 s | 33.4 s | 58.1 s |
| tempo-perdido | 70.5 s | 34.1 s | 58.0 s |
| ai-se-eu-te-pego | 38.8 s | 18.8 s | 33.2 s |
| bohemian-rhapsody | 82.3 s | 39.2 s | 66.0 s |
| dont-stop-believin | 58.2 s | 27.8 s | 46.5 s |
| lose-yourself | 74.8 s | 35.8 s | 59.7 s |

### Alinhamento da letra

Erro = distância entre o início alinhado de cada linha e o tempo do LRC, depois de ajustar uma reta (deslocamento e escala) que descarta linhas a mais de 2 s.

| Variante | Carregar | Alinhar (média/música) | VRAM do processo (pico) | Erro mediano | Linhas ≤ 0,5 s | Linhas ≤ 1 s | Linhas com erro > 2 s | Falhas |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| turbo · voz isolada | 7.9 s | 7.3 s | 3863 MiB | 0.24 s | 81% | 91% | 21 de 329 | 0 |
| turbo · voz isolada · VAD | 7.9 s | 7.3 s | 3863 MiB | 0.26 s | 69% | 76% | 71 de 329 | 0 |
| turbo · mix original (controle) | 7.9 s | 7.3 s | 3863 MiB | 0.32 s | 64% | 74% | 65 de 329 | 0 |
| large-v3 · voz isolada | 2.6 s | 4.1 s | 4044 MiB | 0.38 s | 65% | 77% | 53 de 329 | 0 |
| large-v3 · voz isolada · VAD | 2.6 s | 5.8 s | 4044 MiB | 0.37 s | 64% | 77% | 50 de 329 | 0 |

Por música (linhas ≤ 0,5 s · linhas com erro > 2 s):

| Música | turbo · voz isolada | turbo · voz isolada · VAD | turbo · mix original (controle) | large-v3 · voz isolada | large-v3 · voz isolada · VAD |
| --- | --- | --- | --- | --- | --- |
| evidencias | 76% · 2 > 2 s | 75% · 4 > 2 s | 66% · 6 > 2 s | 64% · 2 > 2 s | 66% · 2 > 2 s |
| tempo-perdido | 84% · 3 > 2 s | 86% · 2 > 2 s | 62% · 3 > 2 s | 54% · 4 > 2 s | 40% · 3 > 2 s |
| ai-se-eu-te-pego | 74% · 6 > 2 s | 76% · 6 > 2 s | 65% · 6 > 2 s | 74% · 3 > 2 s | 76% · 3 > 2 s |
| bohemian-rhapsody | 68% · 9 > 2 s | 0% · 50 > 2 s | 0% · 48 > 2 s | 58% · 12 > 2 s | 56% · 10 > 2 s |
| dont-stop-believin | 82% · 1 > 2 s | 56% · 9 > 2 s | 67% · 1 > 2 s | 0% · 32 > 2 s | 3% · 32 > 2 s |
| lose-yourself | 95% · 0 > 2 s | 96% · 0 > 2 s | 95% · 1 > 2 s | 95% · 0 > 2 s | 97% · 0 > 2 s |

Diferenças entre o vídeo e a letra do LRCLIB que o alinhamento absorve (variante turbo · voz isolada):

| Música | Deslocamento vídeo × LRC | Deriva de velocidade do LRC |
| --- | --- | --- |
| evidencias | -0.0 s | 1.19% |
| tempo-perdido | -0.1 s | -0.06% |
| ai-se-eu-te-pego | -5.5 s | -0.42% |
| bohemian-rhapsody | 0.2 s | -0.09% |
| dont-stop-believin | 1.0 s | 0.11% |
| lose-yourself | 0.1 s | -0.13% |

### Sincronização: LRC como esqueleto (spike 0b)

As linhas começam no tempo do LRC, levado para o relógio do áudio pela reta ajustada contra o alinhamento da música inteira; as palavras são alinhadas dentro da janela de cada linha. Sem gabarito palavra por palavra, a concordância entre os dois alinhadores independentes é o indicador objetivo; o veredito é de ouvido.

| Música | Linhas | Linhas que o alinhamento atual deslocava > 1 s | > 2 s | Deriva do LRC | Concordância stable-ts × CTC (palavras ≤ 0,2 s) |
| --- | --- | --- | --- | --- | --- |
| evidencias | 59 | 5 | 2 | 1.19% | 76% |
| tempo-perdido | 37 | 3 | 3 | -0.06% | 65% |
| ai-se-eu-te-pego | 51 | 9 | 6 | -0.42% | 62% |
| bohemian-rhapsody | 50 | 10 | 9 | -0.09% | 70% |
| dont-stop-believin | 39 | 3 | 1 | 0.11% | 66% |
| lose-yourself | 93 | 1 | 0 | -0.13% | 89% |

| Variante | Tempo médio por música | Linhas sem alinhamento de palavras (plano B) |
| --- | --- | --- |
| LRC + stable-ts por linha | 18.9 s | 0 de 329 |
| LRC + CTC por linha | 1.9 s | 4 de 329 |

### Mudança de tom

Motor R3 (`--fine`), os dois stems um após o outro, na CPU (i5-12400F).

| Música | Duração | −4 semitons (2 stems) | +4 semitons (2 stems) | Maior diferença de duração |
| --- | --- | --- | --- | --- |
| evidencias | 299 s | 73.6 s | 98.0 s | 0.0 ms |
| tempo-perdido | 303 s | 67.3 s | 96.3 s | 0.0 ms |
| ai-se-eu-te-pego | 165 s | 33.9 s | 48.8 s | 0.0 ms |
| bohemian-rhapsody | 354 s | 120.1 s | 260.6 s | 0.0 ms |
| dont-stop-believin | 250 s | 46.3 s | 54.1 s | 0.0 ms |
| lose-yourself | 321 s | 122.1 s | 115.8 s | 0.0 ms |

Alternativas mais rápidas, em `evidencias` (299 s) a +4 semitons:

| Opção | Tempo | Diferença de duração |
| --- | --- | --- |
| R3 (finer), stems em paralelo | 69.1 s | 0.0 ms |
| R2 (faster), stems em paralelo | 11.8 s | 0.0 ms |

### Tempo total por música

Combinação: BS-RoFormer rápido + turbo · voz isolada, carregando cada modelo a cada job (um modelo por vez na GPU de 8 GB).

| Música | Duração | Metadados + letra | Download | Separação (com carga) | Alinhamento (com carga) | Opus | Total |
| --- | --- | --- | --- | --- | --- | --- | --- |
| evidencias | 299 s | 1.7 s | 3.0 s | 71.3 s | 13.8 s | 5.4 s | 95.2 s |
| tempo-perdido | 303 s | 1.8 s | 2.4 s | 71.9 s | 14.6 s | 5.2 s | 95.8 s |
| ai-se-eu-te-pego | 165 s | 1.7 s | 2.0 s | 40.2 s | 11.4 s | 2.8 s | 58.2 s |
| bohemian-rhapsody | 354 s | 1.3 s | 3.2 s | 83.7 s | 20.8 s | 5.8 s | 114.9 s |
| dont-stop-believin | 250 s | 1.5 s | 2.4 s | 59.6 s | 18.7 s | 4.5 s | 86.7 s |
| lose-yourself | 321 s | 1.8 s | 2.9 s | 76.2 s | 12.1 s | 5.8 s | 98.8 s |
| **média** |  |  |  |  |  |  | **91.6 s** |

O processamento leva em média 33% da duração da música.
