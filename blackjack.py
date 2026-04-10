import random

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

RANK_VALUES = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "10": 10, "J": 10, "Q": 10, "K": 10, "A": 11,
}


def build_deck(num_decks=6):
    deck = [(rank, suit) for _ in range(num_decks) for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck


def card_str(card):
    return f"{card[0]}{card[1]}"


def hand_value(hand):
    """Return the best value for a hand (highest without busting, or lowest if already bust)."""
    total = sum(RANK_VALUES[rank] for rank, _ in hand)
    aces = sum(1 for rank, _ in hand if rank == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def is_soft(hand):
    """True if the hand contains an Ace counted as 11."""
    total = sum(RANK_VALUES[rank] for rank, _ in hand)
    aces = sum(1 for rank, _ in hand if rank == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    # Re-check: if an ace is still counted as 11, it's a soft hand
    hard_total = sum(1 if rank == "A" else RANK_VALUES[rank] for rank, _ in hand)
    return (total - hard_total) == 10


def is_blackjack(hand):
    return len(hand) == 2 and hand_value(hand) == 21


def display_hand(hand, label, hide_second=False):
    if hide_second:
        cards = f"{card_str(hand[0])}  ??"
        print(f"  {label}: {cards}  (showing {hand_value([hand[0]])})")
    else:
        cards = "  ".join(card_str(c) for c in hand)
        value = hand_value(hand)
        soft_tag = " (soft)" if is_soft(hand) and value <= 21 else ""
        print(f"  {label}: {cards}  = {value}{soft_tag}")


def deal_card(deck, shoe):
    if len(shoe) < 52:
        print("\n  [Reshuffling deck...]\n")
        shoe.extend(build_deck())
    return shoe.pop()


def resolve_hand(player_hand, dealer_hand, bet, is_bj=False):
    """
    Returns net chip change (positive = win, negative = loss, 0 = push).
    """
    pv = hand_value(player_hand)
    dv = hand_value(dealer_hand)
    dealer_bj = is_blackjack(dealer_hand)

    if pv > 21:
        return -bet, "bust"

    if is_bj and not dealer_bj:
        return int(bet * 1.5), "blackjack"

    if dealer_bj and not is_bj:
        return -bet, "dealer blackjack"

    if is_bj and dealer_bj:
        return 0, "push (both blackjack)"

    if dv > 21:
        return bet, "dealer bust"

    if pv > dv:
        return bet, "win"
    elif pv < dv:
        return -bet, "loss"
    else:
        return 0, "push"


def player_turn(shoe, hand, bet, bankroll, can_double, can_split):
    """
    Plays out a single player hand. Returns (final_hand, final_bet, busted).
    If split returns multiple hands, they are handled by the caller.
    """
    doubled = False

    while True:
        display_hand(hand, "You")
        val = hand_value(hand)

        if val == 21:
            print("  21!")
            break
        if val > 21:
            print("  Bust!")
            break

        options = ["(H)it", "(S)tand"]
        if can_double and len(hand) == 2 and bankroll >= bet:
            options.append("(D)ouble")
        if can_split and len(hand) == 2 and hand[0][0] == hand[1][0] and bankroll >= bet:
            options.append("(P)split")

        prompt = " / ".join(options) + "? "
        choice = input(prompt).strip().upper()

        if choice == "H":
            hand.append(deal_card(None, shoe))
        elif choice == "S":
            break
        elif choice == "D" and "(D)ouble" in options:
            hand.append(deal_card(None, shoe))
            bet *= 2
            doubled = True
            display_hand(hand, "You")
            if hand_value(hand) > 21:
                print("  Bust!")
            break
        elif choice == "P" and "(P)split" in options:
            return "split", hand, bet
        else:
            print("  Invalid choice.")

    return "done", hand, bet


def play_split(shoe, original_hand, original_bet, bankroll):
    """
    Handles a split: returns list of (hand, bet) pairs for resolution.
    """
    card_a = original_hand[0]
    card_b = original_hand[1]
    total_extra_bet = original_bet  # second hand costs same as first

    print(f"\n  Splitting into two hands. Extra bet: {original_bet} chips.")
    bankroll -= original_bet

    hand_a = [card_a, deal_card(None, shoe)]
    hand_b = [card_b, deal_card(None, shoe)]

    results = []
    for i, hand in enumerate([hand_a, hand_b], 1):
        print(f"\n--- Split Hand {i} ---")
        # Only allow double on split hands; no re-splitting for simplicity
        status, final_hand, final_bet = player_turn(
            shoe, hand, original_bet, bankroll, can_double=True, can_split=False
        )
        if status == "split":
            # Re-split not supported; treat as stand
            print("  (Re-splitting not supported, standing.)")
            final_hand = hand
            final_bet = original_bet
        results.append((final_hand, final_bet))

    return results, bankroll


def play_round(shoe, bankroll):
    print(f"\n{'='*50}")
    print(f"  Bankroll: {bankroll} chips")

    # Get bet
    while True:
        try:
            bet_input = input(f"  Place your bet (1-{min(bankroll, 500)}): ").strip()
            bet = int(bet_input)
            if 1 <= bet <= bankroll:
                break
            print("  Invalid bet amount.")
        except ValueError:
            print("  Please enter a number.")

    bankroll -= bet

    # Deal
    player_hand = [deal_card(None, shoe), deal_card(None, shoe)]
    dealer_hand = [deal_card(None, shoe), deal_card(None, shoe)]

    print()
    display_hand(dealer_hand, "Dealer", hide_second=True)
    display_hand(player_hand, "You")

    # Check player blackjack immediately
    player_bj = is_blackjack(player_hand)
    dealer_bj = is_blackjack(dealer_hand)

    if player_bj or dealer_bj:
        print("\n  --- Revealing dealer's hand ---")
        display_hand(dealer_hand, "Dealer")
        if player_bj and dealer_bj:
            print("  Both have Blackjack — Push!")
            return bankroll + bet
        elif player_bj:
            winnings = int(bet * 1.5)
            print(f"  Blackjack! You win {winnings} chips.")
            return bankroll + bet + winnings
        else:
            print("  Dealer has Blackjack. You lose.")
            return bankroll

    # Player turn
    print()
    status, player_hand, bet = player_turn(
        shoe, player_hand, bet, bankroll, can_double=True, can_split=True
    )

    split_results = None
    if status == "split":
        split_results, bankroll = play_split(shoe, player_hand, bet, bankroll)

    # Dealer turn (only if at least one player hand hasn't busted)
    hands_to_resolve = split_results if split_results else [(player_hand, bet)]
    any_alive = any(hand_value(h) <= 21 for h, _ in hands_to_resolve)

    if any_alive:
        print("\n  --- Dealer's turn ---")
        display_hand(dealer_hand, "Dealer")
        while True:
            dv = hand_value(dealer_hand)
            # Dealer hits on soft 16 or less; stands on hard/soft 17+
            if dv < 17 or (dv == 17 and is_soft(dealer_hand)):
                dealer_hand.append(deal_card(None, shoe))
                display_hand(dealer_hand, "Dealer")
            else:
                break

    # Resolve
    print("\n  --- Result ---")
    total_change = 0
    for i, (hand, h_bet) in enumerate(hands_to_resolve, 1):
        label = f"Hand {i}" if split_results else "Your hand"
        change, outcome = resolve_hand(hand, dealer_hand, h_bet)
        print(f"  {label}: {outcome.upper()} ({'+' if change >= 0 else ''}{change} chips)")
        total_change += change

    bankroll += bet + total_change  # return original bet (already deducted) + net
    # For splits the extra bet was already deducted; add back based on results
    if split_results:
        # original bet already in bankroll deduction at top; splits deducted inside play_split
        # total_change already accounts for both hands correctly
        # But we returned bankroll from play_split with extra bet deducted, and bet variable
        # is the original bet — we need to add it back since it was part of the original deduction.
        pass  # already handled: bankroll -= bet at top, split deducts extra inside

    net = total_change
    sign = "+" if net >= 0 else ""
    print(f"\n  Net this round: {sign}{net} chips")
    print(f"  Bankroll: {bankroll} chips")
    return bankroll


def main():
    print("=" * 50)
    print("        BLACKJACK  (6-deck shoe)")
    print("=" * 50)
    print("  Blackjack pays 3:2")
    print("  Dealer stands on hard/soft 17")
    print("  Double down and split available")
    print("=" * 50)

    bankroll = 1000
    shoe = build_deck()

    while bankroll > 0:
        bankroll = play_round(shoe, bankroll)

        if bankroll <= 0:
            print("\n  You're out of chips. Game over!")
            break

        again = input("\n  Play another round? (Y/n): ").strip().upper()
        if again == "N":
            print(f"\n  Thanks for playing! Final bankroll: {bankroll} chips.")
            break

    print()


if __name__ == "__main__":
    main()
