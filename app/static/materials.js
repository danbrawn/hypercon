const selAll = document.getElementById('select-all-rows');
const unselAll = document.getElementById('unselect-all-rows');
if (selAll && unselAll) {
  selAll.addEventListener('click', () => {
    document.querySelectorAll('.row-chk').forEach(chk => { chk.checked = true; });
  });
  unselAll.addEventListener('click', () => {
    document.querySelectorAll('.row-chk').forEach(chk => { chk.checked = false; });
  });
}
