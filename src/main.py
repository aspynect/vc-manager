import discord
from discord import app_commands
from discord.ext import tasks
from os import getenv
import datetime
import zoneinfo

myColor = discord.Color.from_rgb(r=255, g=0, b=255)
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
DISCORD_TOKEN = getenv("DISCORD_TOKEN", "No discord token")
sessions = {}

async def closeSession(session: int):
    sessionToClose = sessions[session]
    users: list[discord.Member] = sessionToClose["users"]
    for user in users:
        await user.remove_roles(sessionToClose["role"])
    sessions.pop(session)


class SessionSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout = 30*60)

    @discord.ui.select(cls = discord.ui.UserSelect, placeholder = "Select anchor user", min_values = 1, max_values = 1)
    async def sessionAnchorUserSelector(self, interaction: discord.Interaction, userSelector: discord.ui.UserSelect):
        self.sessionAnchor = userSelector.values[0]
        await interaction.response.defer()

    @discord.ui.select(cls = discord.ui.ChannelSelect, placeholder = "Select a VC", channel_types = [discord.ChannelType.voice], min_values = 1, max_values = 1)
    async def sessionChannelSelector(self, interaction: discord.Interaction, channelSelector: discord.ui.ChannelSelect):
        self.sessionChannel = await channelSelector.values[0].fetch()
        await interaction.response.defer()

    @discord.ui.select(cls = discord.ui.RoleSelect, placeholder = "Select a role", min_values = 1, max_values = 1)
    async def sessionRoleSelector(self, interaction: discord.Interaction, roleSelector: discord.ui.RoleSelect):
        self.sessionRole = roleSelector.values[0]
        await interaction.response.defer()

    @discord.ui.select(cls = discord.ui.UserSelect, placeholder = "Select users", min_values = 1, max_values = 25)
    async def sessionUserSelector(self, interaction: discord.Interaction, userSelector: discord.ui.UserSelect):
        self.sessionUsers = userSelector.values
        await interaction.response.defer()

    @discord.ui.button(label = "Submit")
    async def submitButton(self, interaction: discord.Interaction, button: discord.ui.Button):
        #TODO does this check work? i dont know
        if not (self.sessionAnchor and self.sessionChannel and self.sessionRole and self.sessionUsers):
            interaction.response.defer()

        try:
            for user in self.sessionUsers:
                await user.add_roles(self.sessionRole)
        except discord.errors.Forbidden:
            await interaction.response.send_message("Ensure that my role is above the VC role and that the VC role is not a managed role", ephemeral = True)
            return
        
        sessions[self.sessionAnchor.id] = {
            "anchor": self.sessionAnchor,
            "channel": self.sessionChannel,
            "role": self.sessionRole,
            "users": self.sessionUsers,
            "server": interaction.guild,
            "sessionTimeout": 0
        }

        await interaction.response.send_message(f"<@{self.sessionAnchor.id}>'s Private VC session:\n<#{self.sessionChannel.id}>\n<@&{self.sessionRole.id}>\n{' '.join(f'<@{user.id}>' for user in self.sessionUsers)}", ephemeral = True)
        self.stop()


@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@tree.command(name="start-session",description="Start a session")
async def sync(interaction: discord.Interaction):
    await interaction.response.send_message(view = SessionSetupView(), ephemeral = True)


@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@tree.command(name="add-user",description="Add user to session")
async def addUser(interaction: discord.Interaction, user: discord.User):
    if interaction.user.id in sessions:
        sessions[interaction.user.id]["users"].append(user)
        await user.add_roles(sessions[interaction.user.id]["role"])
        await interaction.response.send_message(f"Added <@{user.id}> to session", ephemeral = True)



@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@tree.command(name="remove-user",description="Remove user from session")
async def removeUser(interaction: discord.Interaction, user: discord.User):
    if interaction.user.id in sessions:
        sessions[interaction.user.id]["users"].remove(user)
        await user.remove_roles(sessions[interaction.user.id]["role"])
        await user.move_to(None)
        await interaction.response.send_message(f"Removed <@{user.id}> from session", ephemeral = True)


@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="sync",description="sync")
async def sync(interaction: discord.Interaction):
    await tree.sync()
    await interaction.response.send_message("sunk!", ephemeral = True)
    print("Sunk!")


#TODO loop to check on anchor users/check if any non-assigned users are in the vc and close/update accordingly
@tasks.loop(minutes = 1)
async def checkVC():
    for session in sessions:
        sessionAnchor: discord.Member = session["anchor"]
        channelUsers: list[discord.Member] = session["channel"].members
        sessionUsers: list[discord.Member] = session["users"]
        sessionRole: discord.Role = session["role"]

        if sessionAnchor not in channelUsers:
            session["sessionTimeout"] += 1
            if session["sessionTimeout"] > 2:
                await closeSession(sessionAnchor.id)
        else:
            session["sessionTimeout"] = 0

        for newUser in [u for u in channelUsers if u not in sessionUsers]:
            session["users"].append(newUser)
            await newUser.add_roles(sessionRole)



@client.event
async def on_ready():
    print("Ready!")
    checkVC.start()


client.run(DISCORD_TOKEN)