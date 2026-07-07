// masterai — frontend
// Fala direto com as rotas reais do app.py: /upload, /master, /status/<job_id>, /download/<job_id>

const state = {
  fileId: null,
  refId: null,
  mode: 'auto', // 'auto' = padrão, 'reference' = com faixa de referência
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
  state.mode = on ? 'reference' : 'auto';
});

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
    params: {},
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

  state.polling = setInterval(async () => {
    try {
      const res = await fetch(`/status/${state.jobId}`);
      if (!res.ok) throw new Error('Job não encontrado');
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
        el.btnMaster.disabled = false;
      } else if (job.status === 'error') {
        clearInterval(state.polling);
        el.progressStatus.textContent = `Erro: ${job.error || 'falha no processamento'}`;
        el.btnMaster.disabled = false;
      }
    } catch (err) {
      console.error('Erro ao consultar status:', err);
      clearInterval(state.polling);
      el.progressStatus.textContent = 'Perdemos a conexão com o job. Tente novamente.';
      el.btnMaster.disabled = false;
    }
  }, 1200);
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
