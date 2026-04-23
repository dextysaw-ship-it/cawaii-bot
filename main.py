import discord
from discord.ext import commands
import sqlite3
import time
import os
from datetime import datetime
import random
import string

TOKEN = os.environ.get('DISCORD_TOKEN')

# Подключение к БД
conn = sqlite3.connect('licenses.db')
cursor = conn.cursor()

# Создание таблиц
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    discord_id TEXT PRIMARY KEY,
    username TEXT,
    expires_at INTEGER,
    created_at INTEGER
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS codes (
    code TEXT PRIMARY KEY,
    days INTEGER,
    used INTEGER DEFAULT 0,
    created_at INTEGER
)
''')

conn.commit()

# Discord бот
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

def generate_code(days):
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
    cursor.execute('''
    INSERT INTO codes (code, days, created_at)
    VALUES (?, ?, ?)
    ''', (code, days, int(time.time())))
    conn.commit()
    return code

def activate_user(code, discord_id, username):
    cursor.execute('SELECT * FROM codes WHERE code = ? AND used = 0', (code,))
    result = cursor.fetchone()
    
    if not result:
        return False, None
    
    code_data, days, used, created_at = result
    expires_at = int(time.time()) + (days * 86400)
    
    cursor.execute('''
    INSERT OR REPLACE INTO users (discord_id, username, expires_at, created_at)
    VALUES (?, ?, ?, ?)
    ''', (discord_id, username, expires_at, int(time.time())))
    
    cursor.execute('UPDATE codes SET used = 1 WHERE code = ?', (code,))
    conn.commit()
    
    return True, expires_at

def get_user(discord_id):
    cursor.execute('SELECT * FROM users WHERE discord_id = ? AND expires_at > ?', 
                   (discord_id, int(time.time())))
    return cursor.fetchone()

def revoke_user(discord_id):
    cursor.execute('DELETE FROM users WHERE discord_id = ?', (discord_id,))
    conn.commit()

def extend_user(discord_id, days):
    user = get_user(discord_id)
    if user:
        new_expires = user[2] + (days * 86400)
        cursor.execute('UPDATE users SET expires_at = ? WHERE discord_id = ?', 
                       (new_expires, discord_id))
        conn.commit()
        return True
    return False

# ============= КОМАНДЫ =============

@bot.command(name='gen')
@commands.has_permissions(administrator=True)
async def gen_code(ctx, days: int = 30):
    code = generate_code(days)
    embed = discord.Embed(
        title="🔑 Activation Code",
        description=f"```{code}```\n**Duration:** {days} days",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name='activate')
async def activate(ctx, code: str = None):
    if not code:
        await ctx.send("❌ Usage: `!activate CODE`")
        return
    
    success, expires_at = activate_user(code, str(ctx.author.id), ctx.author.name)
    
    if success:
        embed = discord.Embed(
            title="✅ License Activated!",
            description=f"**Expires:** {datetime.fromtimestamp(expires_at).strftime('%Y-%m-%d')}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Invalid Code",
            description="This code doesn't exist or has been used",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

@bot.command(name='status')
async def my_status(ctx):
    user = get_user(str(ctx.author.id))
    
    if not user:
        await ctx.send("❌ No active license. Use `!activate CODE`")
        return
    
    expires_at = user[2]
    remaining_days = (expires_at - int(time.time())) // 86400
    
    embed = discord.Embed(
        title="📋 License Status",
        description=f"✅ Active\n**Expires in:** {remaining_days} days",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name='list')
@commands.has_permissions(administrator=True)
async def list_users(ctx):
    cursor.execute('SELECT discord_id, username, expires_at FROM users WHERE expires_at > ?', 
                   (int(time.time()),))
    users = cursor.fetchall()
    
    if not users:
        await ctx.send("No active users")
        return
    
    embed = discord.Embed(title=f"Active Users ({len(users)})", color=discord.Color.blue())
    for user_id, username, expires_at in users[:20]:
        remaining = (expires_at - int(time.time())) // 86400
        embed.add_field(name=username, value=f"<@{user_id}> • {remaining} days", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='revoke')
@commands.has_permissions(administrator=True)
async def revoke(ctx, user: discord.User):
    revoke_user(str(user.id))
    await ctx.send(f"❌ Revoked: {user.mention}")

@bot.command(name='extend')
@commands.has_permissions(administrator=True)
async def extend(ctx, user: discord.User, days: int):
    if extend_user(str(user.id), days):
        await ctx.send(f"✅ Extended {user.mention} by {days} days")
    else:
        await ctx.send(f"❌ User not found")

@bot.event
async def on_ready():
    print(f'✅ Bot online: {bot.user}')
    await bot.change_presence(activity=discord.Game(name="!activate | Cawaii Loader"))

# Добавь это в КОНЕЦ файла с ботом, перед bot.run(TOKEN)

@bot.command(name='check')
async def check_key(ctx, key: str = None):
    """!check КЛЮЧ - проверить активирован ли ключ"""
    if not key:
        await ctx.send("❌ Использование: `!check КЛЮЧ`")
        return
    
    # Проверяем в базе данных
    cursor.execute('SELECT * FROM codes WHERE code = ? AND used = 1', (key,))
    result = cursor.fetchone()
    
    if result:
        # Ключ активирован
        embed = discord.Embed(
            title="✅ КЛЮЧ АКТИВИРОВАН",
            description=f"Ключ `{key}` действителен! Можешь загружать скрипт.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    else:
        # Проверяем существует ли ключ
        cursor.execute('SELECT * FROM codes WHERE code = ?', (key,))
        exists = cursor.fetchone()
        
        if exists:
            embed = discord.Embed(
                title="⚠️ КЛЮЧ НЕ АКТИВИРОВАН",
                description=f"Ключ `{key}` существует, но ещё не активирован. Используй `!activate {key}`",
                color=discord.Color.orange()
            )
        else:
            embed = discord.Embed(
                title="❌ НЕВЕРНЫЙ КЛЮЧ",
                description=f"Ключ `{key}` не найден в системе",
                color=discord.Color.red()
            )
        await ctx.send(embed=embed)

@bot.command(name='activate')
async def activate_key(ctx, key: str = None):
    """!activate КЛЮЧ - активировать ключ для себя"""
    if not key:
        await ctx.send("❌ Использование: `!activate КЛЮЧ`")
        return
    
    cursor.execute('SELECT * FROM codes WHERE code = ? AND used = 0', (key,))
    result = cursor.fetchone()
    
    if result:
        # Активируем ключ
        expires_at = int(time.time()) + (result[2] * 86400)  # result[2] - это days
        cursor.execute('UPDATE codes SET used = 1, discord_id = ?, expires_at = ? WHERE code = ?', 
                       (str(ctx.author.id), expires_at, key))
        conn.commit()
        
        embed = discord.Embed(
            title="✅ КЛЮЧ АКТИВИРОВАН",
            description=f"Ключ `{key}` активирован для {ctx.author.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ Ключ `{key}` не найден или уже использован")
        
bot.run(TOKEN)
