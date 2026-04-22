from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import blackjack as bj

app = Flask(__name__)
app.config['SECRET_KEY'] = 'bj-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

MAX_SEATS = 5

ROOM = {}


def _room_init():
    ROOM.clear()
    ROOM.update({
        "shoe": bj.build_deck(),
        "phase": "waiting",        # waiting | betting | player_turn | round_over
        "dealer_hand": [],
        "hole_hidden": True,
        "seats": {},               # seat_id -> seat dict
        "seat_order": [],          # seat_ids in join order
        "active_seat_index": 0,
        "five_card_charlie": True,
        "message": "Waiting for players...",
    })


_room_init()

PLAYER_BANKROLLS: dict = {}  # name → bankroll, persists across disconnects within a session


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_seat(sid, name):
    bankroll = PLAYER_BANKROLLS.get(name, 1000)
    if bankroll <= 0:
        bankroll = 1000
    return {
        "sid": sid,
        "name": name,
        "bankroll": bankroll,
        "bet": 0,
        "hands": [],
        "active_hand_index": 0,
        "results": [],
        "round_net": None,
        "ready": False,
    }


def _make_hand(cards, bet, from_split=False):
    return {"hand": cards, "bet": bet, "status": "active", "from_split": from_split}


def _deal():
    shoe = ROOM["shoe"]
    if len(shoe) < 52:
        shoe.extend(bj.build_deck())
    return shoe.pop()


def _find_seat(sid):
    for seat_id, seat in ROOM["seats"].items():
        if seat["sid"] == sid:
            return seat_id, seat
    return None, None


def _options(hand_dict, bankroll, num_hands):
    hand, bet = hand_dict["hand"], hand_dict["bet"]
    val = bj.hand_value(hand)
    return {
        "can_hit":    val < 21,
        "can_stand":  True,
        "can_double": len(hand) == 2 and bankroll >= bet,
        "can_split":  (
            len(hand) == 2
            and hand[0][0] == hand[1][0]
            and bankroll >= bet
            and num_hands == 1
        ),
    }


def _serialize(viewer_sid=None):
    viewer_seat_id = None
    for sid_key, seat in ROOM["seats"].items():
        if seat["sid"] == viewer_sid:
            viewer_seat_id = sid_key
            break

    active_seat_id = (
        ROOM["seat_order"][ROOM["active_seat_index"]]
        if ROOM["seat_order"] and ROOM["active_seat_index"] < len(ROOM["seat_order"])
        else None
    )

    seats_out = {}
    for seat_id, seat in ROOM["seats"].items():
        is_active_seat = (seat_id == active_seat_id and ROOM["phase"] == "player_turn")
        hands_out = []
        for i, h in enumerate(seat["hands"]):
            is_active_hand = (
                is_active_seat
                and i == seat["active_hand_index"]
                and h["status"] == "active"
            )
            opts = _options(h, seat["bankroll"], len(seat["hands"])) if is_active_hand else {
                "can_hit": False, "can_stand": False, "can_double": False, "can_split": False,
            }
            hands_out.append({
                "hand":    [list(c) for c in h["hand"]],
                "value":   bj.hand_value(h["hand"]),
                "bet":     h["bet"],
                "status":  h["status"],
                "is_soft": bj.is_soft(h["hand"]),
                **opts,
            })
        seats_out[seat_id] = {
            "name":              seat["name"],
            "bankroll":          seat["bankroll"],
            "bet":               seat["bet"],
            "hands":             hands_out,
            "active_hand_index": seat["active_hand_index"],
            "results":           seat["results"],
            "round_net":         seat["round_net"],
            "ready":             seat["ready"],
            "is_active":         is_active_seat,
            "is_mine":           seat_id == viewer_seat_id,
        }

    d_hand = ROOM["dealer_hand"]
    d_serial = [
        ["?", "?"] if (i == 1 and ROOM["hole_hidden"]) else list(c)
        for i, c in enumerate(d_hand)
    ]
    visible = [d_hand[0]] if (ROOM["hole_hidden"] and d_hand) else d_hand
    d_value = bj.hand_value(visible) if visible else 0

    return {
        "phase":            ROOM["phase"],
        "dealer":           {"hand": d_serial, "value": d_value, "hole_hidden": ROOM["hole_hidden"]},
        "seats":            seats_out,
        "seat_order":       ROOM["seat_order"],
        "active_seat_id":   active_seat_id,
        "my_seat_id":       viewer_seat_id,
        "five_card_charlie": ROOM["five_card_charlie"],
        "message":          ROOM["message"],
        "seat_count":       len(ROOM["seats"]),
        "max_seats":        MAX_SEATS,
    }


def _broadcast():
    for seat in ROOM["seats"].values():
        if seat["sid"]:
            socketio.emit("state_update", _serialize(seat["sid"]), to=seat["sid"])


# ── Game flow ─────────────────────────────────────────────────────────────────

def _advance_seat():
    if not ROOM["seat_order"]:
        return

    idx = ROOM["active_seat_index"]
    if idx >= len(ROOM["seat_order"]):
        _dealer_turn()
        return

    seat_id = ROOM["seat_order"][idx]
    seat = ROOM["seats"].get(seat_id)
    if not seat or not seat["hands"]:
        ROOM["active_seat_index"] += 1
        _advance_seat()
        return

    hi = seat["active_hand_index"]
    ph = seat["hands"][hi]

    # Auto-resolve current hand
    if ph["status"] == "active":
        val = bj.hand_value(ph["hand"])
        if val > 21:
            ph["status"] = "bust"
        elif val == 21:
            ph["status"] = "stood"
        elif ROOM["five_card_charlie"] and len(ph["hand"]) >= 5:
            ph["status"] = "charlie"

    if ph["status"] == "active":
        return  # still deciding

    # Try next split hand in this seat
    next_hi = hi + 1
    while next_hi < len(seat["hands"]):
        nph = seat["hands"][next_hi]
        nph["status"] = "active"
        if bj.hand_value(nph["hand"]) == 21:
            nph["status"] = "stood"
            next_hi += 1
        else:
            seat["active_hand_index"] = next_hi
            ROOM["message"] = f"{seat['name']}: play hand {next_hi + 1}."
            return

    # Move to the next seat that has hands
    ROOM["active_seat_index"] += 1
    next_idx = ROOM["active_seat_index"]
    while next_idx < len(ROOM["seat_order"]):
        next_seat = ROOM["seats"].get(ROOM["seat_order"][next_idx])
        if next_seat and next_seat["hands"]:
            next_seat["active_hand_index"] = 0
            ROOM["message"] = f"{next_seat['name']}'s turn."
            return
        ROOM["active_seat_index"] += 1
        next_idx += 1

    _dealer_turn()


def _dealer_turn():
    ROOM["hole_hidden"] = False
    any_alive = any(
        any(h["status"] != "bust" for h in seat["hands"])
        for seat in ROOM["seats"].values() if seat["hands"]
    )
    if any_alive:
        while True:
            dv = bj.hand_value(ROOM["dealer_hand"])
            if dv < 17 or (dv == 17 and bj.is_soft(ROOM["dealer_hand"])):
                ROOM["dealer_hand"].append(_deal())
            else:
                break
    _resolve()


def _resolve():
    for seat in ROOM["seats"].values():
        seat["results"] = []
        total_net = 0
        for ph in seat["hands"]:
            if ph["status"] == "charlie":
                net, outcome = ph["bet"], "5 card charlie"
            else:
                is_bj = bj.is_blackjack(ph["hand"]) and not ph.get("from_split", False)
                net, outcome = bj.resolve_hand(ph["hand"], ROOM["dealer_hand"], ph["bet"], is_bj=is_bj)
            seat["bankroll"] += ph["bet"] + net
            total_net += net
            seat["results"].append({"outcome": outcome, "net_change": net})
        seat["round_net"] = total_net

    ROOM["phase"] = "round_over"
    ROOM["message"] = "Round over! Press New Round to play again."


def _start_round():
    ROOM["dealer_hand"] = [_deal(), _deal()]
    ROOM["hole_hidden"] = True
    ROOM["active_seat_index"] = 0

    for seat in ROOM["seats"].values():
        seat["hands"] = []
        seat["active_hand_index"] = 0
        seat["results"] = []
        seat["round_net"] = None
        if seat["bet"] > 0:
            seat["hands"] = [_make_hand([_deal(), _deal()], seat["bet"])]

    player_bjs = {
        sid: bj.is_blackjack(s["hands"][0]["hand"])
        for sid, s in ROOM["seats"].items() if s["hands"]
    }
    dealer_bj = bj.is_blackjack(ROOM["dealer_hand"])

    if dealer_bj or any(player_bjs.values()):
        ROOM["hole_hidden"] = False
        for seat_id, seat in ROOM["seats"].items():
            if seat["hands"]:
                seat["hands"][0]["status"] = "blackjack" if player_bjs.get(seat_id) else "stood"
        _resolve()
        return

    # Find first seat with hands
    ROOM["phase"] = "player_turn"
    for i, seat_id in enumerate(ROOM["seat_order"]):
        seat = ROOM["seats"].get(seat_id)
        if seat and seat["hands"]:
            ROOM["active_seat_index"] = i
            ROOM["message"] = f"{seat['name']}'s turn."
            return

    _dealer_turn()


# ── Socket events ─────────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    emit("state_update", _serialize(None))


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    seat_id, _ = _find_seat(sid)
    if not seat_id:
        return

    was_active = (
        ROOM["phase"] == "player_turn"
        and ROOM["seat_order"]
        and ROOM["active_seat_index"] < len(ROOM["seat_order"])
        and ROOM["seat_order"][ROOM["active_seat_index"]] == seat_id
    )

    seat = ROOM["seats"][seat_id]
    PLAYER_BANKROLLS[seat["name"]] = seat["bankroll"]
    del ROOM["seats"][seat_id]
    ROOM["seat_order"].remove(seat_id)
    if ROOM["active_seat_index"] >= len(ROOM["seat_order"]):
        ROOM["active_seat_index"] = max(0, len(ROOM["seat_order"]) - 1)

    if not ROOM["seats"]:
        _room_init()
    else:
        if was_active:
            _advance_seat()
        # Check if disconnecting player was last to bet
        if ROOM["phase"] == "betting" and ROOM["seats"] and all(s["ready"] for s in ROOM["seats"].values()):
            _start_round()
        _broadcast()


@socketio.on("join_table")
def on_join_table(data):
    sid = request.sid
    name = str(data.get("name") or "Player").strip()[:20] or "Player"

    if len(ROOM["seats"]) >= MAX_SEATS:
        emit("error", {"message": "Table is full (5 players max)."})
        return
    if _find_seat(sid)[0]:
        emit("error", {"message": "Already seated."})
        return

    seat_id = f"s{len(ROOM['seat_order']) + 1}_{sid[:4]}"
    ROOM["seats"][seat_id] = _make_seat(sid, name)
    ROOM["seat_order"].append(seat_id)

    if ROOM["phase"] == "waiting":
        ROOM["phase"] = "betting"
        ROOM["message"] = "Place your bets!"

    _broadcast()


@socketio.on("place_bet")
def on_place_bet(data):
    sid = request.sid
    seat_id, seat = _find_seat(sid)
    if not seat:
        return
    if ROOM["phase"] != "betting":
        emit("error", {"message": "Not in betting phase."})
        return
    if seat["ready"]:
        emit("error", {"message": "Bet already placed."})
        return

    bet = data.get("bet", 0)
    max_bet = min(seat["bankroll"], 500)
    if not isinstance(bet, int) or bet < 1 or bet > max_bet:
        emit("error", {"message": f"Bet must be 1–{max_bet}."})
        return

    seat["bankroll"] -= bet
    seat["bet"] = bet
    seat["ready"] = True

    if all(s["ready"] for s in ROOM["seats"].values()):
        _start_round()
    else:
        waiting = [s["name"] for s in ROOM["seats"].values() if not s["ready"]]
        ROOM["message"] = f"Waiting for: {', '.join(waiting)}"

    _broadcast()


@socketio.on("action")
def on_action(data):
    sid = request.sid
    seat_id, seat = _find_seat(sid)
    if not seat:
        return
    if ROOM["phase"] != "player_turn":
        emit("error", {"message": "Not in player turn phase."})
        return

    active_seat_id = (
        ROOM["seat_order"][ROOM["active_seat_index"]]
        if ROOM["seat_order"] and ROOM["active_seat_index"] < len(ROOM["seat_order"])
        else None
    )
    if seat_id != active_seat_id:
        emit("error", {"message": "Not your turn."})
        return

    hi = seat["active_hand_index"]
    ph = seat["hands"][hi]
    if ph["status"] != "active":
        emit("error", {"message": "Hand is not active."})
        return

    act = data.get("action", "")
    opts = _options(ph, seat["bankroll"], len(seat["hands"]))

    if act == "hit":
        if not opts["can_hit"]:
            emit("error", {"message": "Cannot hit on 21."})
            return
        ph["hand"].append(_deal())
        _advance_seat()

    elif act == "stand":
        ph["status"] = "stood"
        _advance_seat()

    elif act == "double":
        if not opts["can_double"]:
            emit("error", {"message": "Cannot double down."})
            return
        seat["bankroll"] -= ph["bet"]
        ph["bet"] *= 2
        ph["hand"].append(_deal())
        ph["status"] = "doubled"
        _advance_seat()

    elif act == "split":
        if not opts["can_split"]:
            emit("error", {"message": "Cannot split."})
            return
        seat["bankroll"] -= ph["bet"]
        bet = ph["bet"]
        c1, c2 = ph["hand"]
        h1 = _make_hand([c1, _deal()], bet, from_split=True)
        h2 = _make_hand([c2, _deal()], bet, from_split=True)
        h2["status"] = "waiting"
        seat["hands"] = [h1, h2]
        seat["active_hand_index"] = 0
        ROOM["message"] = f"{seat['name']}: play hand 1."
        if bj.hand_value(h1["hand"]) == 21:
            h1["status"] = "stood"
            _advance_seat()

    else:
        emit("error", {"message": f"Unknown action '{act}'."})
        return

    _broadcast()


@socketio.on("new_round")
def on_new_round(data=None):
    sid = request.sid
    if not _find_seat(sid)[0]:
        return
    if ROOM["phase"] != "round_over":
        return

    for seat in ROOM["seats"].values():
        seat["hands"] = []
        seat["results"] = []
        seat["round_net"] = None
        seat["bet"] = 0
        seat["ready"] = False
        seat["active_hand_index"] = 0

    ROOM.update({
        "phase": "betting",
        "dealer_hand": [],
        "hole_hidden": True,
        "active_seat_index": 0,
        "message": "Place your bets!",
    })
    _broadcast()



# ── HTTP ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5001))
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)
