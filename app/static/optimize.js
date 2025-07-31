const form = document.getElementById('opt-form');
const runBtn = document.getElementById('run');
const spinner = document.getElementById('spinner');
const resultDiv = document.getElementById('result');

runBtn.addEventListener('click', e => {
  e.preventDefault();
  const formData = new FormData(form);
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
