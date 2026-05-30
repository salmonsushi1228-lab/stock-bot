import discord
from discord.ext import commands
import sqlite3
import yfinance as yf
import io
import matplotlib.pyplot as plt
import mplfinance as mpf
from datetime import date


# 1. 디스코드 봇 설정
token = "input_your_token"
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 봇이 다룰 주식 종목 딱 20개로 제한 (상단에 배치)
ALLOWED_STOCKS = {
    "테슬라": "TSLA", "애플": "AAPL", "엔비디아": "NVDA", "마이크로소프트": "MSFT",
    "아마존": "AMZN", "구글": "GOOGL", "메타": "META", "넷플릭스": "NFLX", "비트코인ETF": "IBIT",
    "삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "카카오": "035720.KS", "네이버": "035420.KS",
    "현대차": "005380.KS", "기아": "000270.KS", "셀트리온": "068270.KS", "포스코홀딩스": "005490.KS",
    "에코프로비엠": "247540.KQ", "신한지주": "055550.KS", "국민은행": "105560.KS" # KB금융
}

# 안내 메시지용 리스트 문자열 미리 생성
STOCKS_GUIDE_TEXT = ", ".join([f"`{name}`" for name in ALLOWED_STOCKS.keys()])

# 2. 데이터베이스 연결 및 테이블 초기화
conn = sqlite3.connect('real_stock_final.db')
cursor = conn.cursor()

# 유저 잔고 테이블 (기본 자산 50,000,000원 / 출석체크 날짜 포함)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        balance INTEGER DEFAULT 50000000,
        last_daily TEXT DEFAULT '1970-01-01'
    )
''')
# 유저 보유 주식 테이블
cursor.execute('''
    CREATE TABLE IF NOT EXISTS holdings (
        user_id TEXT,
        ticker TEXT,
        quantity INTEGER,
        PRIMARY KEY (user_id, ticker)
    )
''')
conn.commit()

@bot.event
async def on_ready():
    print(f"==========================================")
    print(f"📈 현실 주식 모의투자 봇 [{bot.user.name}] 구동 완료!")
    print(f"==========================================")
    activity = f"{len(bot.guilds)}개의 서버에서 주식 알려주는 중"
    await bot.change_presence(status=discord.Status.online, activity=activity)
    try:
        synced = await bot.tree.sync()
        print(f"🔗 {len(synced)}개의 슬래시 명령어 동기화 성공!")
    except Exception as e:
        print(f"❌ 명령어 동기화 실패: {e}")




# 유저가 DB에 없을 때 자동으로 등록해주는 함수
def check_user(user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (str(user_id),))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (str(user_id),))
        conn.commit()


# [기능 1] 📆 출석체크 (매일 지원금 10만원 지급)
@bot.tree.command(name="출석체크", description="매일 한 번 주식 투자 지원금 10만 원을 받습니다.")
async def daily_money(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    check_user(user_id)

    today = str(date.today())
    cursor.execute("SELECT last_daily, balance FROM users WHERE user_id = ?", (user_id,))
    last_daily, current_balance = cursor.fetchone()

    if last_daily == today:
        await interaction.response.send_message("❌ 이미 오늘 지원금을 받으셨습니다! 내일 다시 시도해 주세요. 💸", ephemeral=True)
        return

    reward = 100000
    new_balance = current_balance + reward

    cursor.execute("UPDATE users SET balance = ?, last_daily = ? WHERE user_id = ?", (new_balance, today, user_id))
    conn.commit()

    embed = discord.Embed(title="📆 출석체크 완료!", color=0xf1c40f)
    embed.description = f"**{interaction.user.display_name}**님께 일일 지원금이 지급되었습니다."
    embed.add_field(name="💰 획득 금액", value=f"+ {reward:,} 원", inline=True)
    embed.add_field(name="💳 현재 잔고", value=f"{new_balance:,} 원", inline=True)
    embed.set_footer(text="내일 또 오셔서 지원금을 받아 가세요!")
    await interaction.response.send_message(embed=embed)


# [기능 2 수정] 📊 제한된 종목 주가조회 + 30일 차트
@bot.tree.command(name="주가조회", description="지정된 우량 주식의 가격과 차트를 조회합니다.")
async def stock_price(interaction: discord.Interaction, 종목명: str):
    await interaction.response.defer()
    search_keyword = 종목명.strip()

    # 목록에 없는 주식이면 컷
    if search_keyword not in ALLOWED_STOCKS:
        await interaction.followup.send(
            f"❌ 거래 가능한 종목이 아닙니다!\n"
            f"**[거래 가능 종목]**\n{STOCKS_GUIDE_TEXT}"
        )
        return

    actual_ticker = ALLOWED_STOCKS[search_keyword]

    try:
        stock = yf.Ticker(actual_ticker)
        history_data = stock.history(period='1mo')

        current_price = history_data['Close'].iloc[-1]
        currency = stock.info.get('currency', 'USD')
        long_name = stock.info.get('longName', search_keyword)

        # 📈 차트 생성 (안전한 nightclouds 스타일 사용)
        style = mpf.make_mpf_style(base_mpf_style='nightclouds', rc={'font.size': 10})
        buf = io.BytesIO()
        mpf.plot(
            history_data,
            type='candle',
            style=style,
            volume=True,
            mav=(5, 20),
            title=f"\n{actual_ticker} - 1 Month Chart",
            savefig=dict(fname=buf, dpi=100, bbox_inches='tight')
        )
        buf.seek(0)
        chart_file = discord.File(buf, filename="chart.png")

        # 임베드 디자인
        embed = discord.Embed(title=f"📊 [주가 정보] {long_name}", color=0x3498db)
        embed.add_field(name="종목명", value=search_keyword, inline=True)
        embed.add_field(name="종목 코드", value=actual_ticker, inline=True)
        embed.add_field(name="현재 주가", value=f"{current_price:,.2f} {currency}", inline=True)
        embed.set_image(url="attachment://chart.png")

        await interaction.followup.send(embed=embed, file=chart_file)
        buf.close()

    except Exception as e:
        await interaction.followup.send(f"❌ 주가를 가져오는 중 오류가 발생했습니다: {e}")


# [기능 3 수정] 🛒 제한된 종목 주식 매수
@bot.tree.command(name="매수", description="지정된 우량 주식을 구매합니다.")
async def buy_stock(interaction: discord.Interaction, 종목명: str, 수량: int):
    if 수량 <= 0:
        await interaction.response.send_message("❌ 1주 이상부터 구매할 수 있습니다.", ephemeral=True)
        return

    await interaction.response.defer()
    user_id = str(interaction.user.id)
    check_user(user_id)
    search_keyword = 종목명.strip()

    if search_keyword not in ALLOWED_STOCKS:
        await interaction.followup.send(f"❌ 거래 가능한 종목이 아닙니다!\n**[거래 가능 종목]**\n{STOCKS_GUIDE_TEXT}")
        return

    actual_ticker = ALLOWED_STOCKS[search_keyword]

    try:
        stock = yf.Ticker(actual_ticker)
        todays_data = stock.history(period='1d')

        price = int(todays_data['Close'].iloc[-1])
        total_cost = price * 수량

        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        balance = cursor.fetchone()[0]

        if balance < total_cost:
            await interaction.followup.send(f"❌ 잔액이 부족합니다! 필요한 금액: {total_cost:,} 원 | 현재 잔액: {balance:,} 원")
            return

        new_balance = balance - total_cost
        cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))

        # DB에는 관리를 편하게 하기 위해 한글 '종목명'으로 저장합니다.
        cursor.execute("SELECT quantity FROM holdings WHERE user_id = ? AND ticker = ?", (user_id, search_keyword))
        holding = cursor.fetchone()

        if holding:
            cursor.execute("UPDATE holdings SET quantity = quantity + ? WHERE user_id = ? AND ticker = ?", (수량, user_id, search_keyword))
        else:
            cursor.execute("INSERT INTO holdings (user_id, ticker, quantity) VALUES (?, ?, ?)", (user_id, search_keyword, 수량))

        conn.commit()
        await interaction.followup.send(f"✅ **{search_keyword}** 주식을 {수량}주 매수했습니다!\n💳 체결 단가: {price:,} 원 | 총 소모 잔액: {total_cost:,} 원")
    except Exception as e:
        await interaction.followup.send(f"❌ 매수 처리 중 오류 발생: {e}")


# [기능 4] 💵 제한된 종목 주식 매도
@bot.tree.command(name="매도", description="보유 중인 주식을 판매합니다.")
async def sell_stock(interaction: discord.Interaction, 종목명: str, 수량: int):
    if 수량 <= 0:
        await interaction.response.send_message("❌ 1주 이상부터 판매할 수 있습니다.", ephemeral=True)
        return

    await interaction.response.defer()
    user_id = str(interaction.user.id)
    check_user(user_id)
    search_keyword = 종목명.strip()

    # 내가 가진 주식 이름으로 대조
    cursor.execute("SELECT quantity FROM holdings WHERE user_id = ? AND ticker = ?", (user_id, search_keyword))
    holding = cursor.fetchone()

    if not holding or holding[0] < 수량:
        current_qty = holding[0] if holding else 0
        await interaction.followup.send(f"❌ 보유 주식이 부족합니다! 현재 보유량: {current_qty}주")
        return

    actual_ticker = ALLOWED_STOCKS[search_keyword]

    try:
        stock = yf.Ticker(actual_ticker)
        todays_data = stock.history(period='1d')
        price = int(todays_data['Close'].iloc[-1])
        total_earnings = price * 수량

        new_quantity = holding[0] - 수량
        cursor.execute("UPDATE holdings SET quantity = ? WHERE user_id = ? AND ticker = ?", (new_quantity, user_id, search_keyword))

        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (total_earnings, user_id))
        conn.commit()

        await interaction.followup.send(f"💵 **{search_keyword}** 주식 {수량}주를 매도했습니다!\n💳 체결 단가: {price:,} 원 | 획득한 금액: {total_earnings:,} 원")
    except Exception as e:
        await interaction.followup.send(f"❌ 매도 처리 중 오류 발생: {e}")


# [기능 5] 💳 계좌조회 (지갑 및 보유 주식 현황)
@bot.tree.command(name="계좌조회", description="현재 내 잔고와 보유 중인 주식을 확인합니다.")
async def my_wallet(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    check_user(user_id)

    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    balance = cursor.fetchone()[0]

    cursor.execute("SELECT ticker, quantity FROM holdings WHERE user_id = ? AND quantity > 0", (user_id,))
    holdings = cursor.fetchall()

    embed = discord.Embed(title=f"💰 {interaction.user.display_name}님의 계좌 현황", color=0x2ecc71)
    embed.add_field(name="예수금 (보유 현금)", value=f"{balance:,} 원", inline=False)

    if holdings:
        stock_list = ""
        for ticker, qty in holdings:
            stock_list += f"• **{ticker}**: {qty}주\n"
        embed.add_field(name="보유 주식 현황", value=stock_list, inline=False)
    else:
        embed.add_field(name="보유 주식 현황", value="보유 중인 주식이 없습니다.", inline=False)

    await interaction.response.send_message(embed=embed)


# 봇 실행 토큰 입력 (디스코드 개발자 포털에서 발급받은 토큰을 넣으세요)
bot.run(')
