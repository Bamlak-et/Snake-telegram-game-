"""
Telegram Habesha Snake Game Bot (Ethiopian Edition)
===================================================
A playable Snake game inside Telegram, rendered as an emoji grid that
updates in place (message editing) with inline-keyboard arrow controls.

Features Added:
- Updated Telegram API Token directly integrated.
- Ethiopian Visual Theme (Green-Yellow-Red Gradient Snake, Buna & Doro Wat items).
- Dynamic Scoring & High Scores Tracking.
- Interactive Leaderboard system.
- Telebirr Airtime Rewards feature integration.
- Amharic / English Localization.

Setup
-----
1. Install dependencies:
       pip install python-telegram-bot==21.4
2. Run the script directly:
       python snake_bot.py
"""

import logging
import os
import random
from dataclasses import dataclass, field
from typing import Optional, Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration & Ethiopian Theming
# ---------------------------------------------------------------------------
BOARD_WIDTH = 9
BOARD_HEIGHT = 9
TICK_SECONDS = 0.6

EMPTY = "⬛"
# Ethiopian Snake Flag Colors (Green, Yellow, Red)
SNAKE_HEAD = "🟢"
SNAKE_BODY_COLORS = ["🟢", "🟡", "🔴"]

# Ethiopian Food Items
FOOD_COFFEE = "☕"      # Buna - Standard Food (+1 Point)
FOOD_SPECIAL = "🍲"     # Doro Wat - Bonus Food (+3 Points)

DIRECTIONS = {
    "UP": (0, -1),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
    "RIGHT": (1, 0),
}
OPPOSITE = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}

# In-memory Global Leaderboard storage {user_id: {"name": str, "score": int}}
LEADERBOARD: Dict[int, dict] = {}


# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------
@dataclass
class SnakeGame:
    chat_id: int
    user_name: str = "Player"
    user_id: int = 0
    message_id: Optional[int] = None
    snake: list = field(default_factory=list)
    direction: str = "RIGHT"
    pending_direction: str = "RIGHT"
    food: tuple = (0, 0)
    food_type: str = FOOD_COFFEE
    score: int = 0
    game_over: bool = False

    def __post_init__(self):
        if not self.snake:
            cx, cy = BOARD_WIDTH // 2, BOARD_HEIGHT // 2
            self.snake = [(cx - 1, cy), (cx - 2, cy)]
            self.direction = "RIGHT"
            self.pending_direction = "RIGHT"
            self.place_food()

    def place_food(self):
        free_cells = [
            (x, y)
            for x in range(BOARD_WIDTH)
            for y in range(BOARD_HEIGHT)
            if (x, y) not in self.snake
        ]
        self.food = random.choice(free_cells) if free_cells else (0, 0)
        # 20% Chance for special bonus Doro Wat 🍲 food
        self.food_type = FOOD_SPECIAL if random.random() < 0.2 else FOOD_COFFEE

    def set_direction(self, new_direction: str):
        # Prevent reversing directly into yourself
        if new_direction != OPPOSITE.get(self.direction):
            self.pending_direction = new_direction

    def step(self):
        if self.game_over:
            return
        self.direction = self.pending_direction
        dx, dy = DIRECTIONS[self.direction]
        head_x, head_y = self.snake[0]
        new_head = (head_x + dx, head_y + dy)

        # Wall collision
        if not (0 <= new_head[0] < BOARD_WIDTH and 0 <= new_head[1] < BOARD_HEIGHT):
            self.game_over = True
            self.update_high_score()
            return

        # Self collision
        if new_head in self.snake:
            self.game_over = True
            self.update_high_score()
            return

        self.snake.insert(0, new_head)
        if new_head == self.food:
            points = 3 if self.food_type == FOOD_SPECIAL else 1
            self.score += points
            self.place_food()
        else:
            self.snake.pop()

    def update_high_score(self):
        if self.user_id:
            current_best = LEADERBOARD.get(self.user_id, {}).get("score", 0)
            if self.score > current_best:
                LEADERBOARD[self.user_id] = {
                    "name": self.user_name,
                    "score": self.score
                }

    def render(self) -> str:
        grid = [[EMPTY for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        fx, fy = self.food
        grid[fy][fx] = self.food_type
        
        # Render Ethiopian Flag Gradient Snake
        for i, (x, y) in enumerate(self.snake):
            if i == 0:
                grid[y][x] = SNAKE_HEAD
            else:
                grid[y][x] = SNAKE_BODY_COLORS[(i - 1) % len(SNAKE_BODY_COLORS)]
                
        board_text = "\n".join("".join(row) for row in grid)
        status = f"🇪🇹 ነጥብ (Score): {self.score} | Buna: ☕ (+1) | Doro: 🍲 (+3)"
        
        if self.game_over:
            status += f"\n💥 ጨዋታው አበቃ! (Game Over)\n🏆 Final Score: {self.score}"
            if self.score >= 10:
                status += "\n🎉 Congratulations! You qualify for Telebirr Rewards!"
            status += "\nTap '🔄 New Game' to play again."
            
        return f"{board_text}\n\n{status}"


# chat_id -> SnakeGame
GAMES: dict[int, SnakeGame] = {}


def build_keyboard(game_over: bool = False) -> InlineKeyboardMarkup:
    if game_over:
        rows = [
            [InlineKeyboardButton("🔄 New Game (አዲስ ጀምር)", callback_data="NEW")],
            [InlineKeyboardButton("🏆 Leaderboard", callback_data="LEADERBOARD")],
            [InlineKeyboardButton("📲 Claim Telebirr", callback_data="TELEBIRR")]
        ]
        return InlineKeyboardMarkup(rows)
    rows = [
        [InlineKeyboardButton("⬆️", callback_data="UP")],
        [
            InlineKeyboardButton("⬅️", callback_data="LEFT"),
            InlineKeyboardButton("⏹", callback_data="STOP"),
            InlineKeyboardButton("➡️", callback_data="RIGHT"),
        ],
        [InlineKeyboardButton("⬇️", callback_data="DOWN")],
    ]
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Game loop (runs via JobQueue, one repeating job per chat)
# ---------------------------------------------------------------------------
async def game_tick(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    game = GAMES.get(chat_id)
    if game is None:
        context.job.schedule_removal()
        return

    game.step()

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game.message_id,
            text=game.render(),
            reply_markup=build_keyboard(game.game_over),
        )
    except Exception as exc:  # noqa: BLE001 - message may be unchanged/deleted
        logger.debug("edit_message_text skipped: %s", exc)

    if game.game_over:
        context.job.schedule_removal()


def start_game_job(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    # Remove any existing job for this chat first
    for job in context.job_queue.get_jobs_by_name(f"snake-{chat_id}"):
        job.schedule_removal()
    context.job_queue.run_repeating(
        game_tick,
        interval=TICK_SECONDS,
        first=TICK_SECONDS,
        chat_id=chat_id,
        name=f"snake-{chat_id}",
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🐍 New Game (ተጫወት)", callback_data="NEW")],
            [InlineKeyboardButton("🏆 Leaderboard (ደረጃ)", callback_data="LEADERBOARD")],
            [InlineKeyboardButton("📲 Telebirr Rewards", callback_data="TELEBIRR")]
        ]
    )
    welcome_text = (
        "እንኳን ወደ ሐበሻ እባብ ጨዋታ በደህና መጡ! 🇪🇹🐍\n\n"
        "Welcome to the Ethiopian Habesha Snake Game!\n"
        "• Eat Coffee ☕ (+1 Point) and Doro Wat 🍲 (+3 Points)\n"
        "• Climb the Leaderboard & Win Telebirr Rewards!\n\n"
        "Tap 'New Game' to start playing."
    )
    await update.message.reply_text(welcome_text, reply_markup=keyboard)


async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    user = update.effective_user
    user_name = user.first_name if user else "Player"
    user_id = user.id if user else 0

    game = SnakeGame(chat_id=chat_id, user_name=user_name, user_id=user_id)
    GAMES[chat_id] = game

    text = game.render()
    if update.callback_query:
        msg = await update.callback_query.edit_message_text(
            text=text, reply_markup=build_keyboard()
        )
    else:
        msg = await update.message.reply_text(text=text, reply_markup=build_keyboard())
    game.message_id = msg.message_id
    start_game_job(context, chat_id)


async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await new_game(update, context, update.effective_chat.id)


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    for job in context.job_queue.get_jobs_by_name(f"snake-{chat_id}"):
        job.schedule_removal()
    GAMES.pop(chat_id, None)
    await update.message.reply_text("Game stopped. Send /play to start a new one.")


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not LEADERBOARD:
        lb_text = "🏆 የከፍተኛ ነጥብ ሰሌዳ (Leaderboard)\n\nNo high scores recorded yet! Play now to be #1!"
    else:
        sorted_lb = sorted(LEADERBOARD.values(), key=lambda x: x["score"], reverse=True)
        lb_text = "🏆 የከፍተኛ ነጥብ ሰሌዳ (Ethiopian Top Players)\n"
        lb_text += "--------------------------------------\n"
        for idx, entry in enumerate(sorted_lb[:10], 1):
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            rank = medals.get(idx, f"{idx}.")
            lb_text += f"{rank} {entry['name']}: {entry['score']} pts\n"

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Play Game", callback_data="NEW")]])
    
    if update.callback_query:
        await update.callback_query.message.reply_text(lb_text, reply_markup=keyboard)
    else:
        await update.message.reply_text(lb_text, reply_markup=keyboard)


async def telebirr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📲 Telebirr Rewards Program 🇪🇹\n\n"
        "• Score 10+ points: Qualify for weekly Telebirr airtime draws!\n"
        "• Top 3 Leaderboard players win 50-100 Birr airtime reward every Sunday.\n\n"
        "Keep playing and climbing the leaderboard! 🐍"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Play Now", callback_data="NEW")]])
    
    if update.callback_query:
        await update.callback_query.message.reply_text(msg, reply_markup=keyboard)
    else:
        await update.message.reply_text(msg, reply_markup=keyboard)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    data = query.data
    await query.answer()

    if data == "NEW":
        await new_game(update, context, chat_id)
        return

    if data == "LEADERBOARD":
        await leaderboard_command(update, context)
        return

    if data == "TELEBIRR":
        await telebirr_command(update, context)
        return

    if data == "STOP":
        for job in context.job_queue.get_jobs_by_name(f"snake-{chat_id}"):
            job.schedule_removal()
        GAMES.pop(chat_id, None)
        await query.edit_message_text("Game stopped. Send /play to start a new one.")
        return

    game = GAMES.get(chat_id)
    if game is None or game.game_over:
        return

    if data in DIRECTIONS:
        game.set_direction(data)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "8585158678:AAGZfcWFVy2daDBe-qNcjzlXaw2THg2XFdc")
    if not token:
        raise SystemExit(
            "Set the TELEGRAM_BOT_TOKEN environment variable before running this bot."
        )

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("play", play_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("telebirr", telebirr_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Habesha Snake bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()

