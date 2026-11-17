/* Aplica a aparência salva antes da primeira pintura, sem depender do app.js. */
(function () {
  try {
    var raw = localStorage.getItem('financas-aparencia');
    if (!raw) return;
    var pref = JSON.parse(raw);
    var raiz = document.documentElement;
    if (pref.tema) raiz.setAttribute('data-theme', pref.tema);
    if (pref.fonte) raiz.setAttribute('data-font', pref.fonte);
    if (pref.destaque) raiz.setAttribute('data-accent', pref.destaque);
    if (pref.movimento) raiz.setAttribute('data-motion', pref.movimento);
  } catch (e) {
    /* preferência corrompida: segue com o padrão */
  }
})();
