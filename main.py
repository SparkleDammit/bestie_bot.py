import discord
from discord import app_commands
import os
import json

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

SCOREBOARD_CHANNEL_ID = 1512096423947014347
DATA_FILE = "/app/data/cumcount.json"
os.makedirs("/app/data", exist_ok=True)


def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_data(data: dict) -> None:
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def build_embed(data: dict) -> discord.Embed:
    embed = discord.Embed(
        title="🍆 Cumcount Scoreboard",
        color=discord.Color.purple()
    )
    if not data:
        embed.description = "No entries yet. Use `/cumcount` to log one!"
        return embed

    lines = []
    for user_id, counts in sorted(data.items(), key=lambda x: x[1].get("orgasms", 0), reverse=True):
        orgasms = counts.get("orgasms", 0)
        edges = counts.get("edges", 0)
        ruins = counts.get("ruins", 0)
        lines.append(
            f"<@{user_id}> — 💦 {orgasms} orgasm(s) | 🔥 {edges} edge(s) | 💔 {ruins} ruin(s)"
        )
    embed.description = "\n".join(lines)
    return embed


async def update_scoreboard(guild: discord.Guild, data: dict) -> None:
    channel = guild.get_channel(SCOREBOARD_CHANNEL_ID)
    if channel is None:
        return
    embed = build_embed(data)
    async for msg in channel.history(limit=20):
        if msg.author == client.user and msg.embeds:
            await msg.edit(embed=embed)
            return
    await channel.send(embed=embed)


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
@tree.command(name="cumcount", description="Log an orgasm, edge, or ruin to the scoreboard")
@app_commands.describe(
    event="What happened?",
    count="How many times? (default: 1)",
    anonymous="Hide your name? (default: no)",
    user="Optional: log on behalf of another user (admin)"
)
@app_commands.choices(event=[
    app_commands.Choice(name="came", value="orgasms"),
    app_commands.Choice(name="edged", value="edges"),
    app_commands.Choice(name="ruined", value="ruins"),
])
async def cumcount(
    interaction: discord.Interaction,
    event: app_commands.Choice[str],
    count: int = 1,
    anonymous: bool = False,
    user: discord.Member = None
):
    target = user if user is not None else interaction.user
    data = load_data()
    user_key = str(target.id)
    times = "time" if count == 1 else "times"

    if user_key not in data:
        data[user_key] = {"orgasms": 0, "edges": 0, "ruins": 0}

    data[user_key][event.value] = data[user_key].get(event.value, 0) + count
    save_data(data)

    name = "Someone" if anonymous else target.mention

    if event.value == "orgasms":
        text = (
            f"{name} came **{count}** {times} woohooo 🎉\n"
            f"Thank you, cum again 😏"
        )
    elif event.value == "edges":
        text = (
            f"{name} edged **{count}** {times}\n"
            f"\"DoN't SpiLL oUr CuM!!\""
        )
    elif event.value == "ruins":
        text = (
            f"{name} had **{count}** ruined orgasm{'s' if count != 1 else ''}\n"
            f"Whoops"
        )

    if anonymous:
        await interaction.response.send_message("Logged anonymously ✅", ephemeral=True)
        await interaction.channel.send(text)
    else:
        await interaction.response.send_message(text)

    await update_scoreboard(interaction.guild, data)


@cumcount.error
async def cumcount_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandSignatureMismatch):
        await interaction.response.send_message(
            "This command is being updated — please wait a moment and try again.",
            ephemeral=True
        )
    else:
        raise error


# --- /resetcount command ---
@tree.command(name="resetcount", description="Reset the scoreboard (admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def resetcount(interaction: discord.Interaction):
    save_data({})
    await update_scoreboard(interaction.guild, {})
    await interaction.response.send_message("Scoreboard reset ✅", ephemeral=True)

@resetcount.error
async def resetcount_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You don't have permission to do that.", ephemeral=True)


@client.event
async def on_ready():
    guild = discord.Object(id=1487446782219911241)
    synced = await tree.sync(guild=guild)
    print(f"Logged in as {client.user}")
    print(f"Synced {len(synced)} command(s) to guild {guild.id}:")
    for cmd in synced:
        print(f"  /{cmd.name}")

client.run(os.environ["DISCORD_TOKEN"])
