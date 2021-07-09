import logging
from threading import Timer

import discord
from discord.ext import commands
from configobj import ConfigObj

logging.basicConfig(level=logging.INFO)
prefix = "?"


async def admin_only(ctx):
    permissions = ctx.author.guild_permissions
    return permissions.administrator


async def globally_block_dms(ctx):
    return ctx.guild is not None


class AutochannelClient(commands.Bot):
    autochannels = {}
    temp_channels = {}

    users_on_cd = []
    channel_to_move_member_on_cd = None

    def __init__(self, command_prefix, **options):
        self.cfg = ConfigObj('config.ini', list_values=False, encoding='utf8')

        super().__init__(command_prefix, **options)

        self.add_check(admin_only)
        self.add_check(globally_block_dms)

    async def on_ready(self):
        try:
            self.channel_to_move_member_on_cd = self.get_channel(int(self.cfg['channel_to_move_member_on_cd']))
        except ValueError:
            pass

        for ch_id in self.cfg['Channels'].keys():
            channel = self.get_channel(int(ch_id))
            if channel is not None:
                self.save_autochannel(int(ch_id))
            else:
                logging.info(f"Channel {ch_id} not found, deleting...")
                await self.delete_autochannel(int(ch_id), True)

        logging.info("Advertisement loaded in {0} servers".format(len(self.guilds)))

    async def close(self):
        for ch_id in self.temp_channels:
            temp_ch = self.get_channel(ch_id)
            if temp_ch is not None:
                await self.delete_temp_channel(temp_ch)
        await super().close()

    async def on_command_error(self, ctx, exception):
        if isinstance(exception, (commands.errors.MissingRequiredArgument, commands.errors.TooManyArguments)):
            await self.send_error_embed(ctx, 'incorrect_command_usage', ctx.command.usage.format(prefix))
        elif isinstance(exception, commands.errors.BadArgument):
            await self.send_error_embed(ctx, 'bad_command_arguments')
        elif isinstance(exception, commands.errors.CommandNotFound) or isinstance(exception, commands.errors.CheckFailure):
            pass
        else:
            await super().on_command_error(ctx, exception)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if isinstance(channel, discord.VoiceChannel) and channel.id in self.autochannels:
            await self.delete_autochannel(channel.id, True)

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState):
        if after.channel is not None:
            if after.channel.id in self.autochannels:

                # if member.id not in self.users_on_cd:
                #     self.users_on_cd.append(member.id)
                #     timer = Timer(10, lambda member_id: self.users_on_cd.remove(member_id), [member.id])
                #     timer.start()
                #
                #     await self.create_temp_channel_and_move(after.channel, member)
                # elif self.channel_to_move_member_on_cd is not None:
                #     await member.move_to(self.channel_to_move_member_on_cd)
                await self.create_temp_channel_and_move(after.channel, member)

        if before.channel is not None and before.channel.id in self.temp_channels:
            if not before.channel.members:
                await self.delete_temp_channel(before.channel)

    def save_autochannel(self, ch_id: int, name: str = "", save_cfg: bool = False):
        self.autochannels[ch_id] = {}
        self.autochannels[ch_id]['count'] = 0
        self.autochannels[ch_id]['temp_channels'] = []

        if save_cfg:
            ch_id = str(ch_id)
            client.cfg['Channels'][ch_id] = {}
            client.cfg['Channels'][ch_id]['name'] = name
            client.cfg.write()

    async def delete_autochannel(self, ch_id: int, save_cfg: bool = False):
        if ch_id in self.autochannels:
            for temp_channel in self.autochannels[ch_id]['temp_channels']:
                temp_ch: discord.VoiceChannel = self.get_channel(temp_channel)
                if temp_ch is not None:
                    await temp_ch.delete()

            self.autochannels.__delitem__(ch_id)
        if save_cfg:
            self.cfg['Channels'].__delitem__(str(ch_id))
            self.cfg.write()

    async def create_temp_channel_and_move(self, autochannel: discord.VoiceChannel, member: discord.Member):
        temp_channel = await autochannel.clone(name=self.cfg['Channels'][str(autochannel.id)]['name'] +
                                               " #" + str(self.autochannels[autochannel.id]['count'] + 1))

        self.temp_channels[temp_channel.id] = {}
        self.temp_channels[temp_channel.id]['number'] = self.autochannels[autochannel.id]['count']
        self.temp_channels[temp_channel.id]['autochannel'] = autochannel.id

        self.autochannels[autochannel.id]['count'] += 1
        self.autochannels[autochannel.id]['temp_channels'].append(temp_channel.id)

        await member.move_to(temp_channel)

    async def delete_temp_channel(self, channel: discord.VoiceChannel):
        temp_ch = self.temp_channels[channel.id]

        self.autochannels[temp_ch['autochannel']]['temp_channels'].remove(channel.id)
        num_of_temp_ch = len(self.autochannels[temp_ch['autochannel']]['temp_channels'])
        if temp_ch['number'] > num_of_temp_ch:
            self.autochannels[temp_ch['autochannel']]['count'] = num_of_temp_ch

        self.temp_channels.__delitem__(channel.id)

        await channel.delete()

    def get_message(self, message: str, *args):
        return (self.cfg['Messages'][message] % args).replace('\\n', '\n')

    async def send_success_embed(self, ctx, message: str, *args):
        embed = discord.Embed(
            color=discord.Colour.green(),
            description=self.get_message(message, *args))
        await ctx.send(embed=embed)

    async def send_error_embed(self, ctx, message: str, *args):
        embed = discord.Embed(
            color=discord.Colour.red(),
            description=self.get_message(message, *args))
        await ctx.send(embed=embed)


client = AutochannelClient(prefix, case_insensitive=True, help_command=None)


@client.command(name="create-autoch", usage="{}create-autoch <auto_channel> <temp_channels_name>")
async def create_autochannel(ctx, channel: discord.VoiceChannel, *, name):
    if channel.id not in client.autochannels:
        if name == "":
            name = channel.name
        client.save_autochannel(channel.id, name, True)
        await client.send_success_embed(ctx, "create_success")
    else:
        await client.send_error_embed(ctx, "create_already_present")


client.run(client.cfg['Token'])
