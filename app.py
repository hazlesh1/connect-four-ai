import os
import secrets

from easyAI import Negamax, TwoPlayerGame
from flask import Flask, redirect, render_template_string, request, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

ROWS = 6
COLUMNS = 7
EMPTY = 0
HUMAN = 1
COMPUTER = 2
DIFFICULTIES = {"Easy": 2, "Medium": 3, "Hard": 4}


def empty_board():
    board = []
    for row in range(ROWS):
        board.append([EMPTY] * COLUMNS)
    return board


def get_groups_of_four():
    groups = []
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    for row in range(ROWS):
        for column in range(COLUMNS):
            for row_step, column_step in directions:
                end_row = row + 3 * row_step
                end_column = column + 3 * column_step
                if not (0 <= end_row < ROWS and 0 <= end_column < COLUMNS):
                    continue
                group = []
                for i in range(4):
                    group.append((row + i * row_step, column + i * column_step))
                groups.append(group)
    return groups


GROUPS = get_groups_of_four()


def winning_cells(board):
    for group in GROUPS:
        row, column = group[0]
        player = board[row][column]
        if player == EMPTY:
            continue
        matching = True
        for row, column in group:
            if board[row][column] != player:
                matching = False
                break
        if matching:
            return group
    return []


def get_winner(board):
    cells = winning_cells(board)
    if cells:
        row, column = cells[0]
        return board[row][column]
    return EMPTY


def valid_columns(board):
    columns = []
    for column in range(COLUMNS):
        if board[0][column] == EMPTY:
            columns.append(column)
    return columns


def round_finished(board):
    return get_winner(board) != EMPTY or len(valid_columns(board)) == 0


def drop_piece(board, column, player):
    if column not in valid_columns(board):
        raise ValueError("That column is full or outside the board.")
    for row in range(ROWS - 1, -1, -1):
        if board[row][column] == EMPTY:
            board[row][column] = player
            return


class ConnectFourAI(TwoPlayerGame):
    def __init__(self, board, player=COMPUTER):
        self.board = []
        for row in board:
            self.board.append(row.copy())
        self.current_player = player
        self.players = [None, None]

    def possible_moves(self):
        moves = []
        for column in [3, 2, 4, 1, 5, 0, 6]:
            if self.board[0][column] == EMPTY:
                moves.append(column)
        return moves

    def make_move(self, column):
        drop_piece(self.board, column, self.current_player)

    def is_over(self):
        return round_finished(self.board)

    def copy(self):
        return ConnectFourAI(self.board, self.current_player)

    def scoring(self):
        player = self.current_player
        opponent = 3 - player
        winner = get_winner(self.board)
        if winner == player:
            return 100000
        if winner == opponent:
            return -100000
        if len(valid_columns(self.board)) == 0:
            return 0

        score = 0
        for row in self.board:
            if row[3] == player:
                score += 4
            elif row[3] == opponent:
                score -= 4

        points = [0, 2, 16, 110, 100000]
        for group in GROUPS:
            own_pieces = 0
            opponent_pieces = 0
            for row, column in group:
                if self.board[row][column] == player:
                    own_pieces += 1
                elif self.board[row][column] == opponent:
                    opponent_pieces += 1
            if opponent_pieces == 0:
                score += points[own_pieces]
            elif own_pieces == 0:
                score -= points[opponent_pieces]
        return score


def computer_move(game):
    depth = DIFFICULTIES[game["difficulty"]]
    search = Negamax(depth)
    position = ConnectFourAI(game["board"])
    column = search(position)
    drop_piece(game["board"], column, COMPUTER)


def new_game(difficulty):
    return {
        "board": empty_board(),
        "difficulty": difficulty,
        "started": False,
        "starter": HUMAN,
    }


def start_round(game, difficulty):
    if game["started"] and not round_finished(game["board"]):
        raise ValueError("Finish the current round first.")
    if difficulty not in DIFFICULTIES:
        raise ValueError("Choose Easy, Medium or Hard.")
    game = new_game(difficulty)
    game["started"] = True
    game["starter"] = secrets.choice([HUMAN, COMPUTER])
    if game["starter"] == COMPUTER:
        computer_move(game)
    return game


def play_turn(game, column, scores):
    if not game["started"] or round_finished(game["board"]):
        raise ValueError("Start a new round first.")
    drop_piece(game["board"], column, HUMAN)
    if not round_finished(game["board"]):
        computer_move(game)
    if round_finished(game["board"]):
        winner = get_winner(game["board"])
        if winner == HUMAN:
            scores["wins"] += 1
        elif winner == COMPUTER:
            scores["losses"] += 1
        else:
            scores["draws"] += 1


def turn_message(game):
    if not game["started"]:
        return "Choose diff"
    winner = get_winner(game["board"])
    if winner == HUMAN:
        return "You win!"
    if winner == COMPUTER:
        return "Computer wins!"
    if round_finished(game["board"]):
        return "Draw!"
    return "Click a collumn"


@app.route("/", methods=["GET", "POST"])
def index():
    game = session.get("game", new_game("Medium"))
    scores = session.get("scores", {"wins": 0, "losses": 0, "draws": 0})
    token = session.setdefault("token", secrets.token_hex(16))
    if request.method == "POST":
        submitted_token = request.form.get("token", "")
        if not secrets.compare_digest(submitted_token, token):
            return "RELOAD PAGEE", 400
        error = ""
        action = request.form.get("action")
        try:
            if action == "start":
                difficulty = request.form.get("difficulty", "Medium")
                game = start_round(game, difficulty)
            elif action == "move":
                try:
                    column = int(request.form.get("column", ""))
                except ValueError:
                    raise ValueError("Choose a collumn") from None
                play_turn(game, column, scores)
            else:
                raise ValueError("Use the buttons below")
        except ValueError as problem:
            error = str(problem)
        session["game"] = game
        session["scores"] = scores
        session["error"] = error
        session["token"] = secrets.token_hex(16)
        return redirect("/", code=303)

    playing = game["started"] and not round_finished(game["board"])
    return render_template_string(
        PAGE,
        game=game,
        scores=scores,
        token=token,
        message=turn_message(game),
        error=session.pop("error", ""),
        playing=playing,
        winning=winning_cells(game["board"]),
        difficulties=DIFFICULTIES,
    )


PAGE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Connect 4 prototype</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 24px auto; padding: 12px; max-width: 520px; }
        h1 { font-size: 28px; }
        button, select { font: inherit; padding: 8px; }
        button { cursor: pointer; }
        button:disabled { cursor: default; }
        .columns, .board { display: grid; grid-template-columns: repeat(7, 1fr); gap: 7px; }
        .columns { margin-top: 20px; padding: 0 10px; }
        .board { background: royalblue; padding: 10px; margin-top: 8px; }
        .cell { aspect-ratio: 1; border-radius: 50%; background: white; }
        .red { background: red; }
        .yellow { background: gold; }
        .winning { outline: 4px solid black; outline-offset: -5px; }
        .error { color: darkred; }
        .scores { margin-top: 20px; }
    </style>
</head>
<body>
    <h1>Connect 4 prototype</h1>
    <p>You are red. The computer is yellow.</p>
    <form method="post">
        <input type="hidden" name="token" value="{{ token }}">
        <input type="hidden" name="action" value="start">
        <label for="difficulty">Difficulty:</label>
        <select id="difficulty" name="difficulty" {% if playing %}disabled{% endif %}>
            {% for difficulty in difficulties %}
                <option {% if difficulty == game.difficulty %}selected{% endif %}>{{ difficulty }}</option>
            {% endfor %}
        </select>
        <button {% if playing %}disabled{% endif %}>Start / New round</button>
    </form>
    <p role="status"><strong>{{ message }}</strong></p>
    {% if error %}<p class="error" role="alert">{{ error }}</p>{% endif %}
    <form method="post" class="columns">
        <input type="hidden" name="token" value="{{ token }}">
        <input type="hidden" name="action" value="move">
        {% for column in range(7) %}
            <button name="column" value="{{ column }}"
                aria-label="Drop in column {{ column + 1 }}"
                {% if not playing or game.board[0][column] != 0 %}disabled{% endif %}>
                {{ column + 1 }}
            </button>
        {% endfor %}
    </form>
    <div class="board">
        {% for row in range(6) %}
            {% for column in range(7) %}
                {% set piece = game.board[row][column] %}
                <div class="cell {% if piece == 1 %}red{% elif piece == 2 %}yellow{% endif %}
                    {% if (row, column) in winning %}winning{% endif %}"
                    role="img" aria-label="Row {{ row + 1 }}, column {{ column + 1 }}:
                    {% if piece == 1 %}red{% elif piece == 2 %}yellow{% else %}empty{% endif %}"></div>
            {% endfor %}
        {% endfor %}
    </div>
    <p class="scores">Wins: {{ scores.wins }} | Losses: {{ scores.losses }} | Draws: {{ scores.draws }}</p>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))

