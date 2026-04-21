# Blackjack Game

A classic blackjack game with two play modes: a terminal CLI and a browser-based web UI. Built with Python and Flask.

## Prerequisites

- [Conda](https://docs.conda.io/en/latest/miniconda.html) (Miniconda or Anaconda)

## Setup

```bash
conda env create -f environment.yml
conda activate blackjack
```

## Running the Game

### Web UI (recommended)

```bash
python app.py
```

Then open [http://localhost:5001](http://localhost:5001) in your browser. Stop the server with `Ctrl+C`.

> **Note (macOS):** Port 5000 is reserved by AirPlay Receiver, so the app runs on port 5001 instead. To use port 5000, disable AirPlay Receiver in System Settings → General → AirDrop & Handoff, then change `port=5001` to `port=5000` in the last line of `app.py`.

### CLI

```bash
python blackjack.py
```

Play entirely in the terminal. Exit at any time with `Ctrl+C`, or choose `N` when prompted after a round.

## Game Rules

- **Shoe:** 6 decks, reshuffled automatically when fewer than 52 cards remain
- **Blackjack pays:** 3:2
- **Dealer:** hits on soft 17, stands on hard 17+
- **Player options:** hit, stand, double down, split (pairs only, no re-split)
- **Starting bankroll:** 1,000 chips
- **Maximum bet per round:** 500 chips
- Blackjack on a split hand pays even money (standard casino rule)

## Project Structure

```
blackjack.py      # Core game logic and CLI entry point
app.py            # Flask API server
templates/        # HTML template for the web UI
static/           # CSS and JavaScript for the web UI
environment.yml   # Conda environment spec
```
