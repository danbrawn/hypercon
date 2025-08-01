const selectAllBtn = document.getElementById('mat-select-all');
const unselectAllBtn = document.getElementById('mat-unselect-all');

if (selectAllBtn && unselectAllBtn) {
  selectAllBtn.addEventListener('click', () => {
    document.querySelectorAll('.row-chk').forEach(c => (c.checked = true));
  });
  unselectAllBtn.addEventListener('click', () => {
    document.querySelectorAll('.row-chk').forEach(c => (c.checked = false));
  });
}
