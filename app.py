"""
MasterAI Pro — Backend Flask
Masterização com loudness maximization profissional
"""

import os, sys, shutil, subprocess, uuid, threading
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
import numpy as np
import zipfile

DEPS_OK = True
try:
    import soundfile as sf
    import librosa
    from scipy.signal import butter, sosfilt, lfilter
    import pyloudnorm as pyln
except ImportError as e:
    DEPS_OK = False
    print(f"⚠️  Dep faltando: {e}")

FFMPEG_OK = shutil.which("ffmpeg") is not None
DEMUCS_OK = shutil.which("demucs") is not None

app = Flask(__name__, static_folder="static")
BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

jobs = {}


# ══════════════════════════════════════════════════════════════
#  UTILITÁRIOS DE SINAL
# ══════════════════════════════════════════════════════════════

def ap(y, func):
    """Aplica função canal a canal."""
    if y.ndim == 2:
        return np.column_stack([func(y[:, i]) for i in range(y.shape[1])])
    return func(y)

def norm(y, ceil=0.98):
    pk = np.max(np.abs(y)) + 1e-9
    return y / pk * ceil if pk > ceil else y

def make_hp(sr, freq, ordem=2):
    freq = min(max(freq, 1), sr//2-50)
    return butter(ordem, freq, btype="high", fs=sr, output="sos")

def make_lp(sr, freq, ordem=2):
    freq = min(max(freq, 1), sr//2-50)
    return butter(ordem, freq, btype="low", fs=sr, output="sos")

def peaking(y, sr, freq, gain_db, Q=1.4):
    if abs(gain_db) < 0.05: return y
    A  = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * min(max(freq, 1), sr//2-50) / sr
    al = np.sin(w0) / (2 * Q)
    b  = [1+al*A, -2*np.cos(w0), 1-al*A]
    a  = [1+al/A, -2*np.cos(w0), 1-al/A]
    b  = [x/a[0] for x in b]; a = [x/a[0] for x in a]
    return ap(y, lambda c: lfilter(b, a, c))

def shelf_hi(y, sr, freq, gain_db):
    if abs(gain_db) < 0.05: return y
    A  = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * min(max(freq, 1), sr//2-50) / sr
    al = np.sin(w0) / 2 / 0.707
    b  = [A*((A+1)+(A-1)*np.cos(w0)+2*np.sqrt(A)*al),
          -2*A*((A-1)+(A+1)*np.cos(w0)),
          A*((A+1)+(A-1)*np.cos(w0)-2*np.sqrt(A)*al)]
    a  = [(A+1)-(A-1)*np.cos(w0)+2*np.sqrt(A)*al,
          2*((A-1)-(A+1)*np.cos(w0)),
          (A+1)-(A-1)*np.cos(w0)-2*np.sqrt(A)*al]
    b  = [x/a[0] for x in b]; a = [x/a[0] for x in a]
    return ap(y, lambda c: lfilter(b, a, c))

def shelf_lo(y, sr, freq, gain_db):
    if abs(gain_db) < 0.05: return y
    A  = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * min(max(freq, 1), sr//2-50) / sr
    al = np.sin(w0) / 2 / 0.707
    b  = [A*((A+1)-(A-1)*np.cos(w0)+2*np.sqrt(A)*al),
          2*A*((A-1)-(A+1)*np.cos(w0)),
          A*((A+1)-(A-1)*np.cos(w0)-2*np.sqrt(A)*al)]
    a  = [(A+1)+(A-1)*np.cos(w0)+2*np.sqrt(A)*al,
          -2*((A-1)+(A+1)*np.cos(w0)),
          (A+1)+(A-1)*np.cos(w0)-2*np.sqrt(A)*al]
    b  = [x/a[0] for x in b]; a = [x/a[0] for x in a]
    return ap(y, lambda c: lfilter(b, a, c))


# ══════════════════════════════════════════════════════════════
#  BLOCO DE LOUDNESS MAXIMIZATION
#  Este é o coração do "peso" — Volume alto sem estourar
# ══════════════════════════════════════════════════════════════

def compressor_vca(canal, sr, thr_db=-18, ratio=4.0,
                   att_ms=8, rel_ms=100, makeup_db=4.0, knee_db=4.0):
    """
    Compressor VCA com knee suave.
    makeup_db alto = mais volume = mais peso.
    """
    thresh  = 10 ** (thr_db / 20)
    makeup  = 10 ** (makeup_db / 20)
    knee    = 10 ** (knee_db / 20)
    att     = 1 - np.exp(-1 / (sr * att_ms / 1000))
    rel     = 1 - np.exp(-1 / (sr * rel_ms / 1000))
    gain    = np.ones(len(canal))
    env     = 0.0
    for i in range(len(canal)):
        lv   = abs(canal[i])
        env += att * (lv - env) if lv > env else rel * (lv - env)
        # Soft knee
        if env < thresh / knee:
            gain[i] = makeup
        elif env < thresh * knee:
            # Zona de knee
            over   = env - thresh / knee
            zone   = thresh * knee - thresh / knee
            frac   = over / (zone + 1e-9)
            r_eff  = 1 + (ratio - 1) * frac * 0.5
            gain[i] = (thresh / knee + over / r_eff) / (env + 1e-9) * makeup
        else:
            red    = thresh + (env - thresh) / ratio
            gain[i] = red / (env + 1e-9) * makeup
    return canal * np.clip(gain, 0, 8)


def saturacao_tape(canal, sr, drive=0.5, harmonicos=0.35):
    """
    Emulação de fita magnética:
    - Saturação tanh suave
    - Geração de 2ª e 3ª harmônicas (dá calor e corpo)
    - Sem adicionar volume excessivo
    """
    # Satura com tanh
    sat = np.tanh(canal * (1 + drive * 6))
    pk  = np.max(np.abs(sat)) + 1e-9
    sat = sat / pk * np.max(np.abs(canal))

    # Extrai harmônicos adicionados (diferença sat - original)
    sos_hi = make_hp(sr, min(800, sr//2-50), ordem=2)
    harm   = sosfilt(sos_hi, sat - canal) * harmonicos

    resultado = canal + harm
    # Mantém o mesmo pico do original — não perde headroom
    pk_orig = np.max(np.abs(canal)) + 1e-9
    pk_res  = np.max(np.abs(resultado)) + 1e-9
    return resultado / pk_res * pk_orig


def clipper_suave(canal, thr=0.80):
    """
    Hard clipper analógico com suavização.
    Permite empurrar mais volume antes do limiter.
    Gera harmônicos ímpares (som de válvula/fita).
    """
    out = canal.copy()
    mask = np.abs(canal) > thr
    over = np.abs(canal[mask]) - thr
    # Curva de saturação progressiva
    out[mask] = np.sign(canal[mask]) * (
        thr + (1 - thr) * (1 - np.exp(-over * 3))
    )
    return out


def limiter_lookahead(y, sr, ceil_db=-0.3, lookahead_ms=3, release_ms=60):
    """
    Limiter brick-wall com lookahead.
    Ceiling mais alto (-0.3 dB) = mais volume percebido.
    """
    ceil    = 10 ** (ceil_db / 20)
    la      = int(sr * lookahead_ms / 1000)
    rel_c   = 1 - np.exp(-1 / (sr * release_ms / 1000))

    def lim_canal(c):
        # Pad com lookahead
        padded = np.concatenate([c, np.zeros(la)])
        out    = np.zeros(len(c))
        g      = 1.0
        for i in range(len(c)):
            # Pico com lookahead
            pk = np.max(np.abs(padded[i:i+la+1]))
            if pk * g > ceil:
                g = ceil / (pk + 1e-9)
            else:
                g = min(1.0, g + rel_c * (1.0 - g))
            out[i] = c[i] * g
        return out

    return ap(y, lim_canal)


def maximizer(y, sr, target_lufs=-9.0, ceil_db=-0.3):
    """
    Loudness Maximizer completo:
    1. Analisa o LUFS atual
    2. Aplica ganho até o target
    3. Roda o limiter para não estourar
    4. Repete até atingir o target com segurança

    target_lufs mais alto = mais PESO e volume.
    -9 LUFS = muito forte (club/streaming agressivo)
    -14 LUFS = padrão Spotify
    """
    meter = pyln.Meter(sr)

    for _ in range(3):  # até 3 passes para convergir
        lufs = meter.integrated_loudness(y)
        if not np.isfinite(lufs) or lufs >= target_lufs - 0.2:
            break
        # Aplica ganho necessário
        diff = target_lufs - lufs
        gain = 10 ** (diff / 20)
        y    = y * gain
        # Limita o pico
        y    = limiter_lookahead(y, sr, ceil_db=ceil_db)

    return y


# ══════════════════════════════════════════════════════════════
#  ANÁLISE
# ══════════════════════════════════════════════════════════════

def analisar(y, sr):
    meter = pyln.Meter(sr)
    lufs  = meter.integrated_loudness(y)
    mono  = (y[:,0]+y[:,1])/2 if y.ndim==2 else y
    pico  = float(20*np.log10(np.max(np.abs(mono))+1e-9))
    rms   = float(20*np.log10(np.sqrt(np.mean(mono**2))+1e-9))
    dr    = pico - rms
    corr  = float(np.corrcoef(y[:,0],y[:,1])[0,1]) if y.ndim==2 else 1.0
    fft   = np.abs(np.fft.rfft(mono, n=32768))
    freqs = np.fft.rfftfreq(32768, 1/sr)
    def banda(f1, f2):
        m = (freqs>=f1)&(freqs<f2)
        return float(np.mean(fft[m]**2)) if m.any() else 0.0
    tot = sum([banda(20,200),banda(200,2000),banda(2000,8000),banda(8000,20000)])+1e-9
    return {
        "lufs":       round(float(lufs),1) if np.isfinite(lufs) else -99,
        "peak":       round(pico,1),
        "rms":        round(rms,1),
        "dr":         round(dr,1),
        "stereo_corr":round(corr,3),
        "sub":        round(banda(20,200)/tot*100,1),
        "mid":        round(banda(200,2000)/tot*100,1),
        "pres":       round(banda(2000,8000)/tot*100,1),
        "air":        round(banda(8000,20000)/tot*100,1),
    }


# ══════════════════════════════════════════════════════════════
#  PIPELINE AUTO — LOUDNESS MAXIMIZATION
# ══════════════════════════════════════════════════════════════

def pipeline_auto(y, sr, loudness_target, genre):
    """
    Pipeline focado em PESO = volume alto sem estourar.
    Cadeia:  EQ → Sub-harmonic → Tape Sat → Compressão Multibanda
          → Clipper → Stereo M/S → Maximizer (multipass)
    """

    # ── PRESETS DE EQ POR GÊNERO ─────────────────────────────
    presets = {
        "pop":      {"sub":3.0,"bass":2.0,"lm":-2.5,"mid":1.5,"pres":3.5,"air":3.5},
        "rock":     {"sub":2.0,"bass":4.0,"lm":-3.5,"mid":2.0,"pres":4.5,"air":2.5},
        "hiphop":   {"sub":5.5,"bass":4.5,"lm":-4.0,"mid":0.5,"pres":2.5,"air":2.0},
        "gospel":   {"sub":3.5,"bass":3.0,"lm":-2.5,"mid":2.5,"pres":5.0,"air":4.0},
        "eletr":    {"sub":5.0,"bass":3.5,"lm":-4.5,"mid":0.5,"pres":2.0,"air":4.0},
        "balada":   {"sub":1.5,"bass":1.5,"lm":-1.5,"mid":2.0,"pres":4.5,"air":5.0},
        "sertanejo":{"sub":2.5,"bass":3.5,"lm":-3.0,"mid":2.5,"pres":4.5,"air":3.5},
        "default":  {"sub":3.5,"bass":2.5,"lm":-3.0,"mid":2.0,"pres":4.0,"air":3.5},
    }
    p = presets.get(genre, presets["default"])

    # ── 1. EQ CORRETIVA + TONAL ──────────────────────────────
    y = ap(y, lambda c: sosfilt(make_hp(sr, 22, 4), c))  # limpa DC/infra
    y = peaking(y, sr,   55, p["sub"],  Q=0.85)  # punch sub
    y = peaking(y, sr,  110, p["bass"], Q=1.1)   # corpo do grave
    y = peaking(y, sr,  270, p["lm"],   Q=1.6)   # corta barro/nasal
    y = peaking(y, sr,  900, p["mid"],  Q=1.3)   # calor dos médios
    y = peaking(y, sr, 3500, p["pres"], Q=1.0)   # presença/punch vocal
    y = shelf_hi(y, sr, 7000, p["air"])           # brilho/ar

    # ── 2. SUB-HARMONIC SYNTHESIS ────────────────────────────
    # Gera grave sintético onde a IA cortou
    def sub_synth(c):
        sos_bp = butter(4, [min(90,sr//2-50), min(220,sr//2-50)],
                        btype="band", fs=sr, output="sos")
        grave  = sosfilt(sos_bp, c)
        # Rectificação + filtragem = oitava abaixo
        sub_r  = np.abs(grave) - np.mean(np.abs(grave))
        sos_lp = butter(4, min(75, sr//2-50), btype="low", fs=sr, output="sos")
        sub    = sosfilt(sos_lp, sub_r) * 3.0
        r      = c + sub
        pk_c   = np.max(np.abs(c)) + 1e-9
        pk_r   = np.max(np.abs(r)) + 1e-9
        return r / pk_r * pk_c * 1.15   # +1.5 dB de ganho
    y = ap(y, sub_synth)

    # ── 3. SATURAÇÃO TAPE (calor antes da compressão) ────────
    y = ap(y, lambda c: saturacao_tape(c, sr, drive=0.55, harmonicos=0.40))
    y = norm(y, 0.97)

    # ── 4. COMPRESSÃO MULTIBANDA COM MAKEUP ALTO ─────────────
    # Cada banda comprime independente e sai com makeup positivo
    def multibanda(c):
        sos_lp1 = butter(2, min(200,  sr//2-50), btype="low",  fs=sr, output="sos")
        sos_hp1 = butter(2, min(200,  sr//2-50), btype="high", fs=sr, output="sos")
        sos_lp2 = butter(2, min(5000, sr//2-50), btype="low",  fs=sr, output="sos")
        sos_hp2 = butter(2, min(5000, sr//2-50), btype="high", fs=sr, output="sos")

        sub_b  = sosfilt(sos_lp1, c)
        mid_b  = sosfilt(sos_lp2, sosfilt(sos_hp1, c))
        hi_b   = sosfilt(sos_hp2, c)

        # Sub: comprime forte, makeup alto → peso e punch
        sub_c  = compressor_vca(sub_b, sr,
                    thr_db=-16, ratio=5.0, att_ms=25, rel_ms=200,
                    makeup_db=5.0, knee_db=4.0)
        # Médio: ratio moderado, makeup médio → corpo
        mid_c  = compressor_vca(mid_b, sr,
                    thr_db=-20, ratio=3.5, att_ms=8,  rel_ms=90,
                    makeup_db=3.5, knee_db=3.0)
        # Agudo: ratio suave, makeup baixo → controla sibilância
        hi_c   = compressor_vca(hi_b, sr,
                    thr_db=-24, ratio=2.5, att_ms=4,  rel_ms=50,
                    makeup_db=1.5, knee_db=2.0)

        resultado = sub_c + mid_c + hi_c
        # Renormaliza mantendo o ganho adicionado
        pk_c = np.max(np.abs(c)) + 1e-9
        pk_r = np.max(np.abs(resultado)) + 1e-9
        # Fator 1.4 = +3 dB de peso líquido após compressão
        return resultado / pk_r * pk_c * 1.4

    y = np.column_stack([multibanda(y[:,i]) for i in range(y.shape[1])]) \
        if y.ndim==2 else multibanda(y)
    y = norm(y, 0.97)

    # ── 5. EXCITER DE HARMÔNICOS ─────────────────────────────
    # Adiciona harmônicos nos agudos (soa mais "vivo" e presente)
    def exciter(c, drive=0.35, mix=0.30):
        sos = butter(3, min(4000, sr//2-100), btype="high", fs=sr, output="sos")
        hi  = sosfilt(sos, c)
        sat = np.tanh(hi * (1 + drive * 8))
        return c + sat * mix
    y = ap(y, exciter)

    # ── 6. STEREO ENHANCER M/S ───────────────────────────────
    if y.ndim == 2:
        L, R = y[:,0], y[:,1]
        mid  = (L + R) / 2
        side = (L - R) / 2
        # Abre o side nos agudos → mais espaço sem perder mono
        sos_hi = butter(2, min(3000,sr//2-50), btype="high", fs=sr, output="sos")
        side_hi = sosfilt(sos_hi, side)
        side    = side + side_hi * 0.5    # agudos mais largos
        side   *= 1.20                    # widening geral
        # Checa correlação para segurança mono
        if abs(np.corrcoef(mid, side)[0,1]) < 0.04:
            side *= 0.75
        y = norm(np.column_stack([mid+side, mid-side]), 0.97)

    # ── 7. SOFT CLIPPER 2 ESTÁGIOS ───────────────────────────
    # Satura progressivamente — permite empurrar mais LUFS
    y = ap(y, lambda c: clipper_suave(c, thr=0.78))
    y = ap(y, lambda c: clipper_suave(c, thr=0.88))

    # ── 8. MAXIMIZER MULTIPASS (o grande segredo do PESO) ────
    # Aumenta volume em múltiplos passes:
    # cada pass comprime os picos novos gerados pelo ganho anterior
    y = maximizer(y, sr,
                  target_lufs=loudness_target,
                  ceil_db=-0.2)   # -0.2 dBTP = máximo possível sem clippar

    return y


# ══════════════════════════════════════════════════════════════
#  PIPELINE ADVANCED
# ══════════════════════════════════════════════════════════════

def pipeline_advanced(y, sr, params):
    lufs_target = params.get("lufs", -14.0)

    y = ap(y, lambda c: sosfilt(make_hp(sr, params.get("hp_freq",22), 4), c))

    for freq, key, Q in [(55,"sub",0.9),(110,"bass",1.2),(270,"low_mid",1.5),
                          (900,"mid",1.3),(3500,"presence",1.1),(8000,"air",1.0)]:
        g = params.get(key, 0.0)
        if abs(g) > 0.05: y = peaking(y, sr, freq, g, Q)
    g = params.get("high_shelf", 0.0)
    if abs(g) > 0.05: y = shelf_hi(y, sr, 12000, g)

    drive = params.get("drive", 0.3)
    if drive > 0:
        y = ap(y, lambda c: saturacao_tape(c, sr, drive=drive, harmonicos=0.35))

    def comp(c):
        return compressor_vca(c, sr,
            thr_db=params.get("comp_thr",-20),
            ratio=params.get("comp_ratio",3.0),
            att_ms=params.get("comp_att",10),
            rel_ms=params.get("comp_rel",80),
            makeup_db=params.get("comp_makeup",3.0))
    y = ap(y, comp)

    larg = params.get("stereo", 1.15)
    if y.ndim == 2:
        L,R=y[:,0],y[:,1]; mid=(L+R)/2; side=(L-R)/2*larg
        y = norm(np.column_stack([mid+side,mid-side]),0.97)

    y = ap(y, lambda c: clipper_suave(c, thr=0.80))
    y = ap(y, lambda c: clipper_suave(c, thr=0.90))
    y = maximizer(y, sr, target_lufs=lufs_target, ceil_db=params.get("ceiling",-0.3))
    return y


# ══════════════════════════════════════════════════════════════
#  PIPELINE REFERENCE
# ══════════════════════════════════════════════════════════════

def pipeline_reference(y, sr, ref_path, loudness_target):
    y_ref, sr_ref = librosa.load(ref_path, sr=sr, mono=False)
    if y_ref.ndim == 1: y_ref = np.column_stack([y_ref, y_ref])
    else: y_ref = y_ref.T

    mono   = (y[:,0]+y[:,1])/2    if y.ndim==2    else y
    mono_r = (y_ref[:,0]+y_ref[:,1])/2 if y_ref.ndim==2 else y_ref

    n = 65536
    fft_in  = np.abs(np.fft.rfft(mono[:min(len(mono),n)],   n=n))
    fft_ref = np.abs(np.fft.rfft(mono_r[:min(len(mono_r),n)], n=n))
    freqs   = np.fft.rfftfreq(n, 1/sr)

    oitavas = [(55,110,70),(110,220,150),(220,440,300),(440,880,600),
               (880,1760,1200),(1760,3500,2500),(3500,7000,5000),(7000,14000,9000)]
    for f_lo, f_hi, f_c in oitavas:
        mask = (freqs>=f_lo)&(freqs<f_hi)
        if not mask.any(): continue
        e_in  = np.mean(fft_in[mask]**2)  + 1e-9
        e_ref = np.mean(fft_ref[mask]**2) + 1e-9
        ratio_db = np.clip(10*np.log10(e_ref/e_in), -7, 7)
        if abs(ratio_db) > 0.3:
            y = peaking(y, sr, f_c, ratio_db * 0.75, Q=0.9)

    y = ap(y, lambda c: saturacao_tape(c, sr, drive=0.3, harmonicos=0.25))
    y = ap(y, lambda c: clipper_suave(c, thr=0.82))

    meter   = pyln.Meter(sr)
    lufs_ref = meter.integrated_loudness(y_ref)
    alvo    = min(lufs_ref if np.isfinite(lufs_ref) else loudness_target, loudness_target)
    y = maximizer(y, sr, target_lufs=alvo, ceil_db=-0.2)
    return y


# ══════════════════════════════════════════════════════════════
#  JOB RUNNER
# ══════════════════════════════════════════════════════════════

def processar_job(job_id, input_path, mode, params, ref_path, output_path):
    try:
        jobs[job_id]["status"] = "processing"
        log = jobs[job_id]["log"]

        log.append("Carregando áudio...")
        y, sr = librosa.load(input_path, sr=44100, mono=False)
        if y.ndim == 1: y = np.column_stack([y, y])
        else: y = y.T

        log.append("Analisando espectro original...")
        jobs[job_id]["analise_antes"] = analisar(y, sr)

        loudness_target = params.get("lufs", -9.0)

        if mode == "auto":
            genre = params.get("genre", "default")
            log.append(f"Modo Auto — gênero: {genre} | alvo: {loudness_target} LUFS")
            log.append("EQ tonal por gênero...")
            log.append("Sub-harmonic synthesis...")
            log.append("Saturação tape...")
            log.append("Compressão multibanda...")
            log.append("Exciter + Stereo M/S...")
            log.append("Soft clipper 2 estágios...")
            log.append("Maximizer multipass (peso)...")
            y = pipeline_auto(y, sr, loudness_target, genre)

        elif mode == "advanced":
            log.append("Modo Avançado...")
            log.append("EQ 7 bandas...")
            log.append("Compressor VCA...")
            log.append("Saturação + Stereo...")
            log.append("Maximizer...")
            y = pipeline_advanced(y, sr, params)

        elif mode == "reference":
            if not ref_path or not os.path.exists(ref_path):
                raise ValueError("Faixa de referência não encontrada")
            log.append("Modo Referência...")
            log.append("Analisando referência...")
            log.append("Casando timbre banda por banda...")
            log.append("Maximizer...")
            y = pipeline_reference(y, sr, ref_path, loudness_target)

        log.append("Exportando WAV 24-bit...")
        sf.write(output_path, y, sr, subtype="PCM_24")

        log.append("Analisando resultado final...")
        jobs[job_id]["analise_depois"] = analisar(y, sr)
        jobs[job_id]["status"]  = "done"
        jobs[job_id]["output"]  = str(output_path)
        log.append("✅ Masterização concluída!")

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"]  = str(e)
        jobs[job_id]["log"].append(f"❌ Erro: {e}")


# ══════════════════════════════════════════════════════════════
#  ROTAS FLASK
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "Nenhum arquivo"}), 400
    f   = request.files["file"]
    uid = str(uuid.uuid4())[:8]
    ext = Path(f.filename).suffix.lower()
    path = UPLOAD_DIR / f"{uid}{ext}"
    f.save(path)
    return jsonify({"file_id": uid, "filename": f.filename, "ext": ext})

@app.route("/master", methods=["POST"])
def master():
    data    = request.json or {}
    file_id = data.get("file_id")
    mode    = data.get("mode", "auto")
    params  = data.get("params", {})
    ref_id  = data.get("ref_id")

    input_path = None
    for ext in [".mp3",".wav",".flac",".ogg",".m4a",".aac"]:
        p = UPLOAD_DIR / f"{file_id}{ext}"
        if p.exists(): input_path = p; break
    if not input_path:
        return jsonify({"error": "Arquivo não encontrado"}), 404

    ref_path = None
    if ref_id:
        for ext in [".mp3",".wav",".flac"]:
            p = UPLOAD_DIR / f"{ref_id}{ext}"
            if p.exists(): ref_path = str(p); break

    job_id      = str(uuid.uuid4())[:8]
    output_path = OUTPUT_DIR / f"{job_id}_master.wav"
    jobs[job_id] = {"status": "queued", "log": [], "mode": mode}

    threading.Thread(
        target=processar_job,
        args=(job_id, str(input_path), mode, params, ref_path, str(output_path)),
        daemon=True
    ).start()

    return jsonify({"job_id": job_id})

@app.route("/status/<job_id>")
def status(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job não encontrado"}), 404
    return jsonify(jobs[job_id])

@app.route("/download/<job_id>")
def download(job_id):
    if job_id not in jobs or jobs[job_id]["status"] != "done":
        return jsonify({"error": "Arquivo não pronto"}), 404
    return send_file(
        jobs[job_id]["output"],
        as_attachment=True,
        download_name=f"master_{job_id}.wav",
        mimetype="audio/wav"
    )

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
            detalhes = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()
            detalhes = detalhes[-1500:] if detalhes else f"Codigo de saida {result.returncode}, sem mensagem"
            raise RuntimeError(detalhes)

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


if __name__ == "__main__":
    reload = "--reload" in sys.argv
    print("🎵 MasterAI Pro — http://localhost:5000")
    if reload:
        print("   Auto-reload ativo")
    app.run(debug=reload, port=5000, use_reloader=reload)
