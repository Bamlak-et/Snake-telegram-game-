import os
import json
import threading
from flask import Flask, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8585158678:AAGZfcWFVy2daDBe-qNcjzlXaw2THg2XFdc")
PORT = int(os.environ.get("PORT", 5000))

# Render automatically creates RENDER_EXTERNAL_HOSTNAME
RENDER_HOST = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
SERVER_URL = f"https://{RENDER_HOST}" if RENDER_HOST else f"http://localhost:{PORT}"

flask_app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="am">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no"/>
  <title>የእባብ ጨዋታ (Habesha Snake)</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    body { background-color: #121212; color: #fff; font-family: sans-serif; text-align: center; margin: 0; touch-action: manipulation; }
    #game-container { margin-top: 10px; }
    canvas { border: 4px solid #fcd116; background-color: #1a1a1a; border-radius: 8px; }
    .score-board { font-size: 20px; margin: 10px; color: #009a44; font-weight: bold; }
    .controls { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; width: 200px; margin: 15px auto; }
    button { padding: 15px; font-size: 18px; background: #da121a; color: white; border: none; border-radius: 8px; }
  </style>
</head>
<body>
  <h2>🐍 Habesha Snake Game</h2>
  <div class="score-board">ደረጃ (Score): <span id="score">0</span></div>
  <div id="game-container"><canvas id="gameCanvas" width="300" height="300"></canvas></div>
  <div class="controls">
    <div></div><button onclick="changeDir('UP')">⬆️</button><div></div>
    <button onclick="changeDir('LEFT')">⬅️</button>
    <button onclick="changeDir('DOWN')">⬇️</button>
    <button onclick="changeDir('RIGHT')">➡️</button>
  </div>
  <script>
    const tg = window.Telegram.WebApp;
    tg.expand();
    const canvas = document.getElementById("gameCanvas");
    const ctx = canvas.getContext("2d");
    const box = 15;
    let score = 0;
    let snake = [{ x: 9 * box, y: 10 * box }];
    let food = { x: Math.floor(Math.random() * 19 + 1) * box, y: Math.floor(Math.random() * 19 + 1) * box };
    let d = "RIGHT";

    function changeDir(direction) {
      if (direction === "LEFT" && d !== "RIGHT") d = "LEFT";
      if (direction === "UP" && d !== "DOWN") d = "UP";
      if (direction === "RIGHT" && d !== "LEFT") d = "RIGHT";
      if (direction === "DOWN" && d !== "UP") d = "DOWN";
    }

    function draw() {
      ctx.fillStyle = "#1a1a1a";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      const colors = ["#009a44", "#fcd116", "#da121a"];
      for (let i = 0; i < snake.length; i++) {
        ctx.fillStyle = colors[i % colors.length];
        ctx.fillRect(snake[i].x, snake[i].y, box, box);
        ctx.strokeStyle = "#121212";
        ctx.strokeRect(snake[i].x, snake[i].y, box, box);
      }
      ctx.fillStyle = "#6F4E37";
      ctx.beginPath();
      ctx.arc(food.x + box/2, food.y + box/2, box/2, 0, Math.PI * 2);
      ctx.fill();

      let snakeX = snake[0].x;
      let snakeY = snake[0].y;
      if (d === "LEFT") snakeX -= box;
      if (d === "UP") snakeY -= box;
      if (d === "RIGHT") snakeX += box;
      if (d === "DOWN") snakeY += box;

      if (snakeX === food.x && snakeY === food.y) {
        score += 10;
        document.getElementById("score").innerText = score;
        if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
        food = { x: Math.floor(Math.random() * 19 + 1) * box, y: Math.floor(Math.random() * 19 + 1) * box };
      } else {
        snake.pop();
      }

      let newHead = { x: snakeX, y: snakeY };
      if (snakeX < 0 || snakeY < 0 || snakeX >= canvas.width || snakeY >= canvas.height || collision(newHead, snake)) {
        clearInterval(game);
        tg.sendData(JSON.stringify({ score: score }));
        alert("ጨዋታው አበቃ! Your Score: " + score);
      }
      snake.unshift(newHead);
    }

    function collision(head, array) {
      for (let i = 0; i < array.length; i++) {
        if (head.x === array[i].x && head.y === array[i].y) return true;
      }
      return false;
    }
    let game = setInterval(draw, 120);
  </script>
</body>
</html>
"""

@flask_app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🎮 ተጫወት (Play Snake)", web_app=WebAppInfo(url=SERVER_URL))]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("እንኳን ወደ ሐበሻ እባብ ጨዋታ በደህና መጡ! 🐍", reply_markup=reply_markup)

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = json.loads(update.effective_message.web_app_data.data)
    user = update.effective_user.first_name
    score = data.get("score", 0)
    await update.message.reply_text(f"👏 አሪፍ ነው {user}! አስመዘገቡት ነጥብ: {score}")

def main():
    server_thread = threading.Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.run_polling()

if __name__ == "__main__":
    main()

