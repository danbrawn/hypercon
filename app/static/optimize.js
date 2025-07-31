const form = document.getElementById('opt-form');
const runBtn = document.getElementById('run');
const spinner = document.getElementById('spinner');
const resultDiv = document.getElementById('result');
const materials = JSON.parse(document.getElementById('materials-data').textContent);
const addConstrBtn = document.getElementById('add-constr');
const constrBody = document.getElementById('constraints-body');

addConstrBtn.addEventListener('click', () => {
  const tr = document.createElement('tr');
  const td1 = document.createElement('td');
  const sel = document.createElement('select');
  sel.className = 'con-mat';
  materials.forEach(m => {
    const o = document.createElement('option');
    o.value = m.id;
    o.textContent = m.name;
    sel.appendChild(o);
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
  const ids = Array.from(document.querySelectorAll('.use-chk:checked')).map(c => parseInt(c.value));
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
    .then(showResult)
    .catch(err => {
      console.error('Optimization error', err);
      alert(err.message || 'Грешка при оптимизацията.');

    })
    .finally(() => {
      spinner.classList.add('d-none');
      runBtn.disabled = false;
    });
});

function showResult(res) {
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
