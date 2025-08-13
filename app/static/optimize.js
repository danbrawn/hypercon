const form = document.getElementById('opt-form');
const runBtn = document.getElementById('run');
const stopBtn = document.getElementById('stop');
const spinner = document.getElementById('spinner');
const resultDiv = document.getElementById('result');
const materials = JSON.parse(document.getElementById('materials-data').value);
const addConstrBtn = document.getElementById('add-constr');
const constrBody = document.getElementById('constraints-body');
const selectAllBtn = document.getElementById('select-all');
const unselectAllBtn = document.getElementById('unselect-all');
const estSpan = document.getElementById('est-time');
const elapsedSpan = document.getElementById('elapsed-time');
const elapsedWrap = document.getElementById('elapsed-wrap');
const remainingSpan = document.getElementById('remaining-time');
const remainingWrap = document.getElementById('remaining-wrap');
const csrfToken = form.querySelector('input[name="csrf_token"]').value;
let timer = null;
let poller = null;
let start = null;
let estSeconds = 0;
let estCombos = 0;

// Initial guess for how long each combination takes. A more accurate
// estimate will be computed from real progress once the backend starts
// reporting work done.
const SECONDS_PER_COMBO = 0.12;

// prevent form submission when pressing Enter
form.addEventListener('submit', e => e.preventDefault());

function getSelectedIds() {
  return Array.from(document.querySelectorAll('.use-chk:checked')).map(c =>
    parseInt(c.value)
  );
}

function nCr(n, r) {
  if (r > n) return 0;
  let res = 1;
  for (let i = 1; i <= r; i++) {
    res = (res * (n - r + i)) / i;
  }
  return res;
}

function formatDuration(sec) {
  const s = Math.round(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rem = s % 60;
  const parts = [];
  if (h) parts.push(`${h}h`);
  if (m || h) parts.push(`${m}m`);
  parts.push(`${rem}s`);
  return parts.join(' ');
}

function updateEstimate() {
  const n = getSelectedIds().length;
  estCombos = 0;
  for (let r = 1; r <= n; r++) {
    estCombos += nCr(n, r);
  }
  estSeconds = estCombos * SECONDS_PER_COMBO;
  estSpan.textContent = `${formatDuration(estSeconds)} (${estCombos} combos)`;
}

function updateConstraintOptions() {
  const ids = getSelectedIds();
  const rows = Array.from(constrBody.querySelectorAll('tr'));
  rows.forEach(row => {
    const sel = row.querySelector('.con-mat');
    const current = parseInt(sel.value);
    // remove options for unchecked materials
    Array.from(sel.options).forEach(o => {
      const val = parseInt(o.value);
      if (!ids.includes(val)) {
        if (val === current) {
          row.remove();
        }
        o.remove();
      }
    });
    // add options for newly checked materials
    ids.forEach(id => {
      if (!sel.querySelector(`option[value="${id}"]`)) {
        const m = materials.find(mm => mm.id === id);
        if (m) {
          const opt = document.createElement('option');
          opt.value = id;
          opt.textContent = m.name;
          sel.appendChild(opt);
        }
      }
    });
    if (!sel.options.length) {
      row.remove();
    } else if (!ids.includes(current)) {
      sel.value = sel.options[0].value;
    }
  });
  updateEstimate();
}

document.querySelectorAll('.use-chk').forEach(chk =>
  chk.addEventListener('change', updateConstraintOptions)
);

if (selectAllBtn && unselectAllBtn) {
  selectAllBtn.addEventListener('click', () => {
    document.querySelectorAll('.use-chk').forEach(c => (c.checked = true));
    updateConstraintOptions();
  });
  unselectAllBtn.addEventListener('click', () => {
    document.querySelectorAll('.use-chk').forEach(c => (c.checked = false));
    updateConstraintOptions();
  });
}

// initial setup
updateConstraintOptions();

addConstrBtn.addEventListener('click', () => {
  const ids = getSelectedIds();
  if (!ids.length) {
    return;
  }
  const tr = document.createElement('tr');
  const td1 = document.createElement('td');
  const sel = document.createElement('select');
  sel.className = 'con-mat';
  ids.forEach(id => {
    const m = materials.find(mm => mm.id === id);
    if (m) {
      const o = document.createElement('option');
      o.value = id;
      o.textContent = m.name;
      sel.appendChild(o);
    }
  });
  td1.appendChild(sel);
  const td2 = document.createElement('td');
  const op = document.createElement('select');
  op.className = 'con-op';
  ['>','<','='].forEach(s => {
    const opt = document.createElement('option');
    opt.value = s;
    opt.textContent = s;
    op.appendChild(opt);
  });
  td2.appendChild(op);
  const td3 = document.createElement('td');
  const val = document.createElement('input');
  val.type = 'number';
  val.min = '0';
  val.max = '1';
  val.step = 'any';
  val.className = 'con-val';
  td3.appendChild(val);
  tr.appendChild(td1);
  tr.appendChild(td2);
  tr.appendChild(td3);
  constrBody.appendChild(tr);
});

runBtn.addEventListener('click', e => {
  e.preventDefault();
  const formData = new FormData();
  formData.append('csrf_token', csrfToken);
  const ids = getSelectedIds();
  const constr = Array.from(constrBody.querySelectorAll('tr')).map(tr => ({
    id: parseInt(tr.querySelector('.con-mat').value),
    op: tr.querySelector('.con-op').value,
    val: parseFloat(tr.querySelector('.con-val').value || 0)
  }));
  formData.append('materials', JSON.stringify(ids));
  formData.append('constraints', JSON.stringify(constr));
  runBtn.disabled = true;
  stopBtn.classList.remove('d-none');
  resultDiv.classList.add('d-none');
  spinner.classList.remove('d-none');
  elapsedWrap.classList.remove('d-none');
  remainingWrap.classList.remove('d-none');
  start = Date.now();
  elapsedSpan.textContent = '0s';
  remainingSpan.textContent = formatDuration(estSeconds);
  timer = setInterval(() => {
    const secs = (Date.now() - start) / 1000;
    elapsedSpan.textContent = formatDuration(secs);
  }, 1000);
  fetch(form.action, {
    method: 'POST',
    body: formData,
    credentials: 'same-origin'
  })
    .then(async r => {
      const txt = await r.text();
      let data;
      try {
        data = JSON.parse(txt);
      } catch (e) {
        if (!r.ok) {
          throw new Error(`Server error ${r.status}`);
        }
        throw new Error('Invalid response');
      }
      if (!r.ok && r.status !== 202) {
        throw new Error(data.error || `Server error ${r.status}`);
      }
      checkStatus();
      poller = setInterval(checkStatus, 2000);
    })
    .catch(err => {
      console.error('Optimization error', err);
      alert(err.message || 'Optimization error.');
      finalize();
    });
});

function checkStatus() {
  fetch(form.action.replace('run', 'status'), { credentials: 'same-origin' })
    .then(r => r.json())
    .then(data => {
      if (typeof data.elapsed === 'number') {
        elapsedSpan.textContent = formatDuration(data.elapsed);
        start = Date.now() - data.elapsed * 1000;
      }
      if (typeof data.progress === 'number' && data.progress > 0) {
        const total = data.elapsed / data.progress;
        estSpan.textContent = `${formatDuration(total)} (${estCombos} combos)`;
        const remaining = total - data.elapsed;
        if (!isNaN(remaining) && remaining >= 0) {
          remainingSpan.textContent = formatDuration(remaining);
        }
      }
      if (data.status === 'running') {
        return;
      }
      if (data.status === 'done') {
        showResult(data.result);
      } else if (data.status === 'error') {
        alert('Optimization error');
      }
      finalize();
    })
    .catch(err => {
      console.error('Status error', err);
    });
}

function finalize() {
  spinner.classList.add('d-none');
  runBtn.disabled = false;
  stopBtn.classList.add('d-none');
  remainingWrap.classList.add('d-none');
  if (timer) clearInterval(timer);
  if (poller) clearInterval(poller);
}

stopBtn.addEventListener('click', () => {
  fetch(form.action.replace('run', 'stop'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `csrf_token=${encodeURIComponent(csrfToken)}`,
    credentials: 'same-origin'
  })
    .then(r => r.json())
    .then(data => {
      if (data.result) {
        showResult(data.result);
      }
      finalize();
    })
    .catch(err => {
      console.error('Stop error', err);
      alert('Failed to stop optimization');
      finalize();
    });
});

function showResult(res) {
  // some backends may wrap or stringify the payload inside a `result` field
  if (res && res.result !== undefined) {
    if (typeof res.result === 'string') {
      try {
        res = JSON.parse(res.result);
      } catch (e) {
        console.error('Failed to parse result string', e, res.result);
        alert('Invalid optimization response.');
        return;
      }
    } else if (res.result && typeof res.result === 'object') {
      res = res.result;
    }
  }
  if (!res || !Array.isArray(res.material_ids) || !Array.isArray(res.weights)) {
    alert(res && res.error ? res.error : 'Invalid optimization response.');
    console.error('Invalid response', res);
    return;
  }

  resultDiv.classList.remove('d-none');

  document.getElementById('best-mse').textContent = `Best MSE: ${res.best_mse}`;
  const tbody = document.getElementById('weights-body');
  tbody.innerHTML = '';
  res.material_ids.forEach((id, i) => {
    const row = document.createElement('tr');
    row.innerHTML = `<td>${id}</td><td>${(res.weights[i] * 100).toFixed(2)}%</td>`;
    tbody.appendChild(row);
  });

  if (window.Chart) {
    new Chart(document.getElementById('chart'), {
      type: 'line',
      data: {
        labels: res.prop_columns,
        datasets: [
          { label: 'Target', data: res.target_profile, borderColor: 'red', fill: false },
          { label: 'Mixed', data: res.mixed_profile, borderColor: 'blue', fill: false }
        ]
      }
    });
  } else {
    console.error('Chart.js not loaded');
  }
}
