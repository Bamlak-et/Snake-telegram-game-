#!/usr/bin/env python3
"""
NOKIA SNAKE × GEN Z  — The ultimate Telegram Snake experience
Classic Nokia vibes + modern Gen Z energy for Telegram.
"""

import asyncio
import random
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ==================== CONFIG ====================
BOT_TOKEN = "8585158678:AAGZfcWFVy2daDBe-qNcjzlXaw2THg2XFdc"

GRID_W = 11
GRID_H = 11
TICK_BASE = 0.45  # seconds between moves (classic feel)

# ==================== THEMES (Nokia core + Gen Z) ====================
THEMES = {
    "nokia": {
        "name": "📱 Classic Nokia",
        "empty": "⬛",
        "body": "🟩",
        "head": "🟢",
        "food": "🍎",
        "power": "⚡",
        "wall": "⬛",
        "desc": "Pure 3310 energy. Green on black. No distractions.",
    },
    "neon": {
        "name": "🌃 Neon Cyber",
        "empty": "⬛",
        "body": "🟦",
        "head": "💠",
        "food": "💜",
        "power": "✨",
        "wall": "⬛",
        "desc": "Night city vibes. Cyberpunk snake mode activated.",
    },
    "pastel": {
        "name": "🎀 Pastel Core",
        "empty": "⬜",
        "body": "🩷",
        "head": "🌸",
        "food": "🧁",
        "power": "💫",
        "wall": "⬜",
        "desc": "Soft girl / soft boy energy. Cute but deadly.",
    },
    "meme": {
        "name": "🗿 Meme Mode",
        "empty": "⬛",
        "body": "💀",
        "head": "🗿",
        "food": "🔥",
        "power": "🤡",
        "wall": "⬛",
        "desc": "Absolute cinema. Sigma snake only.",
    },
    "y2k": {
        "name": "💿 Y2K Glitch",
        "empty": "⬛",
        "body": "🩵",
        "head": "💿",
        "food": "⭐",
        "power": "🪩",
        "wall": "⬛",
        "desc": "Early 2000s internet aesthetic. Glitch in the matrix.",
    },
}

DIFFICULTIES = {
    "chill": {"name": "😌 Chill", "mult": 1.3, "score_mult": 0.8, "desc": "Slow & cozy. Touch grass friendly."},
    "mid": {"name": "😐 Mid", "mult": 1.0, "score_mult": 1.0, "desc": "Classic Nokia speed. Balanced."},
    "sigma": {"name": "🗿 Sigma", "mult": 0.65, "score_mult": 1.6, "desc": "Only the goated survive. Fast."},
}

# Gen Z game over lines
GAME_OVER_LINES = [
    "Skill issue fr 💀",
    "You got cooked by the walls no cap",
    "That was mid... touch grass",
    "L + ratio + wall collision",
    "Bro thought he was built different 🗿",
    "The snake said 'not today'",
    "NPC energy detected",
    "You ate the L instead of the apple",
    "Main character arc cancelled",
    "This ain't it chief",
    "Womp womp 📢",
    "Even the 3310 is disappointed",
]

WIN_LINES = [  # for high scores
    "GOATED run no cap 🐐",
    "You cooked so hard the kitchen is on fire 🔥",
    "Absolute cinema 🎬",
    "Sigma grindset activated",
    "This score hits different",
    "Main character energy unlocked",
    "Rizz levels: maximum",
    "You ate and left no crumbs",
]

# ==================== DATA ====================
class Direction(Enum):
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

@dataclass
class PowerUp:
    kind: str  # "turbo", "ghost", "double"
    remaining: int

@dataclass
class GameState:
    user_id: int
    chat_id: int
    message_id: Optional[int] = None
    snake: List[Tuple[int, int]] = field(default_factory=list)
    direction: Direction = Direction.RIGHT
    next_direction: Direction = Direction.RIGHT
    food: Tuple[int, int] = (0, 0)
    score: int = 0
    high_score: int = 0
    alive: bool = True
    paused: bool = False
    theme: str = "nokia"
    difficulty: str = "mid"
    power: Optional[PowerUp] = None
    tick_task: Optional[asyncio.Task] = None
    moves: int = 0
    food_eaten: int = 0

# In-memory games + simple highscores
games: Dict[int, GameState] = {}
user_highscores: Dict[int, int] = {}  # will also sync to DB

# ==================== DATABASE ====================
def init_db():
    conn = sqlite3.connect("snake_scores.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            high_score INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            total_food INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def get_high_score(user_id: int) -> int:
    conn = sqlite3.connect("snake_scores.db")
    c = conn.cursor()
    c.execute("SELECT high_score FROM scores WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def update_score(user_id: int, username: str, score: int, food: int):
    conn = sqlite3.connect("snake_scores.db")
    c = conn.cursor()
    c.execute("SELECT high_score, games_played, total_food FROM scores WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row:
        high, games_p, total_f = row
        new_high = max(high, score)
        c.execute(
            "UPDATE scores SET high_score=?, games_played=?, total_food=?, username=? WHERE user_id=?",
            (new_high, games_p + 1, total_f + food, username or "anon", user_id),
        )
    else:
        c.execute(
            "INSERT INTO scores (user_id, username, high_score, games_played, total_food) VALUES (?,?,?,?,?)",
            (user_id, username or "anon", score, 1, food),
        )
    conn.commit()
    conn.close()

def get_leaderboard(limit: int = 10) -> List[Tuple]:
    conn = sqlite3.connect("snake_scores.db")
    c = conn.cursor()
    c.execute(
        "SELECT username, high_score, games_played FROM scores ORDER BY high_score DESC LIMIT ?",
        (limit,),
    )
    rows = c.fetchall()
    conn.close()
    return rows

# ==================== GAME LOGIC ====================
def new_game(user_id: int, chat_id: int, theme: str = "nokia", difficulty: str = "mid") -> GameState:
    mid_x, mid_y = GRID_W // 2, GRID_H // 2
    snake = [(mid_x - 1, mid_y), (mid_x, mid_y), (mid_x + 1, mid_y)]  # head is last
    state = GameState(
        user_id=user_id,
        chat_id=chat_id,
        snake=snake,
        direction=Direction.RIGHT,
        next_direction=Direction.RIGHT,
        theme=theme,
        difficulty=difficulty,
        high_score=get_high_score(user_id),
    )
    place_food(state)
    return state

def place_food(state: GameState):
    empty = [(x, y) for x in range(GRID_W) for y in range(GRID_H) if (x, y) not in state.snake]
    if not empty:
        return
    state.food = random.choice(empty)
    # 12% chance of power-up food
    if random.random() < 0.12 and state.power is None:
        state.power = PowerUp(kind=random.choice(["turbo", "ghost", "double"]), remaining=12)

def render_board(state: GameState) -> str:
    t = THEMES[state.theme]
    board = [[t["empty"] for _ in range(GRID_W)] for _ in range(GRID_H)]

    # body
    for i, (x, y) in enumerate(state.snake[:-1]):
        board[y][x] = t["body"]
    # head
    hx, hy = state.snake[-1]
    board[hy][hx] = t["head"]

    # food / power
    fx, fy = state.food
    if state.power and state.power.remaining > 0:
        board[fy][fx] = t["power"]
    else:
        board[fy][fx] = t["food"]

    lines = ["".join(row) for row in board]
    return "\n".join(lines)

def get_status_text(state: GameState) -> str:
    t = THEMES[state.theme]
    d = DIFFICULTIES[state.difficulty]
    power_txt = ""
    if state.power and state.power.remaining > 0:
        icons = {"turbo": "⚡ TURBO", "ghost": "👻 GHOST", "double": "💎 x2 SCORE"}
        power_txt = f"\n{icons.get(state.power.kind, '✨')} ({state.power.remaining})"

    status = (
        f"{t['name']}  •  {d['name']}\n"
        f"Score: <b>{state.score}</b>  |  Best: {state.high_score}\n"
        f"Food: {state.food_eaten}{power_txt}"
    )
    if state.paused:
        status += "\n\n⏸ <i>PAUSED — tap Resume</i>"
    return status

def move_snake(state: GameState) -> bool:
    """Returns True if still alive"""
    if not state.alive or state.paused:
        return state.alive

    state.direction = state.next_direction
    dx, dy = state.direction.value
    hx, hy = state.snake[-1]
    new_head = (hx + dx, hy + dy)

    # wall collision
    if not (0 <= new_head[0] < GRID_W and 0 <= new_head[1] < GRID_H):
        state.alive = False
        return False

    # self collision (unless ghost)
    ghost = state.power and state.power.kind == "ghost" and state.power.remaining > 0
    if new_head in state.snake and not ghost:
        state.alive = False
        return False

    state.snake.append(new_head)
    state.moves += 1

    # eat?
    ate = new_head == state.food
    if ate:
        base = 10
        if state.power and state.power.kind == "double" and state.power.remaining > 0:
            base *= 2
        mult = DIFFICULTIES[state.difficulty]["score_mult"]
        state.score += int(base * mult)
        state.food_eaten += 1
        place_food(state)
    else:
        state.snake.pop(0)

    # tick power
    if state.power:
        state.power.remaining -= 1
        if state.power.remaining <= 0:
            state.power = None

    return True

def controls_keyboard(state: GameState) -> InlineKeyboardMarkup:
    if not state.alive:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Play Again", callback_data="restart"),
                    InlineKeyboardButton(text="🎨 Themes", callback_data="menu_themes"),
                ],
                [
                    InlineKeyboardButton(text="🏆 Leaderboard", callback_data="leaderboard"),
                    InlineKeyboardButton(text="🏠 Menu", callback_data="main_menu"),
                ],
            ]
        )

    pause_btn = "▶️ Resume" if state.paused else "⏸ Pause"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬆️", callback_data="dir_UP"),
            ],
            [
                InlineKeyboardButton(text="⬅️", callback_data="dir_LEFT"),
                InlineKeyboardButton(text="⏹", callback_data="quit"),
                InlineKeyboardButton(text="➡️", callback_data="dir_RIGHT"),
            ],
            [
                InlineKeyboardButton(text="⬇️", callback_data="dir_DOWN"),
            ],
            [
                InlineKeyboardButton(text=pause_btn, callback_data="pause"),
            ],
        ]
    )

# ==================== BOT ====================
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
bot = Bot(token=BOT_TOKEN)


class Setup(StatesGroup):
    choosing_theme = State()
    choosing_diff = State()


async def game_loop(user_id: int):
    """Background tick for continuous movement"""
    while user_id in games:
        state = games[user_id]
        if not state.alive:
            break
        if state.paused:
            await asyncio.sleep(0.2)
            continue

        alive = move_snake(state)
        try:
            text = f"{render_board(state)}\n\n{get_status_text(state)}"
            await bot.edit_message_text(
                chat_id=state.chat_id,
                message_id=state.message_id,
                text=text,
                reply_markup=controls_keyboard(state),
                parse_mode="HTML",
            )
        except Exception:
            pass  # message not modified or deleted

        if not alive:
            await end_game(state)
            break

        # speed
        mult = DIFFICULTIES[state.difficulty]["mult"]
        if state.power and state.power.kind == "turbo" and state.power.remaining > 0:
            mult *= 0.55
        await asyncio.sleep(TICK_BASE * mult)


async def end_game(state: GameState):
    username = None
    try:
        user = await bot.get_chat(state.user_id)
        username = user.username or user.first_name
    except Exception:
        username = "player"

    update_score(state.user_id, username, state.score, state.food_eaten)
    state.high_score = max(state.high_score, state.score)

    if state.score >= 150:
        line = random.choice(WIN_LINES)
    else:
        line = random.choice(GAME_OVER_LINES)

    t = THEMES[state.theme]
    final = (
        f"{render_board(state)}\n\n"
        f"☠️ <b>GAME OVER</b>\n"
        f"{line}\n\n"
        f"Final Score: <b>{state.score}</b>\n"
        f"Food eaten: {state.food_eaten}\n"
        f"Personal best: {state.high_score}\n\n"
        f"<i>{t['desc']}</i>"
    )
    try:
        await bot.edit_message_text(
            chat_id=state.chat_id,
            message_id=state.message_id,
            text=final,
            reply_markup=controls_keyboard(state),
            parse_mode="HTML",
        )
    except Exception:
        pass

    # clean task
    if state.tick_task and not state.tick_task.done():
        state.tick_task.cancel()
    if state.user_id in games:
        del games[state.user_id]


# ---------- Handlers ----------
@dp.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "🐍 <b>NOKIA SNAKE × GEN Z</b>\n\n"
        "The classic 3310 snake… but it hits different now.\n\n"
        "• Real continuous movement (not turn-based)\n"
        "• 5 aesthetic themes\n"
        "• Power-ups: ⚡ Turbo • 👻 Ghost • 💎 Double\n"
        "• Chill / Mid / Sigma difficulties\n"
        "• Global leaderboard + Gen Z commentary\n\n"
        "Ready to lock in?"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Play Now", callback_data="play")],
            [
                InlineKeyboardButton(text="🎨 Themes", callback_data="menu_themes"),
                InlineKeyboardButton(text="🏆 Leaderboard", callback_data="leaderboard"),
            ],
            [InlineKeyboardButton(text="ℹ️ How to play", callback_data="help")],
        ]
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "main_menu")
async def main_menu(cb: CallbackQuery):
    await cb.answer()
    text = (
        "🐍 <b>NOKIA SNAKE × GEN Z</b>\n\n"
        "The classic 3310 snake… but it hits different now.\n\n"
        "Ready to lock in?"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Play Now", callback_data="play")],
            [
                InlineKeyboardButton(text="🎨 Themes", callback_data="menu_themes"),
                InlineKeyboardButton(text="🏆 Leaderboard", callback_data="leaderboard"),
            ],
            [InlineKeyboardButton(text="ℹ️ How to play", callback_data="help")],
        ]
    )
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "help")
async def help_cb(cb: CallbackQuery):
    await cb.answer()
    text = (
        "<b>How to play</b>\n\n"
        "• Use the arrow buttons to change direction\n"
        "• Snake moves automatically (classic Nokia feel)\n"
        "• Eat food to grow & score points\n"
        "• ⚡ / 👻 / 💎 appear sometimes — grab them!\n"
        "  - Turbo = faster moves\n"
        "  - Ghost = pass through yourself\n"
        "  - Double = x2 points for a bit\n"
        "• Hit walls or yourself = game over\n\n"
        "<b>Difficulties</b>\n"
        "😌 Chill — slow, lower score mult\n"
        "😐 Mid — authentic Nokia speed\n"
        "🗿 Sigma — fast, higher score mult\n\n"
        "No microtransactions. No battle pass. Just vibes."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="← Back", callback_data="main_menu")]]
    )
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "menu_themes")
async def menu_themes(cb: CallbackQuery):
    await cb.answer()
    buttons = []
    for key, t in THEMES.items():
        buttons.append([InlineKeyboardButton(text=t["name"], callback_data=f"theme_{key}")])
    buttons.append([InlineKeyboardButton(text="← Back", callback_data="main_menu")])
    await cb.message.edit_text(
        "Choose your aesthetic:\n\n"
        + "\n".join(f"{t['name']} — {t['desc']}" for t in THEMES.values()),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("theme_"))
async def select_theme(cb: CallbackQuery, state: FSMContext):
    theme = cb.data.split("_", 1)[1]
    await state.update_data(theme=theme)
    await cb.answer(f"Theme set: {THEMES[theme]['name']}")
    # now difficulty
    buttons = []
    for key, d in DIFFICULTIES.items():
        buttons.append([InlineKeyboardButton(text=d["name"], callback_data=f"diff_{key}")])
    buttons.append([InlineKeyboardButton(text="← Themes", callback_data="menu_themes")])
    await cb.message.edit_text(
        f"Theme locked: <b>{THEMES[theme]['name']}</b>\n\nNow pick intensity:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("diff_"))
async def select_diff(cb: CallbackQuery, state: FSMContext):
    diff = cb.data.split("_", 1)[1]
    data = await state.get_data()
    theme = data.get("theme", "nokia")
    await cb.answer()
    await start_game(cb, theme=theme, difficulty=diff)


@dp.callback_query(F.data == "play")
async def play_quick(cb: CallbackQuery, state: FSMContext):
    # default theme + ask difficulty or just start mid
    await state.update_data(theme="nokia")
    buttons = []
    for key, d in DIFFICULTIES.items():
        buttons.append([InlineKeyboardButton(text=d["name"], callback_data=f"diff_{key}")])
    buttons.append([InlineKeyboardButton(text="← Menu", callback_data="main_menu")])
    await cb.message.edit_text(
        "Pick your intensity (theme = Classic Nokia):\n\n"
        + "\n".join(f"{d['name']} — {d['desc']}" for d in DIFFICULTIES.values()),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


async def start_game(cb: CallbackQuery, theme: str = "nokia", difficulty: str = "mid"):
    user_id = cb.from_user.id
    # stop any existing
    if user_id in games:
        old = games[user_id]
        if old.tick_task and not old.tick_task.done():
            old.tick_task.cancel()
        del games[user_id]

    state = new_game(user_id, cb.message.chat.id, theme, difficulty)
    games[user_id] = state

    text = f"{render_board(state)}\n\n{get_status_text(state)}"
    msg = await cb.message.edit_text(
        text, reply_markup=controls_keyboard(state), parse_mode="HTML"
    )
    state.message_id = msg.message_id

    # start continuous loop
    state.tick_task = asyncio.create_task(game_loop(user_id))


@dp.callback_query(F.data == "restart")
async def restart(cb: CallbackQuery):
    user_id = cb.from_user.id
    theme = "nokia"
    diff = "mid"
    if user_id in games:
        theme = games[user_id].theme
        diff = games[user_id].difficulty
    await start_game(cb, theme=theme, difficulty=diff)


@dp.callback_query(F.data.startswith("dir_"))
async def change_dir(cb: CallbackQuery):
    user_id = cb.from_user.id
    if user_id not in games:
        await cb.answer("No active game", show_alert=True)
        return
    state = games[user_id]
    if not state.alive:
        await cb.answer()
        return

    new_dir = Direction[cb.data.split("_")[1]]
    # prevent 180 turn
    opp = {
        Direction.UP: Direction.DOWN,
        Direction.DOWN: Direction.UP,
        Direction.LEFT: Direction.RIGHT,
        Direction.RIGHT: Direction.LEFT,
    }
    if new_dir != opp[state.direction]:
        state.next_direction = new_dir
    await cb.answer()


@dp.callback_query(F.data == "pause")
async def pause_game(cb: CallbackQuery):
    user_id = cb.from_user.id
    if user_id not in games:
        await cb.answer()
        return
    state = games[user_id]
    state.paused = not state.paused
    await cb.answer("Paused" if state.paused else "Resumed")
    try:
        text = f"{render_board(state)}\n\n{get_status_text(state)}"
        await cb.message.edit_text(
            text, reply_markup=controls_keyboard(state), parse_mode="HTML"
        )
    except Exception:
        pass


@dp.callback_query(F.data == "quit")
async def quit_game(cb: CallbackQuery):
    user_id = cb.from_user.id
    if user_id in games:
        state = games[user_id]
        state.alive = False
        if state.tick_task and not state.tick_task.done():
            state.tick_task.cancel()
        await end_game(state)
    await cb.answer("Game ended")


@dp.callback_query(F.data == "leaderboard")
async def show_lb(cb: CallbackQuery):
    await cb.answer()
    rows = get_leaderboard(10)
    if not rows:
        text = "No scores yet. Be the first to cook 🔥"
    else:
        medals = ["🥇", "🥈", "🥉"] + ["▫️"] * 7
        lines = []
        for i, (name, score, games_p) in enumerate(rows):
            title = ""
            if score >= 300:
                title = " 🐐"
            elif score >= 200:
                title = " 🔥"
            elif score >= 100:
                title = " ✨"
            lines.append(f"{medals[i]} <b>{name}</b> — {score}{title}  ({games_p} runs)")
        text = "🏆 <b>GLOBAL LEADERBOARD</b>\n\n" + "\n".join(lines)
        text += "\n\n<i>Only the goated make it here.</i>"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Play", callback_data="play")],
            [InlineKeyboardButton(text="← Menu", callback_data="main_menu")],
        ]
    )
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


async def main():
    init_db()
    print("🐍 Nokia Snake × Gen Z bot is live...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
