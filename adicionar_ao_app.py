# ══════════════════════════════════════════════════════════════
#  SEPARADOR DE STEMS (Demucs) — Fase 6 do roadmap
# ══════════════════════════════════════════════════════════════

def processar_stems_job(job_id, input_path):
    """Roda em thread separada — mesmo padrão do processar_job() de mastering."""
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["log"].append("Separando stems (vocais, bateria, baixo, outros)...")

        if not DEMUCS_OK:
            raise RuntimeError("Demucs não está instalado no servidor")

        stems_dir = OUTPUT_DIR / f"stems_{job_id}"
        stems_dir.mkdir(exist_ok=True)

        result = subprocess.run(
            ["demucs", "-n", "htdemucs", "-o", str(stems_dir), input_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            erro = result.stderr[-500:] if result.stderr else "Falha desconhecida no Demucs"
            raise RuntimeError(erro)

        jobs[job_id]["log"].append("Separação concluída, compactando arquivos...")

        # Demucs gera: stems_dir/htdemucs/<nome_do_arquivo>/{vocals,drums,bass,other}.wav
        track_name = Path(input_path).stem
        stems_output = stems_dir / "htdemucs" / track_name
        if not stems_output.exists():
            raise RuntimeError("Pasta de stems não encontrada após a separação")

        zip_path = OUTPUT_DIR / f"{job_id}_stems.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for stem_file in stems_output.glob("*.wav"):
                zf.write(stem_file, arcname=stem_file.name)
                jobs[job_id]["log"].append(f"Adicionado: {stem_file.name}")

        jobs[job_id]["output"] = str(zip_path)
        jobs[job_id]["status"] = "done"
        jobs[job_id]["log"].append("Pronto!")

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


@app.route("/separar", methods=["POST"])
def separar():
    data = request.json or {}
    file_id = data.get("file_id")

    input_path = None
    for ext in [".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"]:
        p = UPLOAD_DIR / f"{file_id}{ext}"
        if p.exists():
            input_path = p
            break
    if not input_path:
        return jsonify({"error": "Arquivo não encontrado"}), 404

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "queued", "log": [], "file_id": file_id, "mode": "stems"}

    t = threading.Thread(
        target=processar_stems_job,
        args=(job_id, str(input_path)),
        daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/download_stems/<job_id>")
def download_stems(job_id):
    if job_id not in jobs or jobs[job_id]["status"] != "done":
        return jsonify({"error": "Arquivo não pronto"}), 404
    path = jobs[job_id]["output"]
    return send_file(path, as_attachment=True,
                     download_name=f"stems_{job_id}.zip",
                     mimetype="application/zip")
