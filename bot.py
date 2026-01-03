import discord
from discord import app_commands
import yt_dlp
import asyncio
import os

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

queues = {}

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

    if not queue:
        await interaction.guild.voice_client.disconnect()
        return

    song = queue.pop(0)

    source = discord.FFmpegPCMAudio(song["stream"])
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

@tree.command(name="queue", description="Show current music queue")
async def show_queue(interaction: discord.Interaction):
    queue = get_queue(interaction.guild.id)

    if not queue:
        await interaction.response.send_message("Queue is empty.")
        return

    text = "\n".join(f"{i+1}. {song['title']}" for i, song in enumerate(queue[:10]))
    embed = discord.Embed(title="📃 Music Queue", description=text, color=0x3498DB)
    await interaction.response.send_message(embed=embed)

@tree.command(name="skip", description="Skip current song")
async def skip_cmd(interaction: discord.Interaction):
    interaction.guild.voice_client.stop()
    await interaction.response.send_message("⏭ Skipped.")

@tree.command(name="stop", description="Stop music and clear queue")
async def stop(interaction: discord.Interaction):
    queues[interaction.guild.id] = []
    await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message("🛑 Stopped and cleared queue.")

# ──────────────────────────────
# Start Bot
# ──────────────────────────────
client.run(os.getenv("DISCORD_TOKEN"))
