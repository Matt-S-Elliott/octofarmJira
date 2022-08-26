import yaml
import interactions

with open("config_files/config.yml", "r") as yamlfile:
    config = yaml.load(yamlfile, Loader=yaml.FullLoader)

bot = interactions.Client(token=config['discord_settings']['DISCORD_TOKEN'])
guild_id = config['discord_settings']['GUILD_ID']



bot.start()
