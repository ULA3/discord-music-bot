import discord
from discord import app_commands
import yt_dlp
import asyncio
import os

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

queues = {}
autoplay = {}

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
# Queue System
# ──────────────────────────────
def get_queue(guild_id):
    return queues.setdefault(guild_id, [])

async def play_next(interaction):
    queue = get_queue(interaction.guild.id)

    # If queue empty
    if not queue:
        if autoplay.get(interaction.guild.id):
            last = autoplay.get(interaction.guild.id)
            if not last:
                await interaction.channel.send("🛑 Queue ended.")
                return

            song = await get_related_song(last["title"])
            queue.append(song)
        else:
            await interaction.channel.send("🛑 Queue ended. Add more songs!")
            return

    song = queue.pop(0)
    autoplay[interaction.guild.id] = song

    ffmpeg_options = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": "-vn -bufsize 64k"
    }

    source = discord.FFmpegPCMAudio(song["stream"], **ffmpeg_options)

    interaction.guild.voice_client.play(
        source,
        after=lambda e: asyncio.run_coroutine_threadsafe(
            play_next(interaction), client.loop
        )
    )

    embed = discord.Embed(
        title="🎶 Now Playing",
        description=f"**{song['title']}**",
        color=0x1DB954
    )
    embed.set_thumbnail(url=song["thumbnail"])
    embed.add_field(name="Requested by", value=song["requester"], inline=True)

    await interaction.channel.send(embed=embed, view=MusicControls())
    
async def preload(song):
    await asyncio.get_event_loop().run_in_executor(
        None, lambda: ytdl.extract_info(song["stream"], download=False)
    )
    
async def get_related_song(title):
    query = f"ytsearch1:{title}"
    info = await asyncio.get_event_loop().run_in_executor(
        None, lambda: ytdl.extract_info(query, download=False)['entries'][0]
    )

    return {
        "stream": info["url"],
        "title": info["title"],
        "thumbnail": info["thumbnail"],
        "requester": "🎵 Autoplay"
    }

# ──────────────────────────────
# Slash Commands
# ──────────────────────────────
@tree.command(name="play", description="Play a song from YouTube")
async def play(interaction: discord.Interaction, query: str):

    await interaction.response.defer()

    if not interaction.user.voice:
        await interaction.followup.send("❗ Join a voice channel first.")
        return

    channel = interaction.user.voice.channel

    if not interaction.guild.voice_client:
        await channel.connect()

    if not query.startswith("http"):
        query = f"ytsearch1:{query}"

    def extract():
        return ytdl.extract_info(query, download=False)['entries'][0] \
            if query.startswith("ytsearch") else ytdl.extract_info(query, download=False)

    info = await asyncio.get_event_loop().run_in_executor(None, extract)

    song = {
        "stream": info["url"],
        "title": info["title"],
        "thumbnail": info["thumbnail"],
        "requester": interaction.user.mention
    }

    queue = get_queue(interaction.guild.id)
    queue.append(song)

    await interaction.followup.send(f"➕ Added to queue: **{song['title']}**")

    if not interaction.guild.voice_client.is_playing():
        await play_next(interaction)
    elif len(queue) == 1:
        asyncio.create_task(preload(queue[0]))


@tree.command(name="queue", description="Show current music queue")
async def show_queue(interaction: discord.Interaction):
    queue = get_queue(interaction.guild.id)

    if not queue:
        await interaction.response.send_message("Queue is empty.")
        return

    text = "\n".join(f"{i+1}. {song['title']}" for i, song in enumerate(queue[:10]))
    embed = discord.Embed(title="📃 Music Queue", description=text, color=0x3498DB)
    await interaction.response.send_message(embed=embed)
    
@tree.command(name="playlist", description="Show current playlist")
async def playlist(interaction: discord.Interaction):

    queue = get_queue(interaction.guild.id)

    if not queue:
        await interaction.response.send_message("🎧 Queue is empty.")
        return

    text = ""
    for i, song in enumerate(queue[:15], 1):
        text += f"**{i}.** {song['title']}\n"

    embed = discord.Embed(title="🎼 Current Playlist", description=text, color=0x5865F2)
    await interaction.response.send_message(embed=embed)
    
@tree.command(name="autoplay", description="Toggle autoplay mode")
async def toggle_autoplay(interaction: discord.Interaction):
    state = autoplay.get(interaction.guild.id, False)
    autoplay[interaction.guild.id] = not state
    await interaction.response.send_message(f"Autoplay {'ON' if not state else 'OFF'} 🎶")


@tree.command(name="skip", description="Skip current song")
async def skip_cmd(interaction: discord.Interaction):
    interaction.guild.voice_client.stop()
    await interaction.response.send_message("⏭ Skipped.")

@client.event
async def on_voice_state_update(member, before, after):
    if member == client.user and before.channel and not after.channel:
        channel = before.channel
        await channel.connect()

@tree.command(name="stop", description="Stop music and clear queue")
async def stop(interaction: discord.Interaction):
    queues[interaction.guild.id] = []
    await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message("🛑 Stopped and cleared queue.")

# ──────────────────────────────
# Start Bot
# ──────────────────────────────
client.run(os.getenv("DISCORD_TOKEN"))
