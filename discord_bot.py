import discord
import logging
from classes.permissionCode import *
from classes.gcodeCheckItem import *
from discord.ext import tasks
from pony import *
from classes.printJob import *

set_sql_debug(False)  # Shows the SQL queries pony is running in the console.
db.bind(provider='sqlite', filename='octofarmJira_database.sqlite', create_db=True)  # Establish DB connection.
db.generate_mapping(create_tables=True)  # Have to generate mapping to use Pony. Will create tables that do not already exist.

logging.basicConfig(level=logging.INFO)

bot = discord.Bot()

db = Database()

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
    with db_session:
        guild = await bot.fetch_guild(771458872379834468)
        channel = await guild.fetch_channel(1253468611310387342)

        for job in PrintJob.select():
            if job.status == PrintStatus.NEEDS_CLEAR:
                await channel.send(job.job_name + " may be complete!")
                job.status = PrintStatus.NEEDS_CLEAR_REPORTED

bot.load_extension("cogs.printFinishedCog")
check_finished.start()
bot.run('')
