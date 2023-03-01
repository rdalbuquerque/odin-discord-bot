import discord
import server
import asyncio
import os

valheim = server.Valheim(cluster=os.getenv('VALHEIM_EC2_CLUSTER'))
valheim_pwd = os.getenv('VALHEIM_PWD')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
discclient = discord.Client(intents=intents)

help_msg = "- *server start*: start Valheim server, reporting every status change until it's up and running\n- *server status*: get Valheim server status\n- *server stop*: stop Valheim server\nOBS: I'll only answer if you mention me with @Odin"

@discclient.event
async def on_ready():
    print('We have logged in as {0.user}'.format(discclient))

@discclient.event
async def on_message(message):
    if message.author == discclient.user:
        return

    if len(message.mentions) > 0:
        if message.mentions[0].id == discclient.user.id:
            if 'help' in message.content:
                await message.channel.send(help_msg)

            if 'password' in message.content:
                await message.channel.send(valheim_pwd)

            elif 'storage status' in message.content:
                v = valheim.get_volume_details()
                print(v)
                await message.channel.send(v)

            elif 'server start' in message.content:
                server_loaded = False
                task = valheim.task_status()
                cur_task_status = task[0]
                print(f"current task status is: {cur_task_status}")
                if cur_task_status != 'STOPPED':
                    if valheim.gameserver_status(task[1]) == 'LOADED':
                        await message.channel.send("Server already up and running, enjoy!")
                        server_loaded = True

                if not server_loaded:
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
                    cur_gameserver_status = valheim.gameserver_status(task[1])
                    print(f"current gameserver status is: {cur_gameserver_status}")
                    async with message.channel.typing():
                        while cur_gameserver_status  != 'LOADED':
                            cur_gameserver_status = valheim.gameserver_status(task[1])
                            print(f"current gameserver status is: {cur_gameserver_status}")
                            await asyncio.sleep(2)

                    await message.channel.send("Server is up and running, enjoy!")
                    server_loaded = True

            elif 'server stop' in message.content:
                valheim.stop()
                await message.channel.send("server down, hope you had a great time!")

            elif 'server status' in message.content:
                if valheim.status() == 'LOADED':
                    await message.channel.send("Server is up and running, enjoy!")
                else:
                    await message.channel.send(f"Server is {valheim.status().lower()}")
            
            else:
                print(message.content)
                await message.channel.send(f"I don't know what this is, I know 'server status', 'server start' and 'server stop'")

# discclient.loop.create_task(valheim.manage_valheim_volume())
discclient.run(os.getenv('ODIN_BOT_TOKEN'))
