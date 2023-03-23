import json
import discord
from discord.ext import tasks
from discord.ext import commands
import server
import asyncio
import os
import storage.s3 as storage

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
bot = commands.Bot(command_prefix='.o ', activity=discord.Activity(name=".o help",type=discord.ActivityType.listening), intents=intents)

s3 = storage.S3(bucket='valheim-worlds-config')
worlds_json = json.loads(s3.get('worlds.json'))

# iterate over the worlds and instantiate Valheim for each
valheim_worlds = {}
for k, v in worlds_json.items():
    cluster_instance = server.Valheim(cluster=v["clustername"])
    valheim_worlds.update({k: cluster_instance})

@bot.event
async def on_ready():
    print('Bot is ready')

@bot.command(name="storage-status", brief="Return storage usage %", help="It runs a df -h inside the container, showing the usage % of every mount")
async def storage_status(ctx):
    v = valheim_worlds[ctx.guild.name].get_storage_details()
    print(v)
    await ctx.send(v)

@bot.command(name="server-status", brief="Return server status", help="Server status: if server is fully loaded, the status will be LOADED")
async def server_status(ctx):
    try:
        sv_status = valheim_worlds[ctx.guild.name].status
        await ctx.send(f"Server {worlds_json[ctx.guild.name]['worldname']} is {sv_status}")
    except Exception as e:
        print(e)
        await ctx.send(f"Error getting status")

@bot.command(name="server-start", brief="Start Valheim", help="It goes thru the following steps: 1- Scale up VM, 2- Scale up Valheim service, 3- Wait for the 'Game connected' on logs to report LOADED state")
async def server_start(ctx):
    valheim_worlds[ctx.guild.name].guild = ctx.guild
    server_loaded = False
    task = valheim_worlds[ctx.guild.name].task_status()
    cur_task_status = task[0]
    print(f"current task status is: {cur_task_status}")
    if valheim_worlds[ctx.guild.name].status == 'LOADED':
        await ctx.send("Server already up and running, enjoy!")
        server_loaded = True

    if not server_loaded:
        valheim_worlds[ctx.guild.name].status = 'STARTING'
        await ctx.send(f"Server {worlds_json[ctx.guild.name]['worldname']} is starting, I'll send updates on every status change")
        async with ctx.typing():
            await valheim_worlds[ctx.guild.name].start()

        last_task_status = None
        while cur_task_status != 'RUNNING':
            task = valheim_worlds[ctx.guild.name].task_status()
            cur_task_status = task[0]
            async with ctx.typing():
                while cur_task_status == last_task_status:
                    task = valheim_worlds[ctx.guild.name].task_status()
                    cur_task_status = task[0]
                    print(f"[{worlds_json[ctx.guild.name]['worldname']}] current task {task[1]} status is: {cur_task_status}")
                    await asyncio.sleep(2)
            await ctx.send(f"Server is starting, status: {cur_task_status}")
            last_task_status = cur_task_status

        await ctx.send(f"Server is running, now loading world, I'll let you know when it's loaded")
        valheim_worlds[ctx.guild.name].status = 'LOADING'
        cur_gameserver_status = valheim_worlds[ctx.guild.name].gameserver_status(task[1])
        print(f"[{worlds_json[ctx.guild.name]['worldname']}] current gameserver status is: {cur_gameserver_status}")
        async with ctx.typing():
            while cur_gameserver_status  != 'LOADED':
                cur_gameserver_status = valheim_worlds[ctx.guild.name].gameserver_status(task[1])
                print(f"current gameserver status is: {cur_gameserver_status}")
                await asyncio.sleep(2)

        await ctx.send("Server is up and running, enjoy!")
        valheim_worlds[ctx.guild.name].status = 'LOADED'
        server_loaded = True

@bot.command(name="server-stop", brief="Stop server", help="It goes thru the following steps: 1- stops Valheim process, 2- Make Valheim bkp, 3- Scale down VM")
async def server_stop(ctx):
    if valheim_worlds[ctx.guild.name].status != 'STOPPED':
        valheim_worlds[ctx.guild.name].stop_valheim_process()
        if valheim_worlds[ctx.guild.name].status == 'LOADED':
            await ctx.send("Making backup before shutdown...")
            async with ctx.typing():
                    await bot.loop.run_in_executor(None, valheim_worlds[ctx.guild.name].make_valheim_bkp)
            valheim_worlds[ctx.guild.name].remove_infra()
            valheim_worlds[ctx.guild.name].status = 'STOPPED'
            await ctx.channel.send(f"server {worlds_json[ctx.guild.name]['worldname']} down, hope you had a great time!")
        else:
            await ctx.channel.send(f"server {worlds_json[ctx.guild.name]['worldname']} is already stopped")


@tasks.loop(seconds=30*60)
async def cleanup_loop():
    for guild in worlds_json:
        if valheim_worlds[guild].status == 'LOADED':
            print(f'{worlds_json[guild]["worldname"]} is loaded, cleaning up old valheim days')
            valheim_worlds[guild].cleanup_old_days(4)
        else:
            print(f'cleanup skipped because {worlds_json[guild]["worldname"]} is {valheim_worlds[guild].status}')

bot.run(os.getenv('ODIN_BOT_TOKEN'))
