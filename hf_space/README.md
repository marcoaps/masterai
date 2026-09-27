---
title: masterai stems
emoji: 🎚️
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: 5.49.1
app_file: app.py
pinned: false
license: mit
---

# masterai — separador de stems (Demucs)

Space gratuito (CPU básico: 2 vCPU, 16 GB de RAM) que separa uma faixa em
vocais, bateria, baixo e outros usando o Demucs (`htdemucs`) e devolve um `.zip`.

O app principal (masterai, no Render) chama este Space pela API do Gradio,
então o Render não precisa carregar o PyTorch — e para de dar erro 502 por falta de memória.

Endpoint da API: `/separar` (entrada: arquivo de áudio; saída: arquivo .zip).
