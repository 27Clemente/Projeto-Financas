'use strict';

/* utilitários */

const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const num = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 });
const $ = (sel) => document.querySelector(sel);

/* ícones svg locais */
const ICON_BANK = '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 10 12 4l9 6M5 10v9M9 10v9M15 10v9M19 10v9M3 20h18"/></svg>';
const ICON_WARN = '<svg class="ico ico-sm" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 2 21h20L12 3ZM12 9v5M12 17h.01"/></svg>';
const ICON_SYNC = '<svg class="ico ico-sm" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6"/></svg>';

/* Erros conhecidos do Pluggy (codeDescription) → mensagem em português. */
const ERROR_PT = {
  ITEM_USER_ALREADY_EXISTS:
    'Essa conta já está conectada a este app — use "Sincronizar" em Conexões para atualizar.',
  ITEM_CREATION_LIMIT_EXCEEDED:
    'Você atingiu o limite de conexões do seu plano no Pluggy. Apague conexões antigas em Conexões ou faça upgrade no dashboard.',
  TRIAL_CLIENT_ITEM_CREATE_NOT_ALLOWED:
    'No modo teste só dá para conectar Pluggy Bank e MeuPluggy. Crie uma aplicação em Produção no dashboard do Pluggy.',
  CONNECTOR_OFFLINE:
    'A instituição está fora do ar neste momento. Tente de novo mais tarde (status.pluggy.ai).',
  TOO_MANY_CONSECUTIVE_LOGIN_FAILURES:
    'Muitas tentativas de login: o banco pediu uma espera. Tente de novo mais tarde.',
  ITEM_IN_ERROR_COOLDOWN:
    'Essa conexão falhou recentemente e está em espera. Tente mais tarde.',
  LOGIN_ERROR: 'O banco recusou o login. Confira usuário, senha e token MFA.',
  ITEM_ALREADY_UPDATING: 'Essa conexão já está sincronizando. Aguarde terminar.',
  CLIENT_KEYS_UNAUTHORIZED: 'Credenciais do Pluggy inválidas — confira o arquivo .env.',
  NOT_CONFIGURED: 'Credenciais do Pluggy não configuradas — preencha o arquivo .env.',
  NOT_FOUND: 'Conexão não encontrada no Pluggy. Ela pode ter sido removida no dashboard.',
  NETWORK: 'Sem conexão com a API do Pluggy. Verifique sua internet.',
};

/* erro do Pluggy → texto em português */
function ptError(err) {
  if (!err) return 'Erro desconhecido ao falar com o banco.';
  const code = typeof err.codeDescription === 'string' ? err.codeDescription : err.errorCode;
  if (code && ERROR_PT[code]) return ERROR_PT[code];
  const msg = String(err.message || err.error || '').trim();
  if (/same credentials|already exists|j[áa] existe/i.test(msg)) return ERROR_PT.ITEM_USER_ALREADY_EXISTS;
  if (!msg) return 'Erro desconhecido ao falar com o banco.';
  return code ? `${msg} [${code}]` : msg;
}

const esc = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );

const MONTHS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function monthLabel(m) {
  const [y, mo] = String(m).split('-');
  return `${MONTHS[Number(mo) - 1] || mo}/${y}`;
}

function fmtDate(iso) {
  return iso ? String(iso).slice(0, 10).split('-').reverse().join('/') : '—';
}

function fmtDateTime(iso) {
  if (!iso) return 'nunca';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

const CATS = {
  'Transfer': 'Transferência', 'Transfer between accounts': 'Transferência entre contas',
  'Money transfer': 'Transferência', 'Salary': 'Salário', 'Investment': 'Investimento',
  'Fixed Income Investment': 'Renda fixa', 'Interest': 'Rendimentos', 'Refund': 'Estorno',
  'Video streaming': 'Streaming', 'Subscription': 'Assinatura', 'Food': 'Alimentação',
  'Restaurant': 'Restaurante', 'Groceries': 'Mercado', 'Supermarket': 'Mercado',
  'Transport': 'Transporte', 'Fuel': 'Combustível', 'Health': 'Saúde', 'Pharmacy': 'Farmácia',
  'Education': 'Educação', 'Travel': 'Viagem', 'Shopping': 'Compras', 'Utilities': 'Contas de casa',
  'Rent': 'Aluguel', 'Taxes': 'Impostos', 'Insurance': 'Seguro', 'Loan': 'Empréstimo',
  'Credit Card Payment': 'Pagamento de fatura', 'ATM': 'Saque', 'Cash Withdrawn': 'Saque',
  'Digital Purchase': 'Compra online', 'Entertainment': 'Lazer', 'Games': 'Jogos',
  'Clothing': 'Roupa', 'Beauty': 'Beleza', 'Pets': 'Animais', 'Gift': 'Presente',
  'Donation': 'Doação', 'Fees': 'Taxas', 'Cashback': 'Cashback',
};

const INV_TYPES = {
  FIXED_INCOME: 'Renda fixa', MUTUAL_FUND: 'Fundo', EQUITY: 'Ações/FII', ETF: 'ETF',
  SECURITY: 'Previdência', COE: 'COE', OTHER: 'Outro',
};

function catLabel(c) {
  c = String(c || '').trim();
  if (!c) return 'Sem categoria';
  return CATS[c] || c;
}

// Open Finance não informa amountProfit; nesse caso usamos balance - amountOriginal.
function invProfit(inv) {
  if (inv.amount_profit != null) return inv.amount_profit;
  if (inv.amount_original != null) return inv.balance - inv.amount_original;
  return null;
}

async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, {
      method: opts.method || 'GET',
      headers: { 'Content-Type': 'application/json' },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new Error('Sem conexão com o servidor local. Ele está rodando? (python server/app.py)');
  }
  let data = {};
  try {
    data = await res.json();
  } catch {
    /* resposta sem JSON */
  }
  if (!res.ok) {
    const msg = String(data.error || data.message || '').trim();
    throw new Error(msg ? ptError({ message: msg, codeDescription: data.code }) : `Erro ${res.status}`);
  }
  return data;
}

/* aparência */

const CHAVE_APARENCIA = 'financas-aparencia';
const APARENCIA_PADRAO = { tema: 'claro', fonte: 'funnel', destaque: 'teal', movimento: 'on' };

function lerAparencia() {
  try {
    return { ...APARENCIA_PADRAO, ...JSON.parse(localStorage.getItem(CHAVE_APARENCIA) || '{}') };
  } catch {
    return { ...APARENCIA_PADRAO };
  }
}

let aparencia = lerAparencia();

function aplicarAparencia() {
  const raiz = document.documentElement;
  raiz.setAttribute('data-theme', aparencia.tema);
  raiz.setAttribute('data-font', aparencia.fonte);
  raiz.setAttribute('data-accent', aparencia.destaque);
  raiz.setAttribute('data-motion', aparencia.movimento);
}

function sincronizarOpcoes() {
  document.querySelectorAll('.options[data-group]').forEach((grupo) => {
    const chave = grupo.dataset.group;
    grupo.querySelectorAll('.option').forEach((opcao) => {
      opcao.setAttribute('aria-pressed', String(aparencia[chave] === opcao.dataset.value));
    });
  });
}

function salvarAparencia() {
  try {
    localStorage.setItem(CHAVE_APARENCIA, JSON.stringify(aparencia));
  } catch {
    /* sem localStorage: a escolha vale só nesta sessão */
  }
}

aplicarAparencia();
sincronizarOpcoes();

/* sandbox */

const CHAVE_SANDBOX = 'financas-sandbox';

function sandboxSalvo() {
  try {
    return localStorage.getItem(CHAVE_SANDBOX);
  } catch {
    return null;
  }
}

function sandboxHabilitado() {
  const salvo = sandboxSalvo();
  if (salvo === 'on') return true;
  if (salvo === 'off') return false;
  return Boolean(state.status && state.status.includeSandbox);
}

/* estado e chrome */

const state = {
  status: null,
  busy: false,
  tab: 'painel',
  filters: { month: '', type: '', category: '', q: '' },
  txOffset: 0,
  txTotal: 0,
};

let toastTimer;
function toast(msg, isError = false) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.toggle('error', isError);
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.hidden = true;
  }, 4500);
}

const busyButtons = ['#btn-sync-all', '#btn-connect', '#btn-connect-2'].map($);
function setBusy(busy) {
  state.busy = busy;
  $('#progress').hidden = !busy;
  busyButtons.forEach((b) => {
    if (b) b.disabled = busy;
  });
}

function renderBanner() {
  const banner = $('#banner');
  if (!state.status) {
    banner.hidden = true;
    return;
  }
  if (!state.status.configured) {
    banner.innerHTML =
      'Acesso aos bancos ainda não configurado — <b data-goto="conexoes">veja como configurar</b>.';
    banner.hidden = false;
    banner.querySelector('[data-goto]').onclick = () => showTab('conexoes');
  } else if (state.status.mode === 'development') {
    banner.innerHTML =
      'Aplicação do Pluggy em modo <b>desenvolvimento</b>: só conectores de teste aparecem. ' +
      'Para bancos reais, crie uma aplicação em Produção — <b data-goto="conexoes">como fazer</b>.';
    banner.hidden = false;
    banner.querySelector('[data-goto]').onclick = () => showTab('conexoes');
  } else if (state.status.items === 0) {
    banner.innerHTML = 'Nenhum banco conectado ainda — <b data-connect>conecte seu primeiro banco</b>.';
    banner.hidden = false;
    banner.querySelector('[data-connect]').onclick = connect;
  } else {
    banner.hidden = true;
  }
}

async function refreshStatus() {
  state.status = await api('/api/status');
  const chk = $('#chk-sandbox');
  if (chk && !sandboxSalvo()) chk.checked = Boolean(state.status.includeSandbox);
  renderBanner();
}

/* abas */

function showTab(name) {
  state.tab = name;
  document.querySelectorAll('.tab').forEach((t) => {
    t.classList.toggle('active', t.dataset.tab === name);
  });
  document.querySelectorAll('main > section').forEach((s) => {
    s.hidden = s.id !== `tab-${name}`;
  });
  renderTab(name).catch((e) => toast(e.message, true));
}

async function renderTab(name) {
  if (name === 'painel') await renderPainel();
  else if (name === 'gastos') await renderGastos();
  else if (name === 'investimentos') await renderInvestimentos();
  else if (name === 'conexoes') await renderConexoes();
  else if (name === 'aparencia') sincronizarOpcoes();
}

async function refreshData() {
  await refreshStatus().catch(() => {});
  await renderTab(state.tab).catch((e) => toast(e.message, true));
}

/* painel */

function txRow(tx) {
  const amountClass = tx.amount >= 0 ? 'pos' : 'neg';
  return `<div class="row">
    <span class="row-date">${fmtDate(tx.date)}</span>
    <div class="row-main">
      <div class="row-title">${esc(tx.description || 'Sem descrição')}</div>
      <div class="row-sub">${esc(catLabel(tx.category))} · ${esc(tx.institution || tx.account_name || '')}</div>
    </div>
    <span class="row-amount ${amountClass}">${brl.format(tx.amount)}</span>
  </div>`;
}

async function renderAccounts() {
  const data = await api('/api/accounts');
  const contas = data.results || [];
  const bancos = contas.filter((a) => a.type !== 'CREDIT');
  const cartoes = contas.filter((a) => a.type === 'CREDIT');
  const total = bancos.reduce((s, a) => s + (a.balance || 0), 0);

  $('#acc-summary').textContent = contas.length
    ? `${bancos.length} contas · ${cartoes.length} cartões · ${brl.format(total)}`
    : '';

  const linha = (a) => {
    const credito = a.type === 'CREDIT';
    const tipo = credito ? 'Fatura de cartão' : a.subtype === 'SAVINGS' ? 'Poupança' : 'Conta corrente';
    const saldo = a.balance || 0;
    const classe = credito ? (saldo < 0 ? 'neg' : '') : saldo >= 0 ? 'pos' : 'neg';
    return `<div class="row">
      ${
        a.image_url
          ? `<img class="item-logo" src="${esc(a.image_url)}" alt="" />`
          : `<span class="item-logo">${ICON_BANK}</span>`
      }
      <div class="row-main">
        <div class="row-title">${esc(a.name || 'Conta')}</div>
        <div class="row-sub">${esc(a.institution || 'Instituição')} · ${tipo}${a.number ? ` · final ${esc(String(a.number).slice(-4))}` : ''}</div>
      </div>
      <span class="chip ${credito ? 'chip-amber' : 'chip-green'}">${credito ? 'Cartão' : 'Banco'}</span>
      <div style="text-align:right">
        <div class="row-amount ${classe}">${brl.format(saldo)}</div>
        <div class="row-sub">${credito ? 'em aberto' : 'disponível'}</div>
      </div>
    </div>`;
  };

  $('#accounts-list').innerHTML = contas.length
    ? [...bancos, ...cartoes].map(linha).join('')
    : '<div class="empty">Nenhuma conta ainda — conecte um banco para ver os saldos aqui.</div>';
}

async function renderPainel() {
  const month = currentMonth();
  const [summary, categories, recent] = await Promise.all([
    api(`/api/summary?month=${month}`),
    api(`/api/categories?month=${month}`),
    api(`/api/transactions?month=${month}&limit=6`),
    renderAccounts().catch(() => {}),
  ]);

  $('#subtitle').textContent =
    `${summary.items} conexões · ${summary.accounts} contas · ${summary.investments} investimentos`;

  const profitClass = summary.profit > 0 ? 'pos' : summary.profit < 0 ? 'neg' : '';
  $('#cards-painel').innerHTML = `
    <div class="stat-cell" data-enter>
      <span class="stat-label">Saldo em contas</span>
      <div>
        <span class="stat-value">${brl.format(summary.bankBalance)}</span>
        <div class="stat-sub">${summary.creditBalance > 0 ? `Fatura em aberto: ${brl.format(summary.creditBalance)}` : 'Contas bancárias'}</div>
      </div>
    </div>
    <div class="stat-cell" data-enter>
      <span class="stat-label">Total investido</span>
      <div>
        <span class="stat-value">${brl.format(summary.invested)}</span>
        <div class="stat-sub">${summary.investments} posição(ões) ativa(s)</div>
      </div>
    </div>
    <div class="stat-cell" data-enter>
      <span class="stat-label">Rendimento acumulado</span>
      <div>
        <span class="stat-value ${profitClass}">${brl.format(summary.profit)}</span>
        <div class="stat-sub">${summary.profitRate != null ? `${num.format(summary.profitRate)}% sobre o investido` : 'sem base de cálculo'}</div>
      </div>
    </div>
    <div class="stat-cell" data-enter>
      <span class="stat-label">Saídas em ${monthLabel(month)}</span>
      <div>
        <span class="stat-value neg">${brl.format(summary.expenses)}</span>
        <div class="stat-sub">Entradas no mês: ${brl.format(summary.income)}</div>
      </div>
    </div>`;

  const list = categories.results;
  const max = list.length ? list[0].total : 0;
  $('#cat-month').textContent = `· ${monthLabel(month)}`;
  $('#category-bars').innerHTML = list.length
    ? list
        .slice(0, 8)
        .map(
          (c) => `<div class="bar-row">
            <span title="${esc(c.category)}">${esc(catLabel(c.category))}</span>
            <div class="bar-track"><div class="bar-fill" style="width:${max ? Math.round((c.total / max) * 100) : 0}%"></div></div>
            <span class="bar-value">${brl.format(c.total)}</span>
          </div>`
        )
        .join('')
    : '<div class="empty">Sem gastos neste mês.</div>';

  $('#recent-list').innerHTML = recent.results.length
    ? recent.results.map(txRow).join('')
    : '<div class="empty">Nenhum lançamento.</div>';
}

/* gastos */

async function renderGastosTotals(month) {
  const s = await api(`/api/summary?month=${encodeURIComponent(month)}`);
  const saldo = s.income - s.expenses;
  $('#gastos-totals').innerHTML = `
    <div class="total-item">Saídas<b class="neg">${brl.format(s.expenses)}</b></div>
    <div class="total-item">Entradas<b class="pos">${brl.format(s.income)}</b></div>
    <div class="total-item">Saldo do mês<b class="${saldo >= 0 ? 'pos' : 'neg'}">${brl.format(saldo)}</b></div>`;
}

async function loadCategories() {
  const data = await api(`/api/categories?month=${encodeURIComponent(state.filters.month)}`);
  const sel = $('#f-category');
  const prev = state.filters.category;
  sel.innerHTML =
    '<option value="">Todas</option>' +
    data.results
      .map(
        (c) =>
          `<option value="${esc(c.category)}" ${c.category === prev ? 'selected' : ''}>${esc(catLabel(c.category))} (${num.format(c.total)})</option>`
      )
      .join('');
  if (prev && ![...sel.options].some((o) => o.value === prev)) {
    sel.value = '';
    state.filters.category = '';
  }
}

async function loadTransactions(reset = false) {
  if (reset) state.txOffset = 0;
  const f = state.filters;
  const params = new URLSearchParams({ month: f.month, limit: '50', offset: String(state.txOffset) });
  if (f.type) params.set('type', f.type);
  if (f.category) params.set('category', f.category);
  if (f.q) params.set('q', f.q);

  const data = await api(`/api/transactions?${params}`);
  state.txTotal = data.total;
  const rows = data.results.map(txRow).join('');
  const list = $('#tx-list');
  if (reset) {
    list.innerHTML = rows || '<div class="empty">Nenhum lançamento com esses filtros.</div>';
  } else {
    list.insertAdjacentHTML('beforeend', rows);
  }
  state.txOffset += data.results.length;

  $('#tx-count').textContent = data.total ? `${state.txOffset} de ${data.total} lançamentos` : '';
  $('#btn-more').hidden = state.txOffset >= data.total;
}

async function renderGastos() {
  const month = state.filters.month || currentMonth();
  const [months] = await Promise.all([api('/api/months')]);
  const all = months.results.includes(month) ? months.results : [month, ...months.results];
  if (!state.filters.month) state.filters.month = all[0];
  $('#f-month').innerHTML = all
    .map((m) => `<option value="${esc(m)}" ${m === state.filters.month ? 'selected' : ''}>${esc(monthLabel(m))}</option>`)
    .join('');

  await Promise.all([
    renderGastosTotals(state.filters.month),
    loadCategories(),
    loadTransactions(true),
  ]);
}

/* investimentos */

function invRow(inv) {
  const p = invProfit(inv);
  const bits = [];
  if (inv.issuer || inv.institution) bits.push(esc(inv.issuer || inv.institution));
  if (inv.rate && inv.rate_type) bits.push(`${num.format(inv.rate)}% ${esc(inv.rate_type)}`);
  else if (inv.fixed_annual_rate != null) bits.push(`${num.format(inv.fixed_annual_rate)}% a.a.`);
  else if (inv.annual_rate != null) bits.push(`${num.format(inv.annual_rate)}% a.a.`);

  return `<div class="row">
    <div class="row-main">
      <div class="row-title">${esc(inv.name)}</div>
      <div class="row-sub">${bits.join(' · ') || '&nbsp;'}</div>
    </div>
    <span class="chip">${esc(INV_TYPES[inv.type] || inv.type || 'Investimento')}</span>
    <div style="text-align:right">
      <div class="row-amount">${brl.format(inv.balance)}</div>
      <div class="row-sub ${p > 0 ? 'pos' : p < 0 ? 'neg' : ''}">${p != null ? `${p >= 0 ? '+' : ''}${brl.format(p)}` : 'lucro —'}</div>
    </div>
  </div>`;
}

async function renderInvestimentos() {
  const data = await api('/api/investments');
  const rows = data.results;

  let invested = 0;
  let profit = 0;
  let base = 0;
  for (const inv of rows) {
    invested += inv.balance || 0;
    const p = invProfit(inv);
    if (p != null) profit += p;
    // Base do rendimento: o que foi aplicado (pode faltar em algumas instituições)
    const b = inv.amount_profit != null ? inv.balance - inv.amount_profit : inv.amount_original;
    if (b != null) base += b;
  }
  const rate = base > 0 ? (profit / base) * 100 : null;

  $('#cards-invest').innerHTML = `
    <div class="stat-cell" data-enter>
      <span class="stat-label">Total investido</span>
      <div>
        <span class="stat-value">${brl.format(invested)}</span>
        <div class="stat-sub">${rows.length} posição(ões) ativa(s)</div>
      </div>
    </div>
    <div class="stat-cell" data-enter>
      <span class="stat-label">Rendimento</span>
      <div>
        <span class="stat-value ${profit > 0 ? 'pos' : profit < 0 ? 'neg' : ''}">${brl.format(profit)}</span>
        <div class="stat-sub">${rate != null ? `${num.format(rate)}% sobre o aplicado` : 'nem toda instituição informa o lucro'}</div>
      </div>
    </div>`;

  $('#inv-list').innerHTML = rows.length
    ? rows.map(invRow).join('')
    : '<div class="empty">Nenhum investimento encontrado ainda. Conecte um banco ou corretora que tenha investimentos.</div>';
}

/* conexões */

async function renderConexoes() {
  const devMode = Boolean(state.status && state.status.mode === 'development');
  $('#setup-help').hidden = !(
    state.status && (!state.status.configured || devMode)
  );

  const sandbox = sandboxHabilitado();
  const chk = $('#chk-sandbox');
  if (chk) chk.checked = sandbox;

  const mode = state.status && state.status.mode;
  const modeEl = $('#conn-mode');
  if (modeEl) {
    modeEl.textContent = sandbox
      ? 'Modo teste · bancos sandbox'
      : mode === 'production'
        ? `Modo produção · ${num.format(state.status.liveConnectors ?? 0)} instituições reais`
        : devMode
          ? 'Modo desenvolvimento · só conectores de teste'
          : 'Modo —';
    modeEl.className = sandbox || devMode ? 'mode-warn' : 'muted';
  }

  const data = await api('/api/items');
  const list = $('#items-list');

  if (!data.results.length) {
    list.innerHTML = '<div class="empty">Nenhuma conexão ainda.</div>';
    return;
  }

  list.innerHTML = data.results
    .map((item) => {
      const ok = item.status === 'UPDATED' || item.status === 'CREATED';
      return `<div class="row">
        ${
          item.image_url
            ? `<img class="item-logo" src="${esc(item.image_url)}" alt="" />`
            : `<span class="item-logo">${ICON_BANK}</span>`
        }
        <div class="row-main">
          <div class="row-title">${esc(item.institution_name || 'Instituição')}</div>
          <div class="row-sub">Sincronizado: ${fmtDateTime(item.last_synced_at)}${item.error_message ? ` · ${ICON_WARN} ${esc(item.error_message)}` : ''}</div>
        </div>
        <span class="chip ${ok ? 'chip-green' : 'chip-amber'}">${esc(item.status || '—')}</span>
        <div class="item-actions">
          <button class="btn btn-small" data-sync="${esc(item.id)}">${ICON_SYNC} Sincronizar</button>
          <button class="btn btn-small btn-danger" data-del="${esc(item.id)}">Remover</button>
        </div>
      </div>`;
    })
    .join('');

  list.querySelectorAll('[data-sync]').forEach((b) => {
    b.onclick = () => syncItem(b.dataset.sync, true);
  });
  list.querySelectorAll('[data-del]').forEach((b) => {
    b.onclick = () => deleteItem(b.dataset.del);
  });
}

/* ações */

async function doSync(id, trigger) {
  return api(`/api/items/${encodeURIComponent(id)}/sync`, {
    method: 'POST',
    body: { trigger },
  });
}

async function syncItem(id, trigger = true) {
  if (state.busy) return;
  try {
    setBusy(true);
    toast('Sincronizando… pode levar alguns minutos.');
    const r = await doSync(id, trigger);
    if (r.ok) toast('Dados atualizados!');
    else toast(ptError({ codeDescription: r.status, message: r.message }), true);
    await refreshData();
  } catch (e) {
    toast(e.message, true);
  } finally {
    setBusy(false);
  }
}

async function syncAll() {
  if (state.busy) return;
  try {
    const data = await api('/api/items');
    if (!data.results.length) {
      toast('Nenhuma conexão para sincronizar.');
      return;
    }
    setBusy(true);
    const erros = [];
    for (const item of data.results) {
      toast(`Sincronizando ${item.institution_name || 'instituição'}…`);
      const r = await doSync(item.id, true);
      if (!r.ok) erros.push(`${item.institution_name || 'Instituição'}: ${r.status} — ${r.message}`);
    }
    await refreshData();
    if (erros.length) toast(`${erros.length} falha(s): ${erros.join(' | ')}`, true);
    else toast('Tudo sincronizado!');
  } catch (e) {
    toast(e.message, true);
  } finally {
    setBusy(false);
  }
}

async function deleteItem(id) {
  if (!confirm('Remover esta conexão e todos os dados locais dela?')) return;
  try {
    setBusy(true);
    await api(`/api/items/${encodeURIComponent(id)}`, { method: 'DELETE' });
    toast('Conexão removida.');
    await refreshData();
  } catch (e) {
    toast(e.message, true);
  } finally {
    setBusy(false);
  }
}

function loadWidgetScript() {
  return new Promise((resolve, reject) => {
    if (window.PluggyConnect) return resolve();
    const s = document.createElement('script');
    s.src = 'https://cdn.pluggy.ai/pluggy-connect/v2.8.2/pluggy-connect.js';
    s.onload = resolve;
    s.onerror = () =>
      reject(new Error('Não foi possível carregar o widget do Pluggy (verifique a internet).'));
    document.head.appendChild(s);
  });
}

async function connect() {
  if (state.busy) return;
  if (state.status && !state.status.configured) {
    showTab('conexoes');
    toast('Configure as credenciais no .env primeiro.', true);
    return;
  }
  let widget = null;
  const fecharWidget = () => {
    try {
      if (widget && typeof widget.close === 'function') widget.close();
    } catch {
      /* widget já fechado */
    }
  };

  try {
    // Fica ocupado até o widget fechar: evita abrir dois widgets ao mesmo tempo.
    setBusy(true);
    const { accessToken } = await api('/api/connect-token', { method: 'POST' });
    await loadWidgetScript();

    widget = new window.PluggyConnect({
      connectToken: accessToken,
      includeSandbox: sandboxHabilitado(),
      language: 'pt',
      theme: 'light',
      onClose: () => setBusy(false),
      onSuccess: async ({ item }) => {
        const name = (item && item.connector && item.connector.name) || 'instituição';
        try {
          toast(`Conectado a ${name}! Sincronizando…`);
          const r = await doSync(item.id, false);
          if (r.ok) toast('Dados atualizados!');
          else toast(ptError({ codeDescription: r.status, message: r.message }), true);
        } catch (e) {
          toast(e.message, true);
        }
        await refreshData();
        fecharWidget();
        setBusy(false);
      },
      onError: async (error) => {
        const msg = ptError(error);
        toast(msg, true);
        const dup =
          (error && error.codeDescription === 'ITEM_USER_ALREADY_EXISTS') ||
          /j[áa] está conectada/.test(msg);
        if (dup) {
          // O Pluggy devolve em error.data.items os ids das conexões que já
          // usam essas credenciais. Importa apenas um deles se ainda não
          // existir neste app: sincronizar ids[0] às cegas sincronizaria o
          // banco errado quando há mais de uma conexão ("2º banco não conecta").
          const ids = (error && error.data && error.data.items) || [];
          if (ids.length) {
            try {
              const locais = await api('/api/items');
              const conhecidos = new Set((locais.results || []).map((i) => i.id));
              const pendente = ids.find((id) => !conhecidos.has(id));
              if (pendente) {
                toast('Conexão existente encontrada no Pluggy — importando…');
                const r = await doSync(pendente, false);
                if (r.ok) toast('Conexão existente adicionada ao app!');
                else toast(ptError({ codeDescription: r.status, message: r.message }), true);
              } else {
                toast('Essa conta já está conectada e importada. Veja em Conexões.', true);
              }
            } catch (e) {
              toast(e.message, true);
            }
          }
          await refreshData();
          showTab('conexoes');
        }
        fecharWidget();
        setBusy(false);
      },
    });
    widget.init();
  } catch (e) {
    setBusy(false);
    toast(e.message, true);
  }
}

/* inicialização */

async function init() {
  document.querySelectorAll('.tab').forEach((t) => {
    t.onclick = () => showTab(t.dataset.tab);
  });
  $('#btn-connect').onclick = connect;
  $('#btn-connect-2').onclick = connect;
  $('#btn-sync-all').onclick = syncAll;
  $('#btn-more').onclick = () => loadTransactions(false).catch((e) => toast(e.message, true));

  const chkSandbox = $('#chk-sandbox');
  if (chkSandbox) {
    chkSandbox.checked = sandboxHabilitado();
    chkSandbox.onchange = () => {
      try {
        localStorage.setItem(CHAVE_SANDBOX, chkSandbox.checked ? 'on' : 'off');
      } catch {
        /* preferência vale só nesta sessão */
      }
      renderConexoes().catch((e) => toast(e.message, true));
      toast(chkSandbox.checked ? 'Bancos de teste ligados.' : 'Bancos de teste desligados.');
    };
  }

  document.querySelectorAll('.options[data-group]').forEach((grupo) => {
    grupo.addEventListener('click', (e) => {
      const opcao = e.target.closest('.option');
      if (!opcao || !grupo.contains(opcao)) return;
      aparencia[grupo.dataset.group] = opcao.dataset.value;
      aplicarAparencia();
      sincronizarOpcoes();
      salvarAparencia();
    });
  });
  $('#btn-reset-aparencia').onclick = () => {
    aparencia = { ...APARENCIA_PADRAO };
    aplicarAparencia();
    sincronizarOpcoes();
    salvarAparencia();
    toast('Aparência restaurada ao padrão.');
  };

  $('#f-month').onchange = async (e) => {
    state.filters.month = e.target.value;
    state.filters.category = '';
    try {
      await Promise.all([renderGastosTotals(state.filters.month), loadCategories(), loadTransactions(true)]);
    } catch (err) {
      toast(err.message, true);
    }
  };
  $('#f-type').onchange = (e) => {
    state.filters.type = e.target.value;
    loadTransactions(true).catch((err) => toast(err.message, true));
  };
  $('#f-category').onchange = (e) => {
    state.filters.category = e.target.value;
    loadTransactions(true).catch((err) => toast(err.message, true));
  };
  let qTimer;
  $('#f-q').oninput = (e) => {
    clearTimeout(qTimer);
    qTimer = setTimeout(() => {
      state.filters.q = e.target.value.trim();
      loadTransactions(true).catch((err) => toast(err.message, true));
    }, 350);
  };

  await refreshStatus();
  showTab('painel');
}

init().catch((e) => toast(e.message, true));
