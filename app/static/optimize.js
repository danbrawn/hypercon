const form = document.getElementById('opt-form');
const runBtn = document.getElementById('run');

runBtn.addEventListener('click', e => {
  e.preventDefault();
  const formData = new FormData(form);
  fetch(form.action, {
    method: 'POST',
    body: formData,
    credentials: 'same-origin'
  })
    .then(r => {
      if (!r.ok) return r.text().then(t => { throw new Error(t || r.status); });
      return r.json();
    })
    .then(showResult)
    .catch(err => {
      console.error('Optimization error', err);
      alert('Грешка при оптимизацията.');
    });
});

function showResult(res) {
  const result = document.getElementById('result');
  result.classList.remove('d-none');

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
