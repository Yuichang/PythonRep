import discord
from discord.ext import tasks
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True

bot = discord.Client(intents=intents)

# user_id -> (HH, MM)
erase_schedule = {}

# user_id -> channel_id
erase_notify = {}

# guild_id -> (HH, MM)
must_sleeps = {}

# guild_id -> channel_id
notify_channels = {}

# guild_id -> 'YYYY-MM-DDHHMM' 最後に全員削除を実行した時刻
last_delete = {}

@bot.event
async def on_ready():
    print("起動に成功しました")
    if not sleep_loop.is_running():
        sleep_loop.start()
    if not disconnect_loop.is_running():
        disconnect_loop.start()

@bot.event
async def on_message(message):
    # botのメッセージは無視する
    if message.author.bot:
        return

    content = message.content.strip()

    # 毎日全員切断時間設定コマンド(毎日set)
    if content.startswith("!mset") or content.startswith("!ms"):
        if not message.guild:
            await message.channel.send("サーバー内で実行してください。")
            return

        parts = content.split()
        if len(parts) != 2:
            await message.channel.send("`!mset HH:MM` または`!mset off`で入力してください`")
            return

        guild_id = message.guild.id
        switch_ = parts[1]
        
        # must_sleep無効化
        if switch_ == "off":
            must_sleeps.pop(guild_id, None)
            notify_channels.pop(guild_id, None)
            last_delete.pop(guild_id, None)
            await message.channel.send("定期的に全員切断をoffにしました")
            return

        # 時間設定フェーズ
        if ":" not in switch_:
            await message.channel.send("切断時間を設定してください。HH:MM")
            return
        hh, mm = switch_.split(":")
        if not (hh.isdigit() and mm.isdigit()):
            await message.channel.send("時間は数字で設定してください。")
            return
        h, m = int(hh), int(mm)
        if not (0 <= h <= 23 and 0 <= m <= 59):
            await message.channel.send("時間は00:00〜23:59の間で設定してください。")
            return

        must_sleeps[guild_id] = (h, m)
        # 通知先を保存
        notify_channels[guild_id] = message.channel.id

        await message.channel.send(f"毎日 {h:02}:{m:02} に全員切断します。")
        return

    # 切断時間設定コマンド
    if content.startswith("!set"):
        sep_message = content.split()
        if len(sep_message) < 2:
            await message.channel.send("切断時間とユーザーを設定してください。HH:MM")
            return

        time_sep = sep_message[1]

        # 書式設定
        if ":" not in time_sep:
            await message.channel.send("切断時間を設定してください。HH:MM")
            return

        # 数字じゃない
        hour_str, minute_str = time_sep.split(":")
        if not (hour_str.isdigit() and minute_str.isdigit()):
            await message.channel.send("時間は数字で設定してください。")
            return

        hour = int(hour_str)
        minute = int(minute_str)

        # 時間形式じゃない
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            await message.channel.send("時間は00:00〜23:59の間で設定してください")
            return

        # @everyoneの実装
        if "@everyone" in content:
            mention = [member for member in message.guild.members if not member.bot]
        else:
            mention = message.mentions

        if not mention:
            await message.channel.send("切断するユーザーがメンションされていません。")
            return

        # 削除予定リストの更新
        for user in mention:
            erase_schedule[user.id] = (hour, minute)
            # 個別通知先の保存
            erase_notify[user.id] = message.channel.id

        user_name = ", ".join([user.display_name for user in mention])
        await message.channel.send(f"{hour:02}:{minute:02} に {user_name} を切断します。")

    # 削除予定リストの表示
    elif content.startswith("!list"):
        # リストが空
        if not erase_schedule:
            await message.channel.send("現在の切断予定はありません")
            return

        mes = "現在の切断予定:\n"
        for user_id, (h, m) in erase_schedule.items():
            user = message.guild.get_member(user_id)
            if user:
                mes += f"{user.display_name} : {h:02}:{m:02}\n"

        await message.channel.send(mes)

# 全員切断を実行するか（30秒毎）
@tasks.loop(seconds=30)
async def sleep_loop():
    now = datetime.now()
    key = now.strftime("%Y-%m-%d%H%M")

    for guild in bot.guilds:
        sleep_time = must_sleeps.get(guild.id)
        if sleep_time == (now.hour, now.minute):
      
            # まだ実行していない
            if last_delete.get(guild.id) != key:
                last_delete[guild.id] = key

                # 通知を送信
                ch_id = notify_channels.get(guild.id)
                if ch_id:
                    channel = bot.get_channel(ch_id)
                    if channel:
                        await channel.send(f"{now.hour:02}:{now.minute:02} なので全員を切断します。")

                # 全員を削除リストに追加
                for vc in guild.voice_channels:
                    for member in vc.members:
                        erase_schedule[member.id] = (now.hour, now.minute)
                        # 個別の通知先を設定する
                        erase_notify[member.id] = notify_channels[guild.id]

# 個別切断処理（10秒毎）
@tasks.loop(seconds=10)
async def disconnect_loop():
    now = datetime.now()

    # 個別の切断予定時間
    for target_id, (h, m) in list(erase_schedule.items()):
        if (h, m) == (now.hour, now.minute):
            for guild in bot.guilds:
                for vc in guild.voice_channels:
                    for member in vc.members:
                        if member.id == target_id:
                            if vc.permissions_for(guild.me).move_members:
                                await member.move_to(None)
                                # 個別切断通知
                                ch_id = erase_notify.get(member.id)
                                if ch_id:
                                    ch = bot.get_channel(ch_id)
                                    if ch:
                                        await ch.send(f"{member.display_name} を切断しました。")
                            else:
                                print(f"{member.display_name} を切断できませんでした")
                            break
                    else:
                        continue
                    break
            # 削除予定リストから削除
            del erase_schedule[target_id]
            erase_notify.pop(target_id, None)

bot.run("あなたのbotトークン")
