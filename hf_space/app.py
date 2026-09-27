"""
masterai — separador de stems rodando no Hugging Face Spaces (grátis).

Recebe um arquivo de áudio, roda o Demucs (htdemucs) e devolve um .zip com
vocals.wav, drums.wav, bass.wav e other.wav.
"""

import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import gradio as gr

MODELO = "htdemucs"


def separar(caminho_audio: str) -> str:
    if not caminho_audio:
        raise gr.Error("Envie um arquivo de áudio.")

    pasta = Path(tempfile.mkdtemp(prefix="stems_"))
    # Nome simples evita problemas com acentos/espaços no nome original
    entrada = pasta / ("faixa" + Path(caminho_audio).suffix.lower())
    shutil.copy(caminho_audio, entrada)

    resultado = subprocess.run(
        [sys.executable, "-m", "demucs", "-n", MODELO, "-o", str(pasta / "saida"), str(entrada)],
        capture_output=True, text=True,
    )
    if resultado.returncode != 0:
        detalhes = ((resultado.stderr or "") + "\n" + (resultado.stdout or "")).strip()
        raise gr.Error("Falha no Demucs: " + detalhes[-1200:])

    stems = pasta / "saida" / MODELO / entrada.stem
    arquivos = sorted(stems.glob("*.wav"))
    if not arquivos:
        raise gr.Error("O Demucs terminou, mas não gerou os stems.")

    zip_path = pasta / "stems.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in arquivos:
            zf.write(f, arcname=f.name)
    return str(zip_path)


demo = gr.Interface(
    fn=separar,
    inputs=gr.Audio(type="filepath", label="Faixa"),
    outputs=gr.File(label="Stems (.zip)"),
    title="masterai — separador de stems",
    description="Separa vocais, bateria, baixo e outros com Demucs (htdemucs). Leva alguns minutos em CPU.",
    api_name="separar",
    flagging_mode="never",
)

if __name__ == "__main__":
    # Uma separação por vez: o Demucs usa bastante CPU/RAM.
    demo.queue(default_concurrency_limit=1, max_size=10).launch()
