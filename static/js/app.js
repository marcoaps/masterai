// masterai — frontend
// Fala direto com as rotas reais do app.py: /upload, /master, /separar, /status/<job_id>, /download/<job_id>, /download_stems/<job_id>

const state = {
  fileId: null,
  refId: null,
  mode: 'suno',   // modo enviado ao app.py: 'suno', 'auto' (padrão) ou 'reference'
  preset: 'suno', // escolha do botão "Tipo de master" (vale quando a referência está desligada)
  lufs: -14,      // volume final
  intens: 'normal', // intensidade do modo Suno
  jobId: null,
  polling: null,
};

const el = {
  dropzone: document.getElementById('dropzone'),
  fileInput: document.getElementById('file-input'),
  dzTitle: document.getElementById('dz-title'),
  refDropzone: document.getElementById('ref-dropzone'),
  refInput: document.getElementById('ref-input'),
  refTitle: document.getElementById('ref-title'),
  referenceZone: document.getElementById('reference-zone'),
  modeSwitch: document.getElementById('mode-switch'),
  labelStandard: document.getElementById('label-standard'),
  labelReference: document.getElementById('label-reference'),
  btnMaster: document.getElementById('btn-master'),
  progress: document.getElementById('progress'),
  progressStatus: document.getElementById('progress-status'),
  progressLog: document.getElementById('progress-log'),
  btnDownload: document.getElementById('btn-download'),
  tabMaster: document.getElementById('tab-master'),
  tabStems: document.getElementById('tab-stems'),
  panelMaster: document.getElementById('panel-master'),
  panelStems: document.getElementById('panel-stems'),
};

// ── Abas ──────────────────────────────────────────────
el.tabMaster.addEventListener('click', () => switchTab('master'));
el.tabStems.addEventListener('click', () => switchTab('stems'));

function switchTab(tab) {
  const isMaster = tab === 'master';
  el.tabMaster.classList.toggle('active', isMaster);
  el.tabStems.classList.toggle('active', !isMaster);
  el.panelMaster.classList.toggle('hidden', !isMaster);
  el.panelStems.classList.toggle('hidden', isMaster);
}

// ── Toggle padrão / referência ───────────────────────
el.modeSwitch.addEventListener('click', () => {
  const on = el.modeSwitch.classList.toggle('on');
  el.labelStandard.classList.toggle('on', !on);
  el.labelReference.classList.toggle('on', on);
  el.referenceZone.classList.toggle('hidden', !on);
  state.mode = on ? 'reference' : state.preset;
  document.getElementById('opcoes-master').querySelector('.opcao').classList.toggle('desligado', on);
});

// ── Tipo de master e volume final ────────────────────
const DICAS = {
  suno: 'Limpa o que a IA estraga: tira o embolado do grave, define o baixo e amacia o agudo metálico.',
  auto: 'Master "pesada": realça graves e brilho e empurra o volume. Melhor para mixagens gravadas.',
};
function ligarSeg(id, aoEscolher) {
  const seg = document.getElementById(id);
  seg.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    seg.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    aoEscolher(b);
  }));
}
ligarSeg('seg-preset', b => {
  state.preset = b.dataset.mode;
  if (state.mode !== 'reference') state.mode = state.preset;
  document.getElementById('dica-preset').textContent = DICAS[state.preset];
  document.getElementById('opcao-intensidade').classList.toggle('hidden', state.preset !== 'suno');
});
ligarSeg('seg-intens', b => { state.intens = b.dataset.intens; });
ligarSeg('seg-lufs', b => { state.lufs = Number(b.dataset.lufs); });

// ── Upload do arquivo principal ──────────────────────
['dragover', 'dragenter'].forEach(evt =>
  el.dropzone.addEventListener(evt, e => { e.preventDefault(); el.dropzone.classList.add('drag'); })
);
['dragleave', 'drop'].forEach(evt =>
  el.dropzone.addEventListener(evt, e => { e.preventDefault(); el.dropzone.classList.remove('drag'); })
);
el.dropzone.addEventListener('drop', e => {
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file, 'main');
});
el.fileInput.addEventListener('change', e => {
  const file = e.target.files[0];
  if (file) uploadFile(file, 'main');
});

// ── Upload da faixa de referência ────────────────────
el.refDropzone.addEventListener('drop', e => {
  e.preventDefault();
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file, 'ref');
});
el.refInput.addEventListener('change', e => {
  const file = e.target.files[0];
  if (file) uploadFile(file, 'ref');
});

async function uploadFile(file, kind) {
  const target = kind === 'main' ? el.dzTitle : el.refTitle;
  const original = target.textContent;
  target.textContent = 'Enviando…';

  try {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/upload', { method: 'POST', body: formData });
    if (!res.ok) throw new Error('Falha no upload');
    const data = await res.json();

    target.textContent = file.name;

    if (kind === 'main') {
      state.fileId = data.file_id;
      el.btnMaster.classList.remove('hidden');
    } else {
      state.refId = data.file_id;
    }
  } catch (err) {
    console.error('Erro no upload:', err);
    target.textContent = original;
    alert('Não foi possível enviar o arquivo. Tente novamente.');
  }
}

// ── Disparar masterização ────────────────────────────
el.btnMaster.addEventListener('click', startMaster);

async function startMaster() {
  if (!state.fileId) return;

  el.btnMaster.disabled = true;
  el.progress.classList.remove('hidden');
  el.btnDownload.classList.add('hidden');
  el.progressStatus.textContent = 'Enviando para processamento…';
  el.progressLog.innerHTML = '';

  const body = {
    file_id: state.fileId,
    mode: state.mode,
    // params fica vazio por enquanto — é aqui que entram os macro controles
    // (Loudness, Width, Bass, Air, Presence, Harshness) quando essa fase for implementada.
    // As chaves precisam bater com o que processar_job() espera no app.py.
    params: { lufs: state.lufs, intensidade: state.intens },
  };
  if (state.mode === 'reference' && state.refId) {
    body.ref_id = state.refId;
  }

  try {
    const res = await fetch('/master', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error('Falha ao iniciar masterização');
    const data = await res.json();
    state.jobId = data.job_id;
    pollStatus();
  } catch (err) {
    console.error('Erro ao iniciar masterização:', err);
    el.progressStatus.textContent = 'Erro ao iniciar. Tente novamente.';
    el.btnMaster.disabled = false;
  }
}

function pollStatus() {
  if (state.polling) clearInterval(state.polling);
  let falhas = 0;
  document.getElementById('comparar').classList.add('hidden');

  state.polling = setInterval(async () => {
    try {
      const res = await fetch(`/status/${state.jobId}`);
      if (!res.ok) throw new Error('Job não encontrado');
      falhas = 0;
      const job = await res.json();

      el.progressStatus.textContent = statusLabel(job.status);
      if (Array.isArray(job.log)) {
        el.progressLog.innerHTML = job.log.map(line => `<div>${line}</div>`).join('');
        el.progressLog.scrollTop = el.progressLog.scrollHeight;
      }

      if (job.status === 'done') {
        clearInterval(state.polling);
        el.btnDownload.href = `/download/${state.jobId}`;
        el.btnDownload.classList.remove('hidden');
        mostrarComparador(state.jobId, job);
        el.btnMaster.disabled = false;
      } else if (job.status === 'error') {
        clearInterval(state.polling);
        el.progressStatus.textContent = `Erro: ${job.error || 'falha no processamento'}`;
        el.btnMaster.disabled = false;
      }
    } catch (err) {
      // uma falha isolada não derruba o acompanhamento; só desiste depois de ~10 s seguidos
      falhas += 1;
      console.warn('Falha ao consultar status:', err);
      if (falhas < 8) return;
      clearInterval(state.polling);
      el.progressStatus.textContent = 'Perdemos a conexão com o MasterAI. Veja se a janela preta ainda está aberta e tente de novo.';
      el.btnMaster.disabled = false;
    }
  }, 1200);
}

// ── Comparador antes/depois ──────────────────────────
function mostrarComparador(jobId, job) {
  const box = document.getElementById('comparar');
  const player = document.getElementById('player');
  const a = job.analise_antes || {}, d = job.analise_depois || {};
  const fmt = v => (typeof v === 'number' ? v.toFixed(1) : '–');
  document.getElementById('comparar-numeros').innerHTML =
    `Volume: <b>${fmt(a.lufs)} LUFS</b> → <b>${fmt(d.lufs)} LUFS</b> · Pico: <b>${fmt(a.peak)}</b> → <b>${fmt(d.peak)} dBFS</b>`;
  const fontes = { master: `/ouvir/${jobId}`, original: `/original/${jobId}` };
  const difDb = (typeof a.lufs === 'number' && typeof d.lufs === 'number') ? d.lufs - a.lufs : 0;
  let atual = 'master';
  function volumeDe(qual) {
    if (!document.getElementById('igualar').checked) return 1;
    // abaixa a versão mais alta para ficarem com o mesmo volume percebido
    const ganho = qual === 'master' ? Math.min(0, -difDb) : Math.min(0, difDb);
    return Math.pow(10, ganho / 20);
  }
  function tocar(qual) {
    const t = player.currentTime || 0, tocando = !player.paused;
    atual = qual;
    player.src = fontes[qual];
    player.volume = volumeDe(qual);
    player.addEventListener('loadedmetadata', function voltar() {
      player.removeEventListener('loadedmetadata', voltar);
      player.currentTime = Math.min(t, player.duration || t);
      if (tocando) player.play();
    });
  }
  const seg = document.getElementById('seg-ab');
  seg.querySelectorAll('button').forEach(b => {
    b.classList.toggle('on', b.dataset.ab === 'master');
    b.onclick = () => { seg.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); tocar(b.dataset.ab); };
  });
  document.getElementById('igualar').onchange = () => { player.volume = volumeDe(atual); };
  player.src = fontes.master;
  player.volume = volumeDe('master');
  box.classList.remove('hidden');
}

function statusLabel(status) {
  switch (status) {
    case 'queued': return 'Na fila…';
    case 'processing': return 'Processando…';
    case 'done': return 'Pronto!';
    case 'error': return 'Erro no processamento';
    default: return status;
  }
}

// ── Separador de stems ───────────────────────────────
const stems = {
  fileId: null,
  jobId: null,
  polling: null,
  dropzone: document.getElementById('stems-dropzone'),
  input: document.getElementById('stems-input'),
  title: document.getElementById('stems-title'),
  btn: document.getElementById('btn-stems'),
  progress: document.getElementById('stems-progress'),
  status: document.getElementById('stems-status'),
  log: document.getElementById('stems-log'),
  download: document.getElementById('btn-stems-download'),
};

['dragover', 'dragenter'].forEach(evt =>
  stems.dropzone.addEventListener(evt, e => { e.preventDefault(); stems.dropzone.classList.add('drag'); })
);
['dragleave', 'drop'].forEach(evt =>
  stems.dropzone.addEventListener(evt, e => { e.preventDefault(); stems.dropzone.classList.remove('drag'); })
);
stems.dropzone.addEventListener('drop', e => {
  const file = e.dataTransfer.files[0];
  if (file) uploadStems(file);
});
stems.input.addEventListener('change', e => {
  const file = e.target.files[0];
  if (file) uploadStems(file);
});

async function uploadStems(file) {
  const original = stems.title.textContent;
  stems.title.textContent = 'Enviando…';
  try {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/upload', { method: 'POST', body: formData });
    if (!res.ok) throw new Error('Falha no upload');
    const data = await res.json();
    stems.fileId = data.file_id;
    stems.title.textContent = file.name;
    stems.btn.classList.remove('hidden');
  } catch (err) {
    console.error('Erro no upload:', err);
    stems.title.textContent = original;
    alert('Não foi possível enviar o arquivo. Tente novamente.');
  }
}

stems.btn.addEventListener('click', async () => {
  if (!stems.fileId) return;
  stems.btn.disabled = true;
  stems.progress.classList.remove('hidden');
  stems.download.classList.add('hidden');
  stems.status.textContent = 'Enviando para separação…';
  stems.log.innerHTML = '';
  try {
    const res = await fetch('/separar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: stems.fileId }),
    });
    if (!res.ok) throw new Error('Falha ao iniciar a separação');
    const data = await res.json();
    stems.jobId = data.job_id;
    pollStems();
  } catch (err) {
    console.error(err);
    stems.status.textContent = 'Erro ao iniciar. Tente novamente.';
    stems.btn.disabled = false;
  }
});

function pollStems() {
  if (stems.polling) clearInterval(stems.polling);
  let falhas = 0;
  stems.polling = setInterval(async () => {
    try {
      const res = await fetch(`/status/${stems.jobId}`);
      if (!res.ok) throw new Error('Job não encontrado');
      const job = await res.json();
      falhas = 0;
      stems.status.textContent = statusLabel(job.status);
      if (Array.isArray(job.log)) {
        stems.log.innerHTML = '';
        job.log.forEach(line => {
          const div = document.createElement('div');
          div.textContent = line;
          stems.log.appendChild(div);
        });
        stems.log.scrollTop = stems.log.scrollHeight;
      }
      if (job.status === 'done') {
        clearInterval(stems.polling);
        stems.download.href = `/download_stems/${stems.jobId}`;
        stems.download.classList.remove('hidden');
        stems.btn.disabled = false;
      } else if (job.status === 'error') {
        clearInterval(stems.polling);
        stems.status.textContent = `Erro: ${job.error || 'falha na separação'}`;
        stems.btn.disabled = false;
      }
    } catch (err) {
      // A separação é longa: tolera algumas falhas de rede antes de desistir.
      if (++falhas >= 5) {
        clearInterval(stems.polling);
        stems.status.textContent = 'Perdemos a conexão com o job. Tente novamente.';
        stems.btn.disabled = false;
      }
    }
  }, 2000);
}
