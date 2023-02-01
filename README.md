# odin-discord-bot
Discord bot to manage this [Valheim server](https://github.com/rdalbuquerque/valheim-server-asg-ec2)

# goal
The goal of this Discord bot is to manage Valheim server state. By mentioning the bot with messages *server start*, *server stop*, and *server status*, the Discord user
can easily start, stop or check Valheim server state.

# infra
The bot runs on an ECS container using Fargate spot capacity provider. The Terraform code is [here](https://github.com/rdalbuquerque/odin-discord-bot/tree/main/infra)

# next steps
Since this bot is a long running Discord client and not a Lambda function we could have features like:
- cheking who is online
- usage report
- live billing calculations

One other important capability would be to manage multiple Valheim servers for multiple Discord servers




