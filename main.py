import discord
from discord import app_commands
import os
import json

# --- Persistence ---
DATA_FILE = "/app/data/counts.json"
os.makedirs("/app/data", exist_ok=True)

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {
        "total_came": 0,
        "total_edged": 0,
        "total_ruined": 0,
        "scoreboard_message_id": None
    }

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# --- Bot setup ---
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

SCOREBOARD_CHANNEL_ID = 1512096423947014347

def build_embed(data):
    embed = discord.Embed(
        title="🍆 Server Scoreboard",
        color=0xff69b4
    )
    embed.add_field(name="💦 Total Orgasms", value=str(data["total_came"]), inline=True)
    embed.add_field(name="😮‍💨 Total Edges", value=str(data["total_edged"]), inline=True)
    embed.add_field(name="😩 Total Ruins", value=str(data["total_ruined"]), inline=True)
    return embed

async def update_scoreboard(data):
    channel = client.get_channel(SCOREBOARD_CHANNEL_ID)
    if channel is None:
        return

    msg_id = data.get("scoreboard_message_id")
    embed = build_embed(data)

    if msg_id:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(embed=embed)
            return
        except discord.NotFound:
            pass

    msg = await channel.send(embed=embed)
    data["scoreboard_message_id"] = msg.id
    save_data(data)

# --- /check command ---
@tree.command(name="check", description="Trigger an anonymous comfort check")
@app_commands.describe(color="Optional: signal a specific light without a full check-in")
@app_commands.choices(color=[
    app_commands.Choice(name="green", value="green"),
    app_commands.Choice(name="yellow", value="yellow"),
    app_commands.Choice(name="red", value="red"),
])
async def check(interaction: discord.Interaction, color: app_commands.Choice[str] = None):
    await interaction.response.send_message(
        "Your comfort check has been sent.",
        ephemeral=True
    )

    if color is None:
        await interaction.channel.send(
            "**COMFORT CHECK IN**\n\n"
            "<:GO:1490423634366304428> **Good to go.** I'm present, I'm in, keep going.\n"
            "<:WAIT:1490423509812511084> **Please wait.** Something shifted. I'm not sure. Pause here. Check in. Pull back.\n"
            "<:STOP:1490423467500109994> **Please stop.** This ends now."
        )
    elif color.value == "green":
        await interaction.channel.send("<:GO:1490423634366304428>")
    elif color.value == "yellow":
        await interaction.channel.send("<:WAIT:1490423509812511084>")
    elif color.value == "red":
        await interaction.channel.send("<:STOP:1490423467500109994>")

# --- /linkdrop command ---
@tree.command(name="linkdrop", description="Anonymously post a link or message, with an optional role ping")
@app_commands.describe(
    message="Your message or link",
    role="Optional: ping a role"
)
@app_commands.choices(role=[
    app_commands.Choice(name="Cocktroller", value="Cocktroller"),
    app_commands.Choice(name="Cuntroller", value="Cuntroller"),
    app_commands.Choice(name="Both", value="both"),
])
async def linkdrop(interaction: discord.Interaction, message: str, role: app_commands.Choice[str] = None):
    await interaction.response.send_message(
        "Your link drop has been posted.",
        ephemeral=True
    )

    ping_text = ""
    if role is not None:
        if role.value in ("Cocktroller", "both"):
            r = discord.utils.get(interaction.guild.roles, name="Cocktroller")
            if r:
                ping_text += r.mention + " "
        if role.value in ("Cuntroller", "both"):
            r = discord.utils.get(interaction.guild.roles, name="Cuntroller")
            if r:
                ping_text += r.mention + " "

    await interaction.channel.send(
        f"{ping_text}\n{message}".strip()
    )

# --- /cumcount command ---
@tree.command(name="cumcount", description="Log an orgasm, edge, or ruin to the server scoreboard")
@app_commands.describe(
    result="What happened?",
    count="How many times? (default: 1)",
    anonymous="Hide your name? (default: no)"
)
@app_commands.choices(result=[
    app_commands.Choice(name="came", value="came"),
    app_commands.Choice(name="edged", value="edged"),
    app_commands.Choice(name="ruined", value="ruined"),
])
async def cumcount(
    interaction: discord.Interaction,
    result: app_commands.Choice[str],
    count: int = 1,
    anonymous: bool = False
):
    data = load_data()
    name = "Someone" if anonymous else interaction.user.mention
    times = "time" if count == 1 else "times"

    if result.value == "came":
        data["total_came"] += count
        message = (
            f"{name} came **{count}** {times} woohooo 🎉\n"
            f"Congrats on the sex 🎊\n"
            f"{name} Thank you, cum again 😏"
        )
    elif result.value == "edged":
        data["total_edged"] += count
        message = (
            f"{name} edged **{count}** {times} yiiissss 😮‍💨\n"
            f"Congrats on the sex 🎊"
        )
    elif result.value == "ruined":
        data["total_ruined"] += count
        message = (
            f"{name} had **{count}** ruined orgasm{'s' if count != 1 else ''} 😩\n"
            f"F in the chat 💀"
        )

    save_data(data)

    if anonymous:
        await interaction.response.send_message("Logged anonymously ✅", ephemeral=True)
        await interaction.channel.send(message)
    else:
        await interaction.response.send_message(message)

    await update_scoreboard(data)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    # Guild sync — makes commands available immediately in the target guild
    try:
        guild = discord.Object(id=1487446782219911241)
        guild_commands = await tree.sync(guild=guild)
        print(f"Synced {len(guild_commands)} command(s) to guild {guild.id}: {[c.name for c in guild_commands]}")
    except Exception as e:
        print(f"Guild sync failed: {e}")

client.run(os.environ["DISCORD_TOKEN"])
