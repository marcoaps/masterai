"""
Separa uma faixa em vocals/drums/bass/other com o Demucs (htdemucs), só no seu PC.

Usa o Demucs apenas para a separação. Ler e salvar o áudio fica com o soundfile,
porque o torchaudio novo (2.9+) mudou a forma de salvar e quebra o comando "demucs".
Assim funciona com qualquer versão do PyTorch, inclusive no Python 3.14.

Uso: python stems_local.py <entrada> <pasta_saida>
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf


def main(entrada, pasta_saida):
    import torch
    from demucs.pretrained import get_model
    from demucs.apply import apply_model

    pasta = Path(pasta_saida)
    pasta.mkdir(parents=True, exist_ok=True)

    print("Carregando o modelo htdemucs (a primeira vez baixa uns 80 MB)...", flush=True)
    model = get_model("htdemucs")
    model.eval()
    sr = model.samplerate  # 44100

    print("Lendo o áudio...", flush=True)
    try:
        audio, sr_in = sf.read(entrada, dtype="float32", always_2d=True)
    except Exception:
        import librosa  # mp3/m4a etc.
        y, sr_in = librosa.load(entrada, sr=None, mono=False)
        audio = (y if y.ndim == 2 else y[None, :]).T.astype(np.float32)
    if sr_in != sr:
        import librosa
        audio = librosa.resample(audio.T, orig_sr=sr_in, target_sr=sr).T
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    audio = audio[:, :2]

    wav = torch.from_numpy(np.ascontiguousarray(audio.T))
    ref = wav.mean(0)
    media, desvio = ref.mean(), ref.std() + 1e-8
    wav = (wav - media) / desvio

    print("Separando (vários minutos em CPU)...", flush=True)
    with torch.no_grad():
        fontes = apply_model(model, wav[None], device="cpu", split=True,
                             overlap=0.25, progress=True)[0]
    fontes = fontes * desvio + media

    for nome, fonte in zip(model.sources, fontes):
        destino = pasta / f"{nome}.wav"
        sf.write(str(destino), fonte.numpy().T, sr, subtype="PCM_16")
        print(f"Salvo: {destino.name}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
