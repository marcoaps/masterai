"""
Aplica automaticamente a Fase 6 (separador de stems) no projeto masterai:
  1. Adiciona 'import zipfile' e 'DEMUCS_OK' no app.py
  2. Insere a rota /separar, /download_stems e o job de processamento
  3. Adiciona 'demucs' ao requirements.txt
  4. Faz git add + commit + push

Rodar de dentro da pasta do projeto (onde está o app.py):
    python aplicar_stems.py

Precisa que 'adicionar_ao_app.py' esteja na mesma pasta.
Seguro rodar mais de uma vez — se já tiver sido aplicado, ele pula e avisa.
"""

import subprocess
from pathlib import Path

APP_PATH = Path("app.py")
REQ_PATH = Path("requirements.txt")
BLOCK_PATH = Path("adicionar_ao_app.py")


def patch_app():
    if not APP_PATH.exists():
        raise SystemExit("❌ Não encontrei app.py nesta pasta. Rode o script de dentro da pasta do projeto.")
    if not BLOCK_PATH.exists():
        raise SystemExit("❌ Não encontrei adicionar_ao_app.py nesta pasta. Baixe e coloque aqui primeiro.")

    content = APP_PATH.read_text(encoding="utf-8")
    changed = False

    if "import zipfile" not in content:
        anchor = "import numpy as np"
        if anchor not in content:
            raise SystemExit(f"❌ Não encontrei a linha '{anchor}' no app.py — ajuste manual necessário.")
        content = content.replace(anchor, anchor + "\nimport zipfile", 1)
        changed = True
        print("✅ Adicionado: import zipfile")
    else:
        print("↪️  import zipfile já existe, pulando")

    if "DEMUCS_OK" not in content:
        anchor = 'FFMPEG_OK = shutil.which("ffmpeg") is not None'
        if anchor not in content:
            raise SystemExit(f"❌ Não encontrei a linha '{anchor}' no app.py — ajuste manual necessário.")
        content = content.replace(anchor, anchor + '\nDEMUCS_OK = shutil.which("demucs") is not None', 1)
        changed = True
        print("✅ Adicionado: DEMUCS_OK")
    else:
        print("↪️  DEMUCS_OK já existe, pulando")

    if "/separar" not in content:
        anchor = 'if __name__ == "__main__":'
        if anchor not in content:
            raise SystemExit(f"❌ Não encontrei a linha '{anchor}' no app.py — ajuste manual necessário.")
        bloco = BLOCK_PATH.read_text(encoding="utf-8")
        content = content.replace(anchor, bloco + "\n\n" + anchor, 1)
        changed = True
        print("✅ Adicionada rota /separar, /download_stems e processar_stems_job")
    else:
        print("↪️  Rota /separar já existe, pulando")

    if changed:
        APP_PATH.write_text(content, encoding="utf-8")
        print("💾 app.py salvo")
    else:
        print("Nada para alterar em app.py")

    return changed


def patch_requirements():
    if not REQ_PATH.exists():
        raise SystemExit("❌ Não encontrei requirements.txt nesta pasta.")
    content = REQ_PATH.read_text(encoding="utf-8")
    if "demucs" not in content:
        content = content.rstrip("\n") + "\ndemucs\n"
        REQ_PATH.write_text(content, encoding="utf-8")
        print("✅ demucs adicionado ao requirements.txt")
        return True
    print("↪️  demucs já está no requirements.txt, pulando")
    return False


def git_commit_push():
    subprocess.run(["git", "add", "."])
    result = subprocess.run(
        ["git", "commit", "-m", "Adiciona separador de stems (Demucs)"],
        capture_output=True, text=True
    )
    print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    push = subprocess.run(["git", "push"], capture_output=True, text=True)
    print(push.stdout.strip())
    if push.stderr.strip():
        print(push.stderr.strip())
    print("🚀 Concluído")


if __name__ == "__main__":
    mudou_app = patch_app()
    mudou_req = patch_requirements()
    if mudou_app or mudou_req:
        git_commit_push()
    else:
        print("Nada mudou — nenhum commit necessário.")
