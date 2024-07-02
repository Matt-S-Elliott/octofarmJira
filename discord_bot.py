import discord
import logging
from classes.permissionCode import *
from classes.gcodeCheckItem import *

set_sql_debug(False)  # Shows the SQL queries pony is running in the console.
db.bind(provider='sqlite', filename='octofarmJira_database.sqlite', create_db=True)  # Establish DB connection.
db.generate_mapping(create_tables=True)  # Have to generate mapping to use Pony. Will create tables that do not already exist.

logging.basicConfig(level=logging.INFO)

bot = discord.Bot()


@bot.event
async def on_ready():
    print("I'M ALIVE!")
    channel = bot.get_channel(1253468611310387342)
    await channel.send("Bot is running!")

@bot.slash_command(name="queueinfo", description="Basic info about the print queue.")
async def hello(ctx: discord.ApplicationContext):
    queuedJobs = PrintJob.Get_All_By_Status(PrintStatus.IN_QUEUE)
    printingJobs = PrintJob.Get_All_By_Status(PrintStatus.PRINTING)
    response = "Printing: " + str(len(printingJobs)) + " Queued: " + str(len(queuedJobs))
    await ctx.respond(response)


bot.load_extension("cogs.printFinishedCog")
bot.run('')
