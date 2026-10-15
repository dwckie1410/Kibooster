import os
import asyncio
import discord
from discord.ext import commands
from flask import Flask
from threading import Thread

# --- WEBSERVER CHO RENDER & UPTIME ROBOT ---
app = Flask('')

@app.route('/')
def home():
    return "Bot đang hoạt động 24/7!"

def run_web():
    # Render sẽ tự cấp cổng qua biến môi trường PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# --- CẤU HÌNH BOT DISCORD ---
intents = discord.Intents.default()
intents.members = True          # BẮT BUỘC: Để theo dõi biến động Role của Member
intents.message_content = True  # BẮT BUỘC: Để nhận diện prefix command "kb."

bot = commands.Bot(command_prefix=["kb.", "KB.", "kB.", "Kb."], intents=intents)

@bot.event
async def on_ready():
    print("------------------------------------------")
    print(f"Bot đã online với tên: {bot.user}")
    print(f"Prefix: kb.")
    print("------------------------------------------")

async def main():
    # Kích hoạt web server ngầm
    keep_alive()
    
    # Load file customrole.py vào bot
    async with bot:
        await bot.load_extension("customrole")
        
        token = os.getenv("BOT_TOKEN")
        if not token:
            print("LỖI: Chưa cài đặt biến BOT_TOKEN!")
            return
            
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
