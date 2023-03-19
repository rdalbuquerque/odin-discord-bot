import discord
from discord.ext import tasks
import server
import asyncio
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
discclient = discord.Client(intents=intents)

valheim = server.Valheim(cluster=os.getenv('VALHEIM_EC2_CLUSTER'))
help_msg = "- *server start*: start Valheim server, reporting every status change until it's up and running\n- *server status*: get Valheim server status\n- *server stop*: stop Valheim server\nOBS: I'll only answer if you mention me with @Odin"

@discclient.event
async def on_ready():
    cleanup_loop.start()
    print('We have logged in as {0.user}'.format(discclient))

@discclient.event
async def on_message(message):
    if message.author == discclient.user:
        return

    if len(message.mentions) > 0:
        if message.mentions[0].id == discclient.user.id:
            if 'help' in message.content:
                await message.channel.send(help_msg)

            elif 'storage status' in message.content:
                v = valheim.get_storage_details()
                print(v)
                await message.channel.send(v)

            elif 'server start' in message.content:
                valheim.guild = message.guild
                server_loaded = False
                task = valheim.task_status()
                cur_task_status = task[0]
                print(f"current task status is: {cur_task_status}")
                if valheim.status == 'LOADED':
                    await message.channel.send("Server already up and running, enjoy!")
                    server_loaded = True

                if not server_loaded:
                    valheim.status = 'STARTING'
                    await message.channel.send("Server is starting, I'll send updates on every status change")
                    async with message.channel.typing():
                        await valheim.start()

                    last_task_status = None
                    while cur_task_status != 'RUNNING':
                        task = valheim.task_status()
                        cur_task_status = task[0]
                        async with message.channel.typing():
                            while cur_task_status == last_task_status:
                                task = valheim.task_status()
                                cur_task_status = task[0]
                                print(f"current task {task[1]} status is: {cur_task_status}")
                                await asyncio.sleep(2)
                        await message.channel.send(f"Server is starting, status: {cur_task_status}")
                        last_task_status = cur_task_status

                    await message.channel.send(f"Server is running, now loading world, I'll let you know when it's loaded")
                    valheim.status = 'LOADING'
                    cur_gameserver_status = valheim.gameserver_status(task[1])
                    print(f"current gameserver status is: {cur_gameserver_status}")
                    async with message.channel.typing():
                        while cur_gameserver_status  != 'LOADED':
                            cur_gameserver_status = valheim.gameserver_status(task[1])
                            print(f"current gameserver status is: {cur_gameserver_status}")
                            await asyncio.sleep(2)

                    await message.channel.send("Server is up and running, enjoy!")
                    valheim.status = 'LOADED'
                    server_loaded = True

            elif 'server stop' in message.content:
                if valheim.status != 'STOPPED':
                    valheim.stop_valheim_process()
                    if valheim.status == 'LOADED':
                        await message.channel.send("Making backup before shutdown...")
                        async with message.channel.typing():
                                await discclient.loop.run_in_executor(None, valheim.make_valheim_bkp)
                    valheim.remove_infra()
                    valheim.status = 'STOPPED'
                    await message.channel.send("server down, hope you had a great time!")
                else:
                    await message.channel.send("server is already stopped")


            elif 'server status' in message.content:
                await message.channel.send(f"Server is {valheim.status}")

            elif 'server backup' in message.content:
                await discclient.loop.run_in_executor(None, valheim.make_valheim_bkp)
            
            else:
                print(message.content)
                await message.channel.send(f"I don't know what this is, I know 'server status', 'server start' and 'server stop'")

@tasks.loop(seconds=30*60)
async def cleanup_loop():
    print('starting cleanup_loop')
    print('evaluating valheim.status...')
    if valheim.status == 'LOADED':
        valheim.cleanup_old_days(4)
    else:
        print(f'cleanup skipped because valheim.status is {valheim.status}')


async def main():
    await discclient.start(os.getenv('ODIN_BOT_TOKEN'))

if __name__ == '__main__':
    asyncio.run(main())