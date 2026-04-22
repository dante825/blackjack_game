// ── Socket setup ──────────────────────────────────────────────────────────────
const socket = io();
let stagedBet = 0;
let lastState = null;

socket.on('connect', () => {
  if (lastState) setMessage('Reconnected.');
});

socket.on('disconnect', () => setMessage('Connection lost — reconnecting…'));

socket.on('state_update', state => {
  lastState = state;
  renderState(state);
});

socket.on('error', data => {
  showLobbyError(data.message);
  setMessage(data.message);
});

// ── Lobby ─────────────────────────────────────────────────────────────────────
function joinTable() {
  const input = document.getElementById('name-input');
  const name = input.value.trim() || 'Player';
  socket.emit('join_table', { name });

  // Hide lobby and show app on first state_update (handled in renderState)
}

document.getElementById('name-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') joinTable();
});

function showLobbyError(msg) {
  const el = document.getElementById('lobby-error');
  if (el) {
    el.textContent = msg;
    el.classList.remove('hidden');
  }
}

function leaveTable() {
  // Disconnect and reload to return to lobby
  socket.disconnect();
  location.reload();
}

// ── Render ────────────────────────────────────────────────────────────────────
function renderState(state) {
  // Transition lobby → game on first state that includes my seat
  if (state.my_seat_id) {
    document.getElementById('lobby').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
  }

  // My seat data
  const mySeat = state.my_seat_id ? state.seats[state.my_seat_id] : null;

  // Header bankroll
  if (mySeat) {
    document.getElementById('bankroll').textContent =
      mySeat.bankroll.toLocaleString();
  }

  // Dealer
  renderDealerCards(state.dealer);

  // All seats
  renderSeats(state);

  // Controls — only for my seat
  updateControls(state, mySeat);

  // Message
  setMessage(state.message);
}

// ── Dealer ────────────────────────────────────────────────────────────────────
function renderDealerCards(dealer) {
  const row   = document.getElementById('dealer-cards');
  const badge = document.getElementById('dealer-value-badge');
  row.innerHTML = '';

  if (!dealer.hand.length) {
    badge.classList.add('hidden');
    return;
  }

  dealer.hand.forEach(card => row.appendChild(makeCard(card)));
  badge.textContent = dealer.value;
  badge.classList.remove('hidden');
}

// ── Seats ─────────────────────────────────────────────────────────────────────
function renderSeats(state) {
  const section = document.getElementById('seats-row');
  section.innerHTML = '';

  state.seat_order.forEach(seatId => {
    const seat = state.seats[seatId];
    if (!seat) return;

    const card = document.createElement('div');
    card.className = 'seat-card';
    if (seat.is_mine)   card.classList.add('my-seat');
    if (seat.is_active) card.classList.add('active-seat');

    // Seat header: name + bankroll
    const hdr = document.createElement('div');
    hdr.className = 'seat-header';

    const nameEl = document.createElement('span');
    nameEl.className = 'seat-name';
    nameEl.textContent = seat.name + (seat.is_mine ? ' (you)' : '');

    const brEl = document.createElement('span');
    brEl.className = 'seat-bankroll';
    brEl.textContent = `$${seat.bankroll.toLocaleString()}`;

    hdr.appendChild(nameEl);
    hdr.appendChild(brEl);
    card.appendChild(hdr);

    // Bet chip (during betting / player_turn / round_over)
    if (seat.bet > 0) {
      const betEl = document.createElement('div');
      betEl.className = 'seat-bet';
      betEl.textContent = `BET $${seat.bet}`;
      card.appendChild(betEl);
    } else if (state.phase === 'betting' && !seat.ready) {
      const waitEl = document.createElement('div');
      waitEl.className = 'seat-bet waiting-bet';
      waitEl.textContent = 'Waiting to bet…';
      card.appendChild(waitEl);
    } else if (state.phase === 'betting' && seat.ready) {
      const waitEl = document.createElement('div');
      waitEl.className = 'seat-bet ready-bet';
      waitEl.textContent = '✓ Ready';
      card.appendChild(waitEl);
    }

    // Hands
    if (seat.hands.length) {
      seat.hands.forEach((h, i) => {
        const handWrap = document.createElement('div');
        handWrap.className = 'seat-hand';

        const isActiveHand = seat.is_active && i === seat.active_hand_index && h.status === 'active';
        if (isActiveHand) handWrap.classList.add('active-hand');
        else if (h.status !== 'active') handWrap.classList.add('resolved-hand');

        // Hand label
        const lbl = document.createElement('div');
        lbl.className = 'seat-hand-label';
        const softTag = h.is_soft && h.value <= 21
          ? ' <span class="soft-tag">(soft)</span>' : '';
        const stTag = makeStatusTag(h.status);
        lbl.innerHTML =
          (seat.hands.length > 1 ? `HAND ${i + 1} · ` : '') +
          `<span class="hand-value">${h.value}${softTag}</span>` +
          ` · $${h.bet}` +
          (stTag ? ` ${stTag}` : '');
        handWrap.appendChild(lbl);

        // Cards
        const cardRow = document.createElement('div');
        cardRow.className = 'card-row';
        const isMini = !seat.is_mine;
        h.hand.forEach(c => cardRow.appendChild(makeCard(c, isMini)));
        handWrap.appendChild(cardRow);

        card.appendChild(handWrap);
      });
    }

    // Round results
    if (state.phase === 'round_over' && seat.results && seat.results.length) {
      const resWrap = document.createElement('div');
      resWrap.className = 'seat-results';
      seat.results.forEach((r, i) => {
        const pill = document.createElement('span');
        const sign = r.net_change >= 0 ? '+' : '';
        const label = seat.results.length > 1 ? `H${i + 1}: ` : '';
        pill.textContent = `${label}${r.outcome.toUpperCase()} ${sign}${r.net_change}`;
        pill.className = `result-pill ${pillClass(r.outcome, r.net_change)}`;
        resWrap.appendChild(pill);
      });
      card.appendChild(resWrap);
    }

    section.appendChild(card);
  });
}

// ── Controls ──────────────────────────────────────────────────────────────────
function updateControls(state, mySeat) {
  const bettingArea   = document.getElementById('betting-area');
  const actionBtns    = document.getElementById('action-buttons');
  const roundOverArea = document.getElementById('round-over-area');

  bettingArea.classList.add('hidden');
  actionBtns.classList.add('hidden');
  roundOverArea.classList.add('hidden');

  if (!mySeat) return;

  if (state.phase === 'betting' && !mySeat.ready) {
    bettingArea.classList.remove('hidden');
  } else if (state.phase === 'player_turn' && mySeat.is_active) {
    const hi = mySeat.active_hand_index;
    const ph = mySeat.hands[hi];
    if (ph && ph.status === 'active') {
      actionBtns.classList.remove('hidden');
      document.getElementById('btn-hit').disabled    = !ph.can_hit;
      document.getElementById('btn-stand').disabled  = !ph.can_stand;
      document.getElementById('btn-double').disabled = !ph.can_double;
      document.getElementById('btn-split').disabled  = !ph.can_split;
    }
  } else if (state.phase === 'round_over') {
    roundOverArea.classList.remove('hidden');
    renderMyResults(mySeat);

    const newRoundBtn = document.querySelector('#round-over-buttons .round-btn:not(.secondary)');
    if (newRoundBtn) newRoundBtn.disabled = mySeat.bankroll <= 0;
  }
}

function renderMyResults(mySeat) {
  const rows    = document.getElementById('result-rows');
  const netLine = document.getElementById('round-net-line');
  rows.innerHTML = '';

  if (!mySeat.results) return;

  mySeat.results.forEach((r, i) => {
    const pill = document.createElement('div');
    const sign = r.net_change >= 0 ? '+' : '';
    const label = mySeat.results.length > 1 ? `Hand ${i + 1}: ` : '';
    pill.textContent = `${label}${r.outcome.toUpperCase()}  ${sign}${r.net_change}`;
    pill.className = `result-pill ${pillClass(r.outcome, r.net_change)}`;
    rows.appendChild(pill);
  });

  const net  = mySeat.round_net ?? 0;
  const sign = net >= 0 ? '+' : '';
  netLine.textContent =
    `Net this round: ${sign}${net} chips  ·  Bankroll: $${mySeat.bankroll.toLocaleString()}`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function makeStatusTag(status) {
  const map = {
    bust:      ['tag-bust',      'BUST'],
    stood:     ['tag-stood',     'STAND'],
    doubled:   ['tag-doubled',   'DOUBLED'],
    blackjack: ['tag-blackjack', 'BLACKJACK'],
    charlie:   ['tag-charlie',   '5♣ CHARLIE'],
    waiting:   ['tag-stood',     'WAITING'],
  };
  if (!map[status]) return '';
  const [cls, label] = map[status];
  return `<span class="hand-status-tag ${cls}">${label}</span>`;
}

function pillClass(outcome, netChange) {
  if (outcome === 'blackjack')      return 'blackjack';
  if (outcome === '5 card charlie') return 'charlie';
  if (netChange > 0)  return 'win';
  if (netChange < 0)  return 'loss';
  return 'push';
}

const SUIT_CLASS = { '♠': 'spades', '♥': 'hearts', '♦': 'diamonds', '♣': 'clubs' };

function makeCard(card, mini = false) {
  const div = document.createElement('div');

  if (card[0] === '?') {
    div.className = 'card back' + (mini ? ' mini' : '');
    return div;
  }

  const [rank, suit] = card;
  div.className = `card ${SUIT_CLASS[suit] || ''}` + (mini ? ' mini' : '');
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

function placeBet() {
  if (stagedBet <= 0) {
    setMessage('Select chips to place a bet first.');
    return;
  }
  const bet = stagedBet;
  stagedBet = 0;
  document.getElementById('staged-amount').textContent = '$0';
  socket.emit('place_bet', { bet });
}

// ── Actions ───────────────────────────────────────────────────────────────────
function doAction(action) { socket.emit('action', { action }); }
function newRound()       { socket.emit('new_round'); }

function openRules()  { document.getElementById('rules-modal').classList.remove('hidden'); }
function closeRules() { document.getElementById('rules-modal').classList.add('hidden'); }
function closeRulesOnBackdrop(e) { if (e.target === e.currentTarget) closeRules(); }

// ── Utilities ─────────────────────────────────────────────────────────────────
function setMessage(text) {
  document.getElementById('message').textContent = text;
}
