#!/usr/bin/env python3
"""
OTP মনিটর বট - আপডেটেড ইউজার এজেন্ট ও কুকি সহ
"""

import asyncio
import aiohttp
import json
import logging
import re
import os
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

# টেলিগ্রাম ইম্পোর্ট
try:
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.error import TelegramError
except ImportError:
    print("❌ python-telegram-bot ইনস্টল নেই। রান করুন: pip install python-telegram-bot")
    sys.exit(1)

# ============= কনফিগারেশন সেকশন (আপডেটেড) =============
class Config:
    """সব কনফিগারেশন এখানে - সর্বশেষ আপডেট"""
    
    # টেলিগ্রাম কনফিগ
    TELEGRAM_BOT_TOKEN = "5929619535:AAGsgoN5pYczsKWOGqVWTrslk0qJr2jJVYA"
    GROUP_CHAT_ID = "-1001153782407"
    
    # প্যানেল কনফিগ - আপডেটেড
    PANEL_URL = "http://217.182.195.194/ints/agent/res/data_smscdr.php"
    PANEL_SESSKEY = "Q05RR0FSUEFCTw=="
    PANEL_COOKIE = "50febb14d463e2c22c150e565816271d"
    PANEL_REFERER = "http://217.182.195.194/ints/agent/SMSCDRStats"
    PANEL_HOST = "217.182.195.194"
    
    # বাটাম লিংক
    MAIN_CHANNEL_LINK = "https://t.me/updaterange"
    NUMBER_BOT_LINK = "https://t.me/Updateotpnew_bot"
    
    # মনিটরিং সেটিংস
    CHECK_INTERVAL = 2
    FETCH_LIMIT = 50
    REQUEST_TIMEOUT = 15
    
    # ফাইল স্টোরেজ
    PROCESSED_FILE = "processed_otps.json"


# ============= লগিং =============
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ============= কান্ট্রি ডাটাবেস =============
COUNTRY_MAP = {
    "880": {"flag": "🇧🇩", "name": "Bangladesh"},
    "91": {"flag": "🇮🇳", "name": "India"},
    "1": {"flag": "🇺🇸", "name": "USA"},
    "44": {"flag": "🇬🇧", "name": "UK"},
    "92": {"flag": "🇵🇰", "name": "Pakistan"},
    "966": {"flag": "🇸🇦", "name": "Saudi Arabia"},
    "971": {"flag": "🇦🇪", "name": "UAE"},
    "261": {"flag": "🇲🇬", "name": "Madagascar"},
    "20": {"flag": "🇪🇬", "name": "Egypt"},
    "90": {"flag": "🇹🇷", "name": "Turkey"},
    "98": {"flag": "🇮🇷", "name": "Iran"},
    "93": {"flag": "🇦🇫", "name": "Afghanistan"},
    "94": {"flag": "🇱🇰", "name": "Sri Lanka"},
    "977": {"flag": "🇳🇵", "name": "Nepal"},
    "84": {"flag": "🇻🇳", "name": "Vietnam"},
    "66": {"flag": "🇹🇭", "name": "Thailand"},
    "60": {"flag": "🇲🇾", "name": "Malaysia"},
    "65": {"flag": "🇸🇬", "name": "Singapore"},
    "63": {"flag": "🇵🇭", "name": "Philippines"},
    "62": {"flag": "🇮🇩", "name": "Indonesia"},
    "81": {"flag": "🇯🇵", "name": "Japan"},
    "82": {"flag": "🇰🇷", "name": "South Korea"},
    "86": {"flag": "🇨🇳", "name": "China"},
    "7": {"flag": "🇷🇺", "name": "Russia"},
    "49": {"flag": "🇩🇪", "name": "Germany"},
    "33": {"flag": "🇫🇷", "name": "France"},
    "39": {"flag": "🇮🇹", "name": "Italy"},
    "34": {"flag": "🇪🇸", "name": "Spain"},
    "55": {"flag": "🇧🇷", "name": "Brazil"},
    "52": {"flag": "🇲🇽", "name": "Mexico"},
    "61": {"flag": "🇦🇺", "name": "Australia"},
    "64": {"flag": "🇳🇿", "name": "New Zealand"},
    "27": {"flag": "🇿🇦", "name": "South Africa"},
}


def get_country_from_phone(phone_number: str) -> Dict:
    digits = re.sub(r'\D', '', str(phone_number))
    for length in range(4, 1, -1):
        code = digits[:length]
        if code in COUNTRY_MAP:
            return COUNTRY_MAP[code]
    return {"flag": "🌍", "name": "Unknown"}


def extract_otp(text: str) -> Optional[Dict]:
    patterns = [
        (r'#\s*(\d{6,10})', 'hashtag'),
        (r'\b(\d{3}-\d{3})\b', 'dash'),
        (r'\b(\d{6})\b', '6_digit'),
        (r'\b(\d{5})\b', '5_digit'),
        (r'\b(?!19|20)\d{4}\b', '4_digit'),
        (r'code[:\s]+(\d{4,8})', 'code_word'),
        (r'OTP[:\s]+(\d{4,8})', 'otp_word'),
        (r'Your\s+\w+\s+code\s+(\d{4,8})', 'your_code'),
        (r'verification\s+code[:\s]+(\d{4,8})', 'verification'),
        (r'🔐\s*(\d{4,8})', 'lock'),
    ]
    
    for pattern, name in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            code = match.group(1) if match.lastindex else match.group(0)
            if '#' in pattern:
                code = f"#{code}"
            clean = re.sub(r'\D', '', code)
            if len(clean) == 4 and 2020 <= int(clean) <= 2030:
                continue
            return {'code': code, 'type': name, 'clean': clean}
    return None


def extract_platform(text: str, raw: str = "") -> str:
    if raw and raw.upper() != "UNKNOWN":
        return raw.upper()
    
    platforms = ['FACEBOOK', 'INSTAGRAM', 'WHATSAPP', 'TELEGRAM', 'GMAIL', 
                 'GOOGLE', 'TWITTER', 'DISCORD', 'PAYPAL', 'AMAZON', 'APPLE']
    for p in platforms:
        if p in text.upper():
            return p
    return "SERVICE"


def format_message(phone: str, platform: str, otp_info: Dict, country: Dict) -> str:
    flag = country['flag']
    country_name = country['name']
    
    phone_str = str(phone)
    if len(phone_str) >= 10:
        hidden_phone = phone_str[:5] + "***" + phone_str[-3:]
    else:
        hidden_phone = phone_str
    
    code = otp_info['code']
    clean = otp_info['clean']
    
    if len(clean) == 6 and '-' not in code:
        formatted_code = f"{clean[:3]}-{clean[3:]}"
    else:
        formatted_code = code
    
    return f"""
{flag}{country_name} - #{platform} - {hidden_phone}

💌Language - #English - Your {platform} code {formatted_code}
Don't share this code with others

🔐{clean}

[ Main Channel ]    [ Number Bot ]
"""


# ============= মেইন বট ক্লাস =============
class LiveOTPBot:
    def __init__(self):
        self.bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        self.chat_id = Config.GROUP_CHAT_ID
        self.processed = set()
        self.load_processed()
    
    def load_processed(self):
        try:
            with open(Config.PROCESSED_FILE, 'r') as f:
                data = json.load(f)
                cutoff = datetime.now() - timedelta(hours=24)
                self.processed = {pid for pid, ts in data.items() if datetime.fromisoformat(ts) > cutoff}
                logger.info(f"📂 {len(self.processed)} টি OTP লোড হয়েছে")
        except:
            self.processed = set()
    
    def save_processed(self, otp_id: str):
        self.processed.add(otp_id)
        if len(self.processed) > 1000:
            self.processed = set(list(self.processed)[-500:])
        
        data = {pid: datetime.now().isoformat() for pid in self.processed}
        with open(Config.PROCESSED_FILE, 'w') as f:
            json.dump(data, f)
    
    def create_keyboard(self):
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("📢 Main Channel", url=Config.MAIN_CHANNEL_LINK),
            InlineKeyboardButton("🤖 Number Bot", url=Config.NUMBER_BOT_LINK)
        ]])
    
    async def send_start_message(self):
        msg = f"""
🚀 **live Otp Bot Start** 🚀
━━━━━━━━━━━━━━━━━━━
✅ বট সক্রিয়
📡 লাইভ মনিটরিং
🌍 {len(COUNTRY_MAP)}+ দেশ
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━
"""
        await self.bot.send_message(
            self.chat_id, 
            msg, 
            parse_mode='Markdown',
            reply_markup=self.create_keyboard()
        )
        logger.info("✅ স্টার্ট মেসেজ পাঠানো হয়েছে")
    
    async def fetch_sms(self) -> List:
        """সর্বশেষ SMS ফেচ - আপডেটেড ইউজার এজেন্ট ও কুকি সহ"""
        
        # ✅ আপডেটেড ইউজার এজেন্ট (একাধিক, রোটেট করতে পারে)
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        ]
        
        # র্যান্ডম ইউজার এজেন্ট সিলেক্ট করুন
        import random
        selected_ua = random.choice(user_agents)
        
        headers = {
            "Host": Config.PANEL_HOST,
            "Connection": "keep-alive",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": selected_ua,  # ✅ আপডেটেড ইউজার এজেন্ট
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "DNT": "1",
            "Referer": Config.PANEL_REFERER,
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-US,en;q=0.9,en-GB;q=0.8,en-AZ;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Cookie": f"PHPSESSID={Config.PANEL_COOKIE}"  # ✅ আপডেটেড কুকি
        }
        
        today = datetime.now().strftime("%Y-%m-%d")
        params = {
            "fdate1": f"{today} 00:00:00",
            "fdate2": f"{today} 23:59:59",
            "frange": "",
            "fclient": "",
            "fnum": "",
            "fcli": "",
            "fgdate": "",
            "fgmonth": "",
            "fgrange": "",
            "fgclient": "",
            "fgnumber": "",
            "fgcli": "",
            "fg": "0",
            "sesskey": Config.PANEL_SESSKEY,
            "sEcho": "1",
            "iColumns": "9",
            "sColumns": ",,,,,,,,",
            "iDisplayStart": "0",
            "iDisplayLength": str(Config.FETCH_LIMIT),
            "mDataProp_0": "0",
            "sSearch_0": "",
            "bRegex_0": "false",
            "bSearchable_0": "true",
            "bSortable_0": "true",
            "mDataProp_1": "1",
            "sSearch_1": "",
            "bRegex_1": "false",
            "bSearchable_1": "true",
            "bSortable_1": "true",
            "mDataProp_2": "2",
            "sSearch_2": "",
            "bRegex_2": "false",
            "bSearchable_2": "true",
            "bSortable_2": "true",
            "mDataProp_3": "3",
            "sSearch_3": "",
            "bRegex_3": "false",
            "bSearchable_3": "true",
            "bSortable_3": "true",
            "mDataProp_4": "4",
            "sSearch_4": "",
            "bRegex_4": "false",
            "bSearchable_4": "true",
            "bSortable_4": "true",
            "mDataProp_5": "5",
            "sSearch_5": "",
            "bRegex_5": "false",
            "bSearchable_5": "true",
            "bSortable_5": "true",
            "mDataProp_6": "6",
            "sSearch_6": "",
            "bRegex_6": "false",
            "bSearchable_6": "true",
            "bSortable_6": "true",
            "mDataProp_7": "7",
            "sSearch_7": "",
            "bRegex_7": "false",
            "bSearchable_7": "true",
            "bSortable_7": "true",
            "mDataProp_8": "8",
            "sSearch_8": "",
            "bRegex_8": "false",
            "bSearchable_8": "true",
            "bSortable_8": "false",
            "sSearch": "",
            "bRegex": "false",
            "iSortCol_0": "0",
            "sSortDir_0": "desc",
            "iSortingCols": "1",
            "_": str(int(datetime.now().timestamp() * 1000))
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    Config.PANEL_URL,
                    headers=headers,
                    params=params,
                    timeout=Config.REQUEST_TIMEOUT,
                    ssl=False
                ) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        if text:
                            data = json.loads(text)
                            return data.get('aaData', [])
                    else:
                        logger.warning(f"HTTP {resp.status}")
                    return []
        except asyncio.TimeoutError:
            logger.warning("⏱️ টাইমআউট - আবার চেষ্টা")
            return []
        except aiohttp.ClientError as e:
            logger.error(f"🌐 ক্লায়েন্ট এরর: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"📄 JSON এরর: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ ফেচ এরর: {e}")
            return []
    
    async def monitor(self):
        """মূল মনিটরিং লুপ"""
        await self.send_start_message()
        
        error_count = 0
        
        while True:
            try:
                sms_list = await self.fetch_sms()
                
                if sms_list:
                    error_count = 0
                    
                    for sms in sms_list:
                        if len(sms) >= 6:
                            timestamp = sms[0]
                            phone = sms[2]
                            raw_platform = sms[3] if len(sms) > 3 else ""
                            message = sms[5] if len(sms) > 5 else ""
                            
                            if not message:
                                continue
                            
                            otp_info = extract_otp(message)
                            
                            if otp_info:
                                otp_id = f"{timestamp}_{phone}_{otp_info['clean']}"
                                
                                if otp_id not in self.processed:
                                    self.save_processed(otp_id)
                                    
                                    country = get_country_from_phone(phone)
                                    platform = extract_platform(message, raw_platform)
                                    formatted = format_message(phone, platform, otp_info, country)
                                    
                                    try:
                                        await self.bot.send_message(
                                            self.chat_id,
                                            formatted,
                                            reply_markup=self.create_keyboard()
                                        )
                                        logger.info(f"✅ OTP: {otp_info['code']} | {country['name']} | {platform}")
                                    except TelegramError as e:
                                        logger.error(f"📨 টেলিগ্রাম এরর: {e}")
                                    
                                    await asyncio.sleep(0.5)
                
                await asyncio.sleep(Config.CHECK_INTERVAL)
                
            except asyncio.CancelledError:
                logger.info("🛑 মনিটরিং বন্ধ")
                break
            except Exception as e:
                error_count += 1
                logger.error(f"❌ মনিটরিং এরর: {e}")
                wait = min(error_count * 2, 30)
                await asyncio.sleep(wait)
    
    async def run(self):
        """বট রান"""
        print("=" * 55)
        print("🚀 OTP মনিটর বট চালু হয়েছে (আপডেটেড)")
        print(f"📢 মেইন চ্যানেল: {Config.MAIN_CHANNEL_LINK}")
        print(f"🤖 নাম্বার বট: {Config.NUMBER_BOT_LINK}")
        print(f"🔑 সেশন: {Config.PANEL_SESSKEY[:10]}...")
        print(f"🍪 কুকি: {Config.PANEL_COOKIE[:15]}...")
        print("=" * 55)
        
        await self.monitor()


async def main():
    bot = LiveOTPBot()
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 বট বন্ধ হয়েছে! আল্লাহ হাফেজ.")