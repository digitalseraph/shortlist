// Location inputs on the settings page: add/remove rows, and fill the shared
// #place-options datalist with suggestions as you type.
let placeTimer;

document.addEventListener("input", (e) => {
  if (!e.target.matches('input[list="place-options"]')) return;
  clearTimeout(placeTimer);
  placeTimer = setTimeout(async () => {
    const r = await fetch("/places?q=" + encodeURIComponent(e.target.value));
    // Keep only <option> elements from the response; nothing else is inserted.
    const doc = new DOMParser().parseFromString(await r.text(), "text/html");
    document.getElementById("place-options").replaceChildren(...doc.querySelectorAll("option"));
  }, 200);
});

document.addEventListener("click", (e) => {
  const add = e.target.closest("[data-add-location]");
  if (add) {
    const list = add.previousElementSibling;
    const row = list.querySelector(".location-row").cloneNode(true);
    row.querySelector("input").value = "";
    list.append(row);
    row.querySelector("input").focus();
    return;
  }
  const remove = e.target.closest("[data-remove-location]");
  if (remove) {
    const row = remove.closest(".location-row");
    // Keep one row so there is always somewhere to type.
    if (row.parentElement.children.length > 1) row.remove();
    else row.querySelector("input").value = "";
  }
});
