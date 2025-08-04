const form = document.getElementById('opt-form');
const runBtn = document.getElementById('run');
const spinner = document.getElementById('spinner');
const resultDiv = document.getElementById('result');
const materials = JSON.parse(document.getElementById('materials-data').textContent);
const addConstrBtn = document.getElementById('add-constr');
const constrBody = document.getElementById('constraints-body');
const selectAllBtn = document.getElementById('select-all');
const unselectAllBtn = document.getElementById('unselect-all');

// prevent form submission when pressing Enter
form.addEventListener('submit', e => e.preventDefault());

function getSelectedIds() {
  return Array.from(document.querySelectorAll('.use-chk:checked')).map(c =>
    parseInt(c.value)
  );
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
  formData.append('csrf_token', form.querySelector('input[name="csrf_token"]').value);
  const ids = getSelectedIds();
  const constr = Array.from(constrBody.querySelectorAll('tr')).map(tr => ({
    id: parseInt(tr.querySelector('.con-mat').value),
    op: tr.querySelector('.con-op').value,
    val: parseFloat(tr.querySelector('.con-val').value || 0)
  }));
  formData.append('materials', JSON.stringify(ids));
  formData.append('constraints', JSON.stringify(constr));
  runBtn.disabled = true;
  resultDiv.classList.add('d-none');
  spinner.classList.remove('d-none');
  fetch(form.action, {
    method: 'POST',
    body: formData,
    credentials: 'same-origin'
  })
    .then(r =>
      r
        .json()
        .then(data => {
          if (!r.ok || data.error) {
            throw new Error(data.error || r.status);
          }
          return data;
        })
    )
    .then(data => {
      if (data.job_id) {
        pollProgress(data.job_id);
      } else {
        showResult(data);
        spinner.classList.add('d-none');
        runBtn.disabled = false;
      }
    })
    .catch(err => {
      console.error('Optimization error', err);
      alert(err.message || 'Optimization error.');
      spinner.classList.add('d-none');
      runBtn.disabled = false;
    });
});

function pollProgress(jobId) {
  fetch(`/optimize/progress?job_id=${jobId}`, { credentials: 'same-origin' })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        throw new Error(data.error);
      }
      if (data.total === 0 && data.done === 0) {
        setTimeout(() => pollProgress(jobId), 500);
        return;
      }
      if (data.done < data.total || !data.result) {
        setTimeout(() => pollProgress(jobId), 500);
        return;
      }
      showResult(data.result);
      spinner.classList.add('d-none');
      runBtn.disabled = false;
    })
    .catch(err => {
      console.error('Optimization error', err);
      alert(err.message || 'Optimization error.');
      spinner.classList.add('d-none');
      runBtn.disabled = false;
    });
}

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
