// ── State ────────────────────────────────────────────────────────────────────
let activeHandIndex = 0;
let stagedBet = 0;

// ── API helpers ───────────────────────────────────────────────────────────────
async function api(path, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== null) opts.body = JSON.stringify(body);
  try {
    const res = await fetch(path, opts);
    const data = await res.json();
    if (data.error) {
      setMessage(data.error);
      return null;
    }
    renderState(data);
    return data;
  } catch (err) {
    setMessage('Network error — is the server running?');
    return null;
  }
}

// ── Render ────────────────────────────────────────────────────────────────────
function renderState(state) {
  activeHandIndex = state.active_hand_index;

  // Bankroll
  document.getElementById('bankroll').textContent = state.bankroll.toLocaleString();

  // Dealer cards
  renderDealerCards(state.dealer);

  // Player hands
  renderPlayerHands(state.player_hands, state.active_hand_index, state.phase);

  // UI panels
  const betting       = document.getElementById('betting-area');
  const actionBtns    = document.getElementById('action-buttons');
  const roundOverBtns = document.getElementById('round-over-buttons');
  const resultBanner  = document.getElementById('result-banner');

  betting.classList.add('hidden');
  actionBtns.classList.add('hidden');
  roundOverBtns.classList.add('hidden');
  resultBanner.classList.add('hidden');

  if (state.phase === 'betting') {
    betting.classList.remove('hidden');
  } else if (state.phase === 'player_turn') {
    actionBtns.classList.remove('hidden');
    const ph = state.player_hands[state.active_hand_index];
    if (ph) {
      document.getElementById('btn-hit').disabled    = !ph.can_hit;
      document.getElementById('btn-stand').disabled  = !ph.can_stand;
      document.getElementById('btn-double').disabled = !ph.can_double;
      document.getElementById('btn-split').disabled  = !ph.can_split;
    }
  } else if (state.phase === 'round_over') {
    roundOverBtns.classList.remove('hidden');
    resultBanner.classList.remove('hidden');
    renderResults(state.results, state.round_net, state.bankroll);

    // Disable "New Round" if bankroll is empty
    const nextBtn = roundOverBtns.querySelector('.round-btn:not(.secondary)');
    if (nextBtn) nextBtn.disabled = state.bankroll <= 0;
  }

  // Message
  setMessage(state.message);
}

function renderDealerCards(dealer) {
  const row     = document.getElementById('dealer-cards');
  const badge   = document.getElementById('dealer-value-badge');
  row.innerHTML = '';

  if (!dealer.hand.length) {
    badge.classList.add('hidden');
    return;
  }

  dealer.hand.forEach(card => row.appendChild(makeCard(card)));

  badge.textContent = dealer.value;
  badge.classList.remove('hidden');
}

function renderPlayerHands(hands, activeIdx, phase) {
  const container = document.getElementById('player-hands-container');
  container.innerHTML = '';

  if (!hands.length) return;

  hands.forEach((ph, i) => {
    const wrap = document.createElement('div');
    wrap.className = 'player-hand';

    if (phase === 'player_turn') {
      if (i === activeIdx && ph.status === 'active') {
        wrap.classList.add('active-hand');
      } else {
        wrap.classList.add('inactive-hand');
      }
    }

    // Label row
    const labelRow = document.createElement('div');
    labelRow.className = 'hand-label';

    const prefix = hands.length > 1 ? `HAND ${i + 1} · ` : 'YOU · ';
    const softTag = ph.is_soft && ph.value <= 21 ? ' <span style="opacity:0.6">(soft)</span>' : '';
    const statusTag = makeStatusTag(ph.status);
    labelRow.innerHTML =
      `${prefix}<span class="hand-value">${ph.value}${softTag}</span>` +
      ` &nbsp;·&nbsp; BET $${ph.bet}` +
      (statusTag ? ` ${statusTag}` : '');

    // Cards
    const cardRow = document.createElement('div');
    cardRow.className = 'card-row';
    ph.hand.forEach(card => cardRow.appendChild(makeCard(card)));

    wrap.appendChild(labelRow);
    wrap.appendChild(cardRow);
    container.appendChild(wrap);
  });
}

function makeStatusTag(status) {
  const map = {
    bust:      ['tag-bust',      'BUST'],
    stood:     ['tag-stood',     'STAND'],
    doubled:   ['tag-doubled',   'DOUBLED'],
    blackjack: ['tag-blackjack', 'BLACKJACK'],
    waiting:   ['tag-stood',     'WAITING'],
  };
  if (!map[status]) return '';
  const [cls, label] = map[status];
  return `<span class="hand-status-tag ${cls}">${label}</span>`;
}

function renderResults(results, roundNet, bankroll) {
  const rows   = document.getElementById('result-rows');
  const netLine = document.getElementById('round-net-line');
  rows.innerHTML = '';

  results.forEach((r, i) => {
    const pill = document.createElement('div');
    const sign = r.net_change >= 0 ? '+' : '';
    const label = results.length > 1 ? `Hand ${i + 1}: ` : '';
    pill.textContent = `${label}${r.outcome.toUpperCase()}  ${sign}${r.net_change}`;
    pill.className = `result-pill ${pillClass(r.outcome, r.net_change)}`;
    rows.appendChild(pill);
  });

  const sign = roundNet >= 0 ? '+' : '';
  netLine.textContent = `Net this round: ${sign}${roundNet} chips  ·  Bankroll: $${bankroll.toLocaleString()}`;
}

function pillClass(outcome, netChange) {
  if (outcome === 'blackjack') return 'blackjack';
  if (netChange > 0)  return 'win';
  if (netChange < 0)  return 'loss';
  return 'push';
}

// ── Card factory ──────────────────────────────────────────────────────────────
const SUIT_CLASS = { '♠': 'spades', '♥': 'hearts', '♦': 'diamonds', '♣': 'clubs' };

function makeCard(card) {
  const div = document.createElement('div');

  if (card[0] === '?') {
    div.className = 'card back';
    return div;
  }

  const [rank, suit] = card;
  const suitCls = SUIT_CLASS[suit] || '';
  div.className = `card ${suitCls}`;

  div.innerHTML =
    `<span class="corner">${rank}<br>${suit}</span>` +
    `<span class="center-suit">${suit}</span>` +
    `<span class="corner bottom">${rank}<br>${suit}</span>`;

  return div;
}

// ── Betting ───────────────────────────────────────────────────────────────────
function addChip(amount) {
  stagedBet += amount;
  document.getElementById('staged-amount').textContent = `$${stagedBet}`;
}

function clearBet() {
  stagedBet = 0;
  document.getElementById('staged-amount').textContent = '$0';
}

async function placeBet() {
  if (stagedBet <= 0) {
    setMessage('Select chips to place a bet first.');
    return;
  }
  const prev = stagedBet;
  stagedBet = 0;
  document.getElementById('staged-amount').textContent = '$0';
  await api('/api/place_bet', 'POST', { bet: prev });
}

// ── Actions ───────────────────────────────────────────────────────────────────
async function doAction(action) {
  await api('/api/action', 'POST', { action, hand_index: activeHandIndex });
}

async function nextRound() {
  await api('/api/new_round', 'POST');
}

async function newGame() {
  await api('/api/new_game', 'POST');
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function setMessage(text) {
  document.getElementById('message').textContent = text;
}

// ── Init ──────────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => api('/api/state'));
