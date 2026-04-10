from flask import Flask, jsonify, request, render_template
import blackjack as bj

app = Flask(__name__)
STATE: dict = {}


# ── State helpers ────────────────────────────────────────────────────────────

def _init(bankroll: int = 1000) -> None:
    STATE.clear()
    STATE.update({
        "shoe": bj.build_deck(),
        "bankroll": bankroll,
        "phase": "betting",          # betting | player_turn | round_over
        "dealer_hand": [],
        "hole_hidden": True,
        "player_hands": [],          # list of hand dicts (see _make_hand)
        "active_hand_index": 0,
        "current_bet": 0,
        "results": [],
        "round_net": None,
        "message": "Place your bet to start.",
    })


def _make_hand(cards: list, bet: int, from_split: bool = False) -> dict:
    return {"hand": cards, "bet": bet, "status": "active", "from_split": from_split}


def _deal() -> tuple:
    return bj.deal_card(None, STATE["shoe"])


def _options(ph: dict) -> dict:
    hand, bet = ph["hand"], ph["bet"]
    val = bj.hand_value(hand)
    can_split = (
        len(hand) == 2
        and hand[0][0] == hand[1][0]
        and STATE["bankroll"] >= bet
        and len(STATE["player_hands"]) == 1   # no re-split
    )
    return {
        "can_hit": val < 21,
        "can_stand": True,
        "can_double": len(hand) == 2 and STATE["bankroll"] >= bet,
        "can_split": can_split,
    }


def _serialize() -> dict:
    d_hand = STATE["dealer_hand"]
    d_serial = [
        ["?", "?"] if (i == 1 and STATE["hole_hidden"]) else list(c)
        for i, c in enumerate(d_hand)
    ]
    visible = [d_hand[0]] if (STATE["hole_hidden"] and d_hand) else d_hand
    d_value = bj.hand_value(visible) if visible else 0

    ph_serial = []
    for i, ph in enumerate(STATE["player_hands"]):
        is_active = (i == STATE["active_hand_index"] and ph["status"] == "active")
        opts = _options(ph) if is_active else {
            "can_hit": False, "can_stand": False, "can_double": False, "can_split": False,
        }
        ph_serial.append({
            "hand": [list(c) for c in ph["hand"]],
            "value": bj.hand_value(ph["hand"]),
            "bet": ph["bet"],
            "status": ph["status"],
            "is_soft": bj.is_soft(ph["hand"]),
            **opts,
        })

    return {
        "phase": STATE["phase"],
        "bankroll": STATE["bankroll"],
        "current_bet": STATE["current_bet"],
        "dealer": {"hand": d_serial, "value": d_value, "hole_hidden": STATE["hole_hidden"]},
        "player_hands": ph_serial,
        "active_hand_index": STATE["active_hand_index"],
        "results": STATE["results"],
        "message": STATE["message"],
        "round_net": STATE["round_net"],
    }


# ── Game flow ────────────────────────────────────────────────────────────────

def _advance() -> None:
    """Auto-complete current hand if needed, then move to next or dealer turn."""
    idx = STATE["active_hand_index"]
    ph = STATE["player_hands"][idx]

    # Auto-resolve bust / 21 on active hand
    if ph["status"] == "active":
        val = bj.hand_value(ph["hand"])
        if val > 21:
            ph["status"] = "bust"
        elif val == 21:
            ph["status"] = "stood"

    if ph["status"] == "active":
        return  # player still deciding

    # Scan for the next hand to activate
    next_idx = idx + 1
    while next_idx < len(STATE["player_hands"]):
        nph = STATE["player_hands"][next_idx]
        nph["status"] = "active"
        if bj.hand_value(nph["hand"]) == 21:
            nph["status"] = "stood"   # auto-stand on 21
            next_idx += 1
        else:
            STATE["active_hand_index"] = next_idx
            STATE["message"] = f"Now play hand {next_idx + 1}."
            return

    _dealer_turn()


def _dealer_turn() -> None:
    STATE["hole_hidden"] = False
    any_alive = any(ph["status"] != "bust" for ph in STATE["player_hands"])

    if any_alive:
        while True:
            dv = bj.hand_value(STATE["dealer_hand"])
            if dv < 17 or (dv == 17 and bj.is_soft(STATE["dealer_hand"])):
                STATE["dealer_hand"].append(_deal())
            else:
                break

    _resolve()


def _resolve() -> None:
    STATE["results"] = []
    total_net = 0

    for ph in STATE["player_hands"]:
        # Split hands cannot be paid as natural blackjack (casino rule)
        is_bj = bj.is_blackjack(ph["hand"]) and not ph.get("from_split", False)
        net, outcome = bj.resolve_hand(ph["hand"], STATE["dealer_hand"], ph["bet"], is_bj=is_bj)
        STATE["bankroll"] += ph["bet"] + net   # return staked bet + net delta
        total_net += net
        STATE["results"].append({"outcome": outcome, "net_change": net})

    STATE["round_net"] = total_net
    STATE["phase"] = "round_over"

    sign = "+" if total_net >= 0 else ""
    if len(STATE["results"]) == 1:
        r = STATE["results"][0]
        s = "+" if r["net_change"] >= 0 else ""
        STATE["message"] = f"{r['outcome'].upper()} — {s}{r['net_change']} chips"
    else:
        STATE["message"] = f"Round over — net: {sign}{total_net} chips"


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def get_state():
    if not STATE:
        _init()
    return jsonify(_serialize())


@app.route("/api/new_game", methods=["POST"])
def new_game():
    _init()
    return jsonify(_serialize())


@app.route("/api/new_round", methods=["POST"])
def new_round():
    """Keep bankroll and shoe; reset to betting phase."""
    STATE.update({
        "phase": "betting",
        "dealer_hand": [],
        "hole_hidden": True,
        "player_hands": [],
        "active_hand_index": 0,
        "current_bet": 0,
        "results": [],
        "round_net": None,
        "message": "Place your bet to start.",
    })
    return jsonify(_serialize())


@app.route("/api/place_bet", methods=["POST"])
def place_bet():
    if STATE.get("phase") != "betting":
        return jsonify({"error": "Not in betting phase."}), 400

    data = request.get_json(silent=True) or {}
    bet = data.get("bet", 0)
    max_bet = min(STATE["bankroll"], 500)

    if not isinstance(bet, int) or bet < 1 or bet > max_bet:
        return jsonify({"error": f"Bet must be between 1 and {max_bet} chips."}), 400

    STATE["bankroll"] -= bet
    STATE["current_bet"] = bet
    STATE["hole_hidden"] = True
    STATE["results"] = []
    STATE["round_net"] = None

    # Deal initial cards
    STATE["dealer_hand"] = [_deal(), _deal()]
    STATE["player_hands"] = [_make_hand([_deal(), _deal()], bet)]
    STATE["active_hand_index"] = 0

    player_bj = bj.is_blackjack(STATE["player_hands"][0]["hand"])
    dealer_bj = bj.is_blackjack(STATE["dealer_hand"])

    if player_bj or dealer_bj:
        STATE["hole_hidden"] = False
        STATE["player_hands"][0]["status"] = "blackjack" if player_bj else "stood"
        _resolve()
        return jsonify(_serialize())

    STATE["phase"] = "player_turn"
    STATE["message"] = "Your turn."
    return jsonify(_serialize())


@app.route("/api/action", methods=["POST"])
def action():
    if STATE.get("phase") != "player_turn":
        return jsonify({"error": "Not in player turn phase."}), 400

    data = request.get_json(silent=True) or {}
    act = data.get("action", "")
    hi = data.get("hand_index", STATE["active_hand_index"])

    if hi != STATE["active_hand_index"]:
        return jsonify({"error": "Not the active hand."}), 400

    ph = STATE["player_hands"][hi]
    if ph["status"] != "active":
        return jsonify({"error": "Hand is not active."}), 400

    opts = _options(ph)

    if act == "hit":
        if not opts["can_hit"]:
            return jsonify({"error": "Cannot hit on 21."}), 400
        ph["hand"].append(_deal())
        _advance()

    elif act == "stand":
        ph["status"] = "stood"
        _advance()

    elif act == "double":
        if not opts["can_double"]:
            return jsonify({"error": "Cannot double down."}), 400
        STATE["bankroll"] -= ph["bet"]
        ph["bet"] *= 2
        ph["hand"].append(_deal())
        ph["status"] = "doubled"
        _advance()

    elif act == "split":
        if not opts["can_split"]:
            return jsonify({"error": "Cannot split."}), 400
        STATE["bankroll"] -= ph["bet"]
        bet = ph["bet"]
        c1, c2 = ph["hand"]
        h1 = _make_hand([c1, _deal()], bet, from_split=True)
        h2 = _make_hand([c2, _deal()], bet, from_split=True)
        h2["status"] = "waiting"
        STATE["player_hands"] = [h1, h2]
        STATE["active_hand_index"] = 0
        STATE["message"] = "Play hand 1."
        if bj.hand_value(h1["hand"]) == 21:
            h1["status"] = "stood"
            _advance()

    else:
        return jsonify({"error": f"Unknown action '{act}'."}), 400

    return jsonify(_serialize())


if __name__ == "__main__":
    _init()
    app.run(debug=True)
