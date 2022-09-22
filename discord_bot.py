import yaml
import interactions
from classes.permissionCode import *
from classes.gcodeCheckItem import *
import print_job_handler

with open("config_files/config.yml", "r") as yamlfile:
    config = yaml.load(yamlfile, Loader=yaml.FullLoader)

set_sql_debug(False)  # Shows the SQL queries pony is running in the console.
db.bind(provider='sqlite', filename='octofarmJira_database.sqlite', create_db=True)  # Establish DB connection.
db.generate_mapping(create_tables=True)


bot = interactions.Client(token=config['discord_settings']['DISCORD_TOKEN'])
# guild_id = config['discord_settings']['GUILD_ID']
guild_id = config['discord_settings']['GUILD_ID2']

@bot.command()
async def say_hello(ctx: interactions.CommandContext):
    """Make the poor robot say something."""
    await ctx.send("Hi there!")

@bot.command()
async def print_queue_length(ctx: interactions.CommandContext):
    """Shows number of prints in queue."""
    queue = PrintJob.Get_All_By_Status(PrintStatus.IN_QUEUE)
    if queue:
        await ctx.send(len(queue))
    else:
        await ctx.send("Nothing in queue!")

bot.start()
