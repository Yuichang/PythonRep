import discord
from discord.ext import tasks
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True

bot = discord.Client(intents=intents)

# user_id -> (HH,MM)
erase_schedule = {}

@bot.event
async def on_ready():
    print("起動に成功しました")
    if not disconnect_loop.is_running():
        disconnect_loop.start()

@bot.event
async def on_message(message):

    # botのメッセージは無視する
    if message.author.bot:
        return

    content = message.content.strip()

    # 切断時間設定コマンド
    if content.startswith("!set"):
        sep_message = content.split()
        if len(sep_message) < 2:
            await message.channel.send("切断時間とユーザーを設定してください。HH:MM")
            return

        time_sep = sep_message[1]
        
        # 書式設定
        if ":" not in time_sep:
            await message.channel.send("時間はHH:MMで設定してください。")
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
            await message.channel.send("時間は 00:00〜23:59 の間で設定してください")
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

        user_name = ", ".join([user.display_name for user in mention])
        await message.channel.send(f"⏱️ {hour:02}:{minute:02} に {user_name} を切断します。")

    # 削除予定リストの表示
    elif content.startswith("!list"):
        if not erase_schedule:
            await message.channel.send("切断予定リストは空です")
            return
        
        schedule = []
        for user_id, (h, m) in erase_schedule.items():
            user = message.guild.get_member(user_id)
            if user:
                schedule.append(f"{user.display_name}: {h:02}:{m:02}")
        if schedule:
            await message.channel.send("現在の切断予定:\n" + "\n".join(schedule))
        else:
            await message.channel.send("現在の切断予定はありません")

# 切断処理の実行
@tasks.loop(seconds=30)
async def disconnect_loop():
    now = datetime.now()

    for target_id, (h, m) in list(erase_schedule.items()):
        # 削除予定の時間になった
        if h == now.hour and m == now.minute:
            # サーバーの全探索
            for guild in bot.guilds:
                # ボイスチャンネルの全探索
                for vc in guild.voice_channels:
                    for member in vc.members:
                        # 通話メンバーの全探索
                        if member.id == target_id:
                            if vc.permissions_for(guild.me).move_members:
                                # 通話から削除する
                                await member.move_to(None)
                                print(f"{member.display_name} を切断しました")
                            else:
                                print(f"{member.display_name} を切断できませんでした")
                            break
                else:
                    continue
                break
                
            # 削除予定リストから削除
            del erase_schedule[target_id]

bot.run("あなたのbotトークンを入力")
