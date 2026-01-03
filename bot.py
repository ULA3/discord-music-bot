import discord
from discord import app_commands
import yt_dlp
import asyncio
import os
import time

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

queues = {}
autoplay = {}
current_song = {}
current_volume = {}
song_start_time = {}

# ──────────────────────────────
# Music Control Buttons
# ──────────────────────────────
class MusicControls(discord.ui.View):

    @discord.ui.button(label="⏸ Pause", style=discord.ButtonStyle.gray)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("Paused ⏸", ephemeral=True)

    @discord.ui.button(label="▶ Resume", style=discord.ButtonStyle.green)
    async def resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("Resumed ▶", ephemeral=True)

    @discord.ui.button(label="⏭ Skip", style=discord.ButtonStyle.red)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            await interaction.response.send_message("Skipped ⏭", ephemeral=True)

# ──────────────────────────────
# Bot Ready
# ──────────────────────────────
@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {client.user}")

# ──────────────────────────────
# YouTube Config
# ──────────────────────────────
ytdl = yt_dlp.YoutubeDL({
    'format': 'bestaudio',
    'noplaylist': True,
    'quiet': True
})

# ──────────────────────────────
# Helpers
# ──────────────────────────────
def get_queue(guild_id):
    return queues.setdefault(guild_id, [])

def get_volume(guild_id):
    return current_volume.setdefault(guild_id, 0.5)

def make_bar(progress, length=20):
    filled = int(length * progress)
    return "▰" * filled + "▱" * (length - filled)

# ──────────────────────────────
# Playback Engine
# ──────────────────────────────
async def play_next(interaction):
    queue = get_queue(interaction.guild.id)

    if not queue:
        if autoplay.get(interaction.guild.id):
            last = autoplay.get(interaction.guild.id)
            song = await get_related_song(last["title"])
            queue.append(song)
        else:
            await interaction.channel.send("🛑 Queue ended.")
            return

    song = queue.pop(0)
    autoplay[interaction.guild.id] = song
    current_song[interaction.guild.id] = song
    song_start_time[interaction.guild.id] = time.time()

    ffmpeg_options = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": "-vn -bufsize 64k"
    }

    audio = discord.FFmpegPCMAudio(song["stream"], **ffmpeg_options)
    source = discord.PCMVolumeTransformer(audio, volume=get_volume(interaction.guild.id))

    interaction.guild.voice_client.play(
        source,
        after=lambda e: asyncio.run_coroutine_threadsafe(
            play_next(interaction), client.loop
        )
    )

    embed = discord.Embed(title="🎶 Now Playing", description=song["title"], color=0x1DB954)
    embed.set_thumbnail(url=song["thumbnail"])
    embed.add_field(name="Requested by", value=song["requester"])
    await interaction.channel.send(embed=embed, view=MusicControls())

async def preload(song):
    await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(song["stream"], download=False))

async def get_related_song(title):
    query = f"ytsearch1:{title}"
    info = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(query, download=False)['entries'][0])
    return {
        "stream": info["url"],
        "title": info["title"],
        "thumbnail": info["thumbnail"],
        "requester": "🎵 Autoplay"
    }

# ──────────────────────────────
# Commands
# ──────────────────────────────
@tree.command(name="play")
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()

    if not interaction.user.voice:
        await interaction.followup.send("Join a voice channel first.")
        return

    if not interaction.guild.voice_client:
        await interaction.user.voice.channel.connect()

    if not query.startswith("http"):
        query = f"ytsearch1:{query}"

    info = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(query, download=False)['entries'][0])

    song = {"stream": info["url"], "title": info["title"], "thumbnail": info["thumbnail"], "requester": interaction.user.mention}

    queue = get_queue(interaction.guild.id)
    queue.append(song)

    msg = await interaction.followup.send(f"🎧 Queued: **{song['title']}**")
    await asyncio.sleep(2)
    await msg.edit(content=f"🎶 Playing: **{song['title']}**")

    if not interaction.guild.voice_client.is_playing():
        await play_next(interaction)
    elif len(queue) == 1:
        asyncio.create_task(preload(queue[0]))

@tree.command(name="volume")
async def volume(interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]):
    current_volume[interaction.guild.id] = level / 100
    vc = interaction.guild.voice_client
    if vc and vc.source:
        vc.source.volume = current_volume[interaction.guild.id]
    await interaction.response.send_message(f"🔊 Volume set to {level}%")

@tree.command(name="now")
async def now(interaction: discord.Interaction):
    song = current_song.get(interaction.guild.id)
    if not song:
        await interaction.response.send_message("Nothing playing.")
        return

    elapsed = time.time() - song_start_time.get(interaction.guild.id, time.time())
    bar = make_bar(min(elapsed / 180, 1))
    embed = discord.Embed(title="🎵 Now Playing", description=f"{song['title']}\n{bar}", color=0x1DB954)
    embed.set_thumbnail(url=song["thumbnail"])
    await interaction.response.send_message(embed=embed)

@tree.command(name="autoplay")
async def toggle_autoplay(interaction: discord.Interaction):
    autoplay[interaction.guild.id] = not autoplay.get(interaction.guild.id, False)
    await interaction.response.send_message(f"Autoplay {'ON' if autoplay[interaction.guild.id] else 'OFF'}")

@tree.command(name="skip")
async def skip_cmd(interaction: discord.Interaction):
    interaction.guild.voice_client.stop()
    await interaction.response.send_message("Skipped ⏭")

@tree.command(name="stop")
async def stop(interaction: discord.Interaction):
    queues[interaction.guild.id] = []
    await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message("Stopped 🛑")

client.run(os.getenv("DISCORD_TOKEN"))
