import discord
import logging
from classes.permissionCode import *
from classes.gcodeCheckItem import *
from discord.ext import tasks

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
    
@tasks.loop(seconds=120)
async def check_finished():
    with open('botnotifier.json', 'r') as file:
        current = []
        try:
            current = json.loads(file.read())
            print(current)
        except Exception as e:
            print(e)
    with open('botnotifier.json', 'w+') as file:

        if len(current) > 0:
            guild = await bot.fetch_guild(771458872379834468)
            channel = await guild.fetch_channel(1253468611310387342)
            for fin in current:
                await channel.send(str(fin) + " may be complete!")
        file.write(json.dumps([]))


bot.load_extension("cogs.printFinishedCog")
check_finished.start()
bot.run('')
