import discord
from discord.ext import commands, tasks
from discord import app_commands
import yt_dlp
import asyncio
import os
import time

# ================= CONFIG =================
BOT_TOKEN = "MTQ2OTM3NTk0MzU5NTM5NzMyNA.GzmBev.LThKESeMgi4YVLZwmIJNxyS4UZCPn-Imnj0BNg"

VOICE_CHANNEL_ID = 1454791933280129219
TEXT_CHANNEL_ID  = 1454791933280129219

MUSIC_DIR = "music"
os.makedirs(MUSIC_DIR, exist_ok=True)

BAR_LEN = 18
# =========================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

queues = {}
panel_message = {}
muted_users = set()
panel_lock = asyncio.Lock()

# ================= yt-dlp =================
ytdl_opts = {
    "format": "bestaudio/best",
    "outtmpl": f"{MUSIC_DIR}/%(id)s.%(ext)s",
    "quiet": True,
    "noplaylist": True,
    "default_search": "ytsearch1",
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "opus",
        "preferredquality": "0"
    }]
}
ffmpeg_opts = {"options": "-vn"}

# ================= HELPERS =================

def get_queue(gid):
    return queues.setdefault(gid, [])

def fmt(sec):
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"

def bar(cur, total):
    filled = int((cur / total) * BAR_LEN)
    return "▬" * filled + "🔘" + "▬" * (BAR_LEN - filled)

def cache_path(video_id):
    path = f"{MUSIC_DIR}/{video_id}.opus"
    return path if os.path.exists(path) else None

def build_embed(guild, status):
    vc = guild.voice_client
    q = get_queue(guild.id)

    embed = discord.Embed(
        title="🎶 Music Control Panel",
        description=status,
        color=0x1DB954
    )

    if vc and vc.source:
        s = vc.source
        elapsed = min(time.time() - s.start_time, s.duration)
        embed.add_field(
            name="🎧 Now Playing",
            value=(
                f"**{s.title}**\n"
                f"👤 {s.requester}\n"
                f"{fmt(elapsed)} {bar(elapsed, s.duration)} {fmt(s.duration)}"
            ),
            inline=False
        )
    else:
        embed.add_field(name="🎧 Now Playing", value="Nothing", inline=False)

    if q:
        embed.add_field(
            name="⏭️ Next Up",
            value=f"**{q[0][1]}**\n👤 {q[0][2]}",
            inline=False
        )
    else:
        embed.add_field(name="⏭️ Next Up", value="Nothing", inline=False)

    embed.set_footer(text="RNR Music • Premium Mode")
    return embed

# ================= PANEL LOGIC =================
# EXACT RULE:
# - panel latest → edit
# - panel not latest → delete + send new

async def send_or_update_panel(guild, embed, view=None):
    async with panel_lock:
        channel = guild.get_channel(TEXT_CHANNEL_ID)
        old_panel = panel_message.get(guild.id)

        try:
            history = [m async for m in channel.history(limit=1)]
            latest = history[0] if history else None
        except:
            latest = None

        # CASE 1: panel exists AND is latest → EDIT
        if old_panel and latest and latest.id == old_panel.id:
            try:
                if view:
                    await old_panel.edit(embed=embed, view=view)
                else:
                    await old_panel.edit(embed=embed)
                return
            except:
                pass

        # CASE 2: panel exists BUT not latest → DELETE
        if old_panel:
            try:
                await old_panel.delete()
            except:
                pass

        # CASE 3: SEND NEW
        msg = await channel.send(embed=embed, view=view)
        panel_message[guild.id] = msg

# ================= PLAYER =================

async def play_next(guild):
    vc = guild.voice_client
    q = get_queue(guild.id)

    if not vc or vc.is_playing() or vc.is_paused():
        return

    if not q:
        await send_or_update_panel(
            guild, build_embed(guild, "Queue empty 💤"), MusicMenu()
        )
        return

    path, title, user, dur = q.pop(0)

    src = discord.FFmpegPCMAudio(path, **ffmpeg_opts)
    src.title = title
    src.requester = user
    src.duration = dur
    src.start_time = time.time()

    def after(_):
        async def cleanup():
            await asyncio.sleep(600)
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass

        asyncio.run_coroutine_threadsafe(cleanup(), bot.loop)
        asyncio.run_coroutine_threadsafe(play_next(guild), bot.loop)

    vc.play(src, after=after)
    await send_or_update_panel(
        guild, build_embed(guild, "▶️ Playing"), MusicMenu()
    )

# ================= PLAY HANDLER =================

async def handle_play(interaction, query):
    if interaction.user.id in muted_users:
        await interaction.response.send_message(
            "🔇 You muted bot music. Use /unmute or UI button.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    requester = interaction.user.display_name

    await send_or_update_panel(
        guild, build_embed(guild, "⬇️ Processing…"), MusicMenu()
    )

    with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        if "entries" in info:
            info = info["entries"][0]

        vid = info["id"]
        title = info["title"]
        duration = info.get("duration", 0)

        path = cache_path(vid)
        if not path:
            ydl.extract_info(query, download=True)
            path = f"{MUSIC_DIR}/{vid}.opus"

    get_queue(guild.id).append((path, title, requester, duration))
    await interaction.followup.send(f"➕ Added: **{title}**")

    if not guild.voice_client.is_playing():
        await play_next(guild)
    else:
        await send_or_update_panel(
            guild, build_embed(guild, "➕ Added to queue"), MusicMenu()
        )

# ================= SLASH COMMANDS =================

@tree.command(name="play")
@app_commands.describe(song="Song name or link")
async def play(interaction: discord.Interaction, song: str):
    await handle_play(interaction, song)

@tree.command(name="mute")
async def mute(interaction: discord.Interaction):
    muted_users.add(interaction.user.id)
    if interaction.guild.voice_client:
        interaction.guild.voice_client.stop()
    get_queue(interaction.guild.id).clear()
    await interaction.response.send_message(
        "🔇 Bot music muted for you", ephemeral=True
    )

@tree.command(name="unmute")
async def unmute(interaction: discord.Interaction):
    muted_users.discard(interaction.user.id)
    await interaction.response.send_message(
        "🔊 Bot music unmuted for you", ephemeral=True
    )

# ================= UI =================

class AddSongModal(discord.ui.Modal, title="Add Music"):
    song = discord.ui.TextInput(label="Song name or link")

    async def on_submit(self, interaction):
        await handle_play(interaction, self.song.value)

class MusicMenu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Add Song", emoji="⬇️", style=discord.ButtonStyle.green)
    async def add(self, interaction, _):
        await interaction.response.send_modal(AddSongModal())

    @discord.ui.button(emoji="⏸", style=discord.ButtonStyle.gray)
    async def pause(self, interaction, _):
        await interaction.response.defer(ephemeral=True)
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await send_or_update_panel(
                interaction.guild,
                build_embed(interaction.guild, "⏸ Paused")
            )

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.green)
    async def resume(self, interaction, _):
        await interaction.response.defer(ephemeral=True)
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await send_or_update_panel(
                interaction.guild,
                build_embed(interaction.guild, "▶️ Playing")
            )

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.blurple)
    async def skip(self, interaction, _):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild.voice_client:
            interaction.guild.voice_client.stop()

    @discord.ui.button(label="Mute / Unmute", emoji="🔇", style=discord.ButtonStyle.gray)
    async def mute_toggle(self, interaction, _):
        await interaction.response.defer(ephemeral=True)
        uid = interaction.user.id

        if uid in muted_users:
            muted_users.remove(uid)
            await interaction.followup.send("🔊 Bot music unmuted for you")
        else:
            muted_users.add(uid)
            get_queue(interaction.guild.id).clear()
            if interaction.guild.voice_client:
                interaction.guild.voice_client.stop()
            await interaction.followup.send("🔇 Bot music muted for you")

# ================= PROGRESS =================

@tasks.loop(seconds=5)
async def progress_updater():
    for g in bot.guilds:
        vc = g.voice_client
        if vc and vc.is_playing() and g.id in panel_message:
            embed = build_embed(g, "▶️ Playing")
            await send_or_update_panel(g, embed)

# ================= EVENTS =================

@bot.event
async def on_ready():
    await tree.sync()
    progress_updater.start()
    print(f"Logged in as {bot.user}")

    for g in bot.guilds:
        vc = g.get_channel(VOICE_CHANNEL_ID)
        if vc and not g.voice_client:
            await vc.connect()
            await send_or_update_panel(
                g, build_embed(g, "🎧 Ready"), MusicMenu()
            )

# ================= RUN =================
bot.run(BOT_TOKEN)
