import os
import json
import random
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

# Loggingni sozlash
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "8915839857:AAFctENKZly0ZVrqa3iWvVQnwMCVh1KMFUA")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8149451732"))  # O'zingizning Telegram ID'ngizni yozing

if not TOKEN:
    raise ValueError("BOT_TOKEN muhit o'zgaruvchisi o'rnatilmagan!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Bot xotirasi
games = {}
poll_to_chat = {}
admin_context = {} # Admin uchun holat (qaysi blokni tahrirlayotgani)

# JSON fayldan barcha savollarni yuklash
def load_questions():
    default_structure = {"blocks": {"default": {"name": "Asosiy Blok", "questions": []}}, "allowed_users": []}
    try:
        if os.path.exists("questions.json"):
            with open("questions.json", "r", encoding="utf-8") as file:
                data = json.load(file)
                if isinstance(data, list): # Eski format bo'lsa migratsiya qilish
                    data = {"blocks": {"default": {"name": "Asosiy Blok", "questions": data}}}
                if "allowed_users" not in data:
                    data["allowed_users"] = []
                return data
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Yuklashda xato: {e}")
    return default_structure

def save_questions(qs):
    try:
        with open("questions.json", "w", encoding="utf-8") as file:
            json.dump(qs, file, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Saqlashda xato: {e}")
        
DATA = load_questions()

def is_allowed(user_id):
    return user_id == ADMIN_ID or user_id in DATA.get("allowed_users", [])

def get_blocks_keyboard(chat_id):
    builder = InlineKeyboardBuilder()
    blocks = DATA.get("blocks", {})
    for b_id, b_data in blocks.items():
        q_count = len(b_data["questions"])
        builder.button(text=f"📦 {b_data['name']} ({q_count})", callback_data=f"quiz_block:{b_id}:{chat_id}")
    builder.adjust(2)
    return builder.as_markup()

def get_admin_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🆕 Yangi blok yaratish", callback_data="admin_new_block")
    builder.button(text="📂 Bloklarni boshqarish", callback_data="admin_list_blocks")
    builder.button(text="👤 Foydalanuvchilarni boshqarish", callback_data="admin_manage_users")
    builder.adjust(1)
    return builder.as_markup()

def get_admin_users_keyboard():
    builder = InlineKeyboardBuilder()
    allowed = DATA.get("allowed_users", [])
    for u_id in allowed:
        builder.button(text=f"👤 {u_id} ❌", callback_data=f"adm_rem_user:{u_id}")
    builder.button(text="➕ Yangi foydalanuvchi qo'shish", callback_data="adm_add_user_prompt")
    builder.button(text="⬅️ Orqaga", callback_data="admin_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_admin_block_manage_keyboard(block_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Nomini o'zgartirish", callback_data=f"adm_ren:{block_id}")
    builder.button(text="➕ Savol qo'shish (Forward)", callback_data=f"adm_add:{block_id}")
    builder.button(text="🗑 Oxirgi savolni o'chirish", callback_data=f"adm_del_last:{block_id}")
    builder.button(text="❌ Blokni butunlay o'chirish", callback_data=f"adm_rem_block:{block_id}")
    builder.button(text="⬅️ Orqaga", callback_data="admin_list_blocks")
    builder.adjust(1)
    return builder.as_markup()

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Salom! Men Blokli va Aqlli Viktorina botman.\n\n"
        "• Testni boshlash: /quiz\n"
        "• Testni to'xtatish: /stop"
    )

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("🛠 **Admin Panelga xush kelibsiz.**\nBloklarni va savollarni boshqarish uchun quyidagilardan birini tanlang:", 
                         reply_markup=get_admin_main_keyboard())

@dp.callback_query(F.data == "admin_list_blocks", F.from_user.id == ADMIN_ID)
async def admin_list_blocks(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    for b_id, b_data in DATA["blocks"].items():
        builder.button(text=f"📂 {b_data['name']}", callback_data=f"adm_manage:{b_id}")
    builder.button(text="⬅️ Menyu", callback_data="admin_menu")
    builder.adjust(1)
    await callback.message.edit_text("Boshqarish uchun blokni tanlang:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "admin_menu", F.from_user.id == ADMIN_ID)
async def admin_menu_cb(callback: types.CallbackQuery):
    await callback.message.edit_text("🛠 Admin Panel:", reply_markup=get_admin_main_keyboard())

@dp.callback_query(F.data == "admin_manage_users", F.from_user.id == ADMIN_ID)
async def admin_manage_users(callback: types.CallbackQuery):
    await callback.message.edit_text("👥 **Ruxsat berilgan foydalanuvchilar:**\nID raqamini bosib o'chirishingiz mumkin.", 
                                     reply_markup=get_admin_users_keyboard())

@dp.callback_query(F.data == "adm_add_user_prompt", F.from_user.id == ADMIN_ID)
async def admin_add_user_prompt(callback: types.CallbackQuery):
    admin_context[callback.from_user.id] = {"action": "adding_user"}
    await callback.message.answer("🆔 Ruxsat bermoqchi bo'lgan foydalanuvchining Telegram ID raqamini yuboring:")
    await callback.answer()

@dp.callback_query(F.data.startswith("adm_rem_user:"), F.from_user.id == ADMIN_ID)
async def admin_rem_user(callback: types.CallbackQuery):
    u_id = int(callback.data.split(":")[1])
    if u_id in DATA.get("allowed_users", []):
        DATA["allowed_users"].remove(u_id)
        save_questions(DATA)
        await callback.answer(f"✅ ID {u_id} o'chirildi")
        await admin_manage_users(callback)

@dp.callback_query(F.data == "admin_new_block", F.from_user.id == ADMIN_ID)
async def admin_create_block_start(callback: types.CallbackQuery):
    admin_context[callback.from_user.id] = {"action": "naming_new_block"}
    await callback.message.answer("📝 Yangi blok uchun nom yuboring:")
    await callback.answer()

@dp.message(F.text, F.from_user.id == ADMIN_ID)
async def admin_text_handler(message: types.Message):
    ctx = admin_context.get(message.from_user.id)
    if not ctx: return

    if ctx["action"] == "naming_new_block":
        b_id = f"block_{int(asyncio.get_event_loop().time())}"
        DATA["blocks"][b_id] = {"name": message.text, "questions": []}
        save_questions(DATA)
        admin_context.pop(message.from_user.id)
        await message.answer(f"✅ '{message.text}' bloki yaratildi!", reply_markup=get_admin_block_manage_keyboard(b_id))
    
    elif ctx["action"] == "renaming_block":
        b_id = ctx["block_id"]
        old_name = DATA["blocks"][b_id]["name"]
        DATA["blocks"][b_id]["name"] = message.text
        save_questions(DATA)
        admin_context.pop(message.from_user.id)
        await message.answer(f"✅ Blok nomi '{old_name}' -> '{message.text}' ga o'zgardi.", reply_markup=get_admin_block_manage_keyboard(b_id))

    elif ctx["action"] == "adding_user":
        try:
            new_id = int(message.text)
            if new_id not in DATA["allowed_users"]:
                DATA["allowed_users"].append(new_id)
                save_questions(DATA)
                await message.answer(f"✅ ID {new_id} ruxsat etilganlar ro'yxatiga qo'shildi.")
            else:
                await message.answer("ℹ️ Bu ID allaqachon ro'yxatda bor.")
            admin_context.pop(message.from_user.id)
            await admin_panel(message)
        except ValueError:
            await message.answer("❌ Xato! Faqat raqamlardan iborat ID yuboring.")

@dp.callback_query(F.data.startswith("adm_manage:"), F.from_user.id == ADMIN_ID)
async def admin_manage_block(callback: types.CallbackQuery):
    b_id = callback.data.split(":")[1]
    b_data = DATA["blocks"].get(b_id)
    if not b_data: return await callback.answer("Blok topilmadi")
    await callback.message.edit_text(f"📦 Blok: **{b_data['name']}**\nJami savollar: {len(b_data['questions'])}", 
                                     reply_markup=get_admin_block_manage_keyboard(b_id))

@dp.callback_query(F.data.startswith("adm_add:"), F.from_user.id == ADMIN_ID)
async def admin_add_mode(callback: types.CallbackQuery):
    b_id = callback.data.split(":")[1]
    admin_context[callback.from_user.id] = {"action": "importing", "block_id": b_id}
    await callback.message.answer(f"📥 '{DATA['blocks'][b_id]['name']}' bloki uchun savollarni forward qiling.\nTugatgach /done buyrug'ini bering.")
    await callback.answer()

@dp.message(Command("done"), F.from_user.id == ADMIN_ID)
async def admin_done_import(message: types.Message):
    if message.from_user.id in admin_context:
        admin_context.pop(message.from_user.id)
        save_questions(DATA)
        await message.answer("✅ Savollar saqlandi.")

@dp.callback_query(F.data.startswith("adm_del_last:"), F.from_user.id == ADMIN_ID)
async def admin_del_last_q(callback: types.CallbackQuery):
    b_id = callback.data.split(":")[1]
    if DATA["blocks"][b_id]["questions"]:
        DATA["blocks"][b_id]["questions"].pop()
        save_questions(DATA)
        await callback.answer("🗑 Oxirgi savol o'chirildi")
        await admin_manage_block(callback)
    else:
        await callback.answer("Savollar yo'q", show_alert=True)

@dp.callback_query(F.data.startswith("adm_rem_block:"), F.from_user.id == ADMIN_ID)
async def admin_remove_block(callback: types.CallbackQuery):
    b_id = callback.data.split(":")[1]
    if b_id == "default": return await callback.answer("Asosiy blokni o'chirib bo'lmaydi", show_alert=True)
    DATA["blocks"].pop(b_id, None)
    save_questions(DATA)
    await callback.answer("❌ Blok o'chirildi")
    await admin_list_blocks(callback)

@dp.callback_query(F.data.startswith("adm_ren:"), F.from_user.id == ADMIN_ID)
async def admin_rename_start(callback: types.CallbackQuery):
    b_id = callback.data.split(":")[1]
    admin_context[callback.from_user.id] = {"action": "renaming_block", "block_id": b_id}
    await callback.message.answer("📝 Blok uchun yangi nom yuboring:")
    await callback.answer()

@dp.message(F.poll, F.from_user.id == ADMIN_ID)
async def handle_poll_import(message: types.Message):
    ctx = admin_context.get(message.from_user.id)
    if ctx and ctx["action"] == "importing":
        b_id = ctx["block_id"]
        poll = message.poll
        options = [o.text for o in poll.options]
        correct_option = options[poll.correct_option_id] if poll.correct_option_id is not None else ""
        
        DATA["blocks"][b_id]["questions"].append({
            "question": poll.question,
            "options": options,
            "correct": correct_option
        })
        await message.reply(f"📥 Qabul qilindi! Jami: {len(DATA['blocks'][b_id]['questions'])} ta")

@dp.message(F.document, F.from_user.id == ADMIN_ID)
async def handle_file_upload(message: types.Message):
    ctx = admin_context.get(message.from_user.id)
    if ctx and ctx["action"] == "importing" and message.document.file_name.endswith(".txt"):
        b_id = ctx["block_id"]
        file = await bot.get_file(message.document.file_id)
        content = await bot.download_file(file.file_path)
        lines = content.read().decode('utf-8').splitlines()
        for line in lines:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                DATA["blocks"][b_id]["questions"].append({
                    "question": parts[0],
                    "options": parts[1:-1],
                    "correct": parts[-1]
                })
        save_questions(DATA)
        await message.answer(f"✅ Fayldan savollar qo'shildi. Jami: {len(DATA['blocks'][b_id]['questions'])} ta")

@dp.message(Command("quiz"))
async def choose_block_msg(message: types.Message):
    if not is_allowed(message.from_user.id):
        return await message.answer("⛔️ Kechirasiz, sizga ushbu botdan foydalanishga ruxsat berilmagan.")
    chat_id = message.chat.id
    if chat_id in games:
        return await message.answer("⚠️ Bu chatda hozirda faol viktorina ketmoqda. Uni to'xtatish uchun /stop buyrug'ini bering.")
    await message.answer("📚 Viktorina blokini tanlang:", reply_markup=get_blocks_keyboard(chat_id))

@dp.callback_query(F.data.startswith("quiz_block:"))
async def set_block_and_show_timer(callback: types.CallbackQuery):
    _, b_id, chat_id = callback.data.split(":")
    chat_id = int(chat_id)
    
    if chat_id in games:
        return await callback.answer("Bu chatda o'yin boshlanib ketgan!", show_alert=True)
        
    block_questions = DATA["blocks"].get(b_id, {}).get("questions", [])
    if not block_questions:
        return await callback.answer("Bu blokda savollar mavjud emas!", show_alert=True)
        
    # [O'ZGARTIRISH] Faqat shu blok ichidagi savollarni chuqur nusxa olib aralashtiramiz
    shuffled_questions = random.sample(block_questions, len(block_questions))
    is_group = callback.message.chat.type in ["group", "supergroup"]
    
    games[chat_id] = {
        "questions": shuffled_questions,
        "current_index": 0,
        "time_limit": 30,
        "results": {},
        "is_group": is_group,
        "current_poll_id": None,
        "current_msg_id": None,
        "task": None,
        "block_name": DATA["blocks"][b_id]["name"],
        "unanswered_counter": 0,
        "current_poll_answered": False,
        "current_correct_idx": 0  # To'g'ri indeksni saqlash uchun
    }
    
    builder = InlineKeyboardBuilder()
    builder.button(text="15 Sekund", callback_data=f"time:15:{chat_id}")
    builder.button(text="30 Sekund", callback_data=f"time:30:{chat_id}")
    builder.button(text="1 Daqiqa", callback_data=f"time:60:{chat_id}")
    builder.adjust(3)
    
    await callback.message.edit_text(
        f"✅ **{DATA['blocks'][b_id]['name']}** tanlandi ({len(block_questions)} ta savol).\n"
        f"⏱ Taymer vaqtini tanlang:", 
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("time:"))
async def set_time_and_start(callback: types.CallbackQuery):
    _, seconds, chat_id = callback.data.split(":")
    chat_id = int(chat_id)
    seconds = int(seconds)
    
    if chat_id not in games:
        return await callback.answer("Sessiya eskirgan. Qaytadan /quiz bering.", show_alert=True)
        
    games[chat_id]["time_limit"] = seconds
    await callback.message.delete()
    await send_next_question(chat_id)

async def send_next_question(chat_id):
    if chat_id not in games:
        return
        
    game = games[chat_id]
    idx = game["current_index"]
    questions = game["questions"]
    
    if idx >= len(questions):
        await finish_quiz(chat_id)
        return
        
    q = questions[idx]
    game["current_poll_answered"] = False
    
    # [YANGILIK] Variantlarni aralashtirish qismi
    raw_options = list(q["options"])  # Asl variantlar ro'yxatidan nusxa olamiz
    correct_text = str(q.get("correct", "")).strip().lower()
    
    # Variantlarni tasodifiy tartibda aralashtiramiz
    random.shuffle(raw_options)
    
    # Aralashgan variantlar ichidan to'g'ri javobning yangi indeksini topamiz
    correct_index = 0
    for i, opt in enumerate(raw_options):
        if str(opt).strip().lower() == correct_text:
            correct_index = i
            break
            
    # Telegram cheklovlariga moslab matn uzunligini qisqartirish
    cleaned_options = []
    for opt in raw_options:
        opt_str = str(opt).strip()
        if len(opt_str) > 100:
            cleaned_options.append(opt_str[:97] + "...")
        else:
            cleaned_options.append(opt_str)

    # To'g'ri indeksni geym xotirasiga saqlab qo'yamiz (poll_answer kelganda tekshirish uchun)
    game["current_correct_idx"] = correct_index

    try:
        poll_msg = await bot.send_poll(
            chat_id=chat_id,
            question=f"🎲 {game['block_name']} | {idx+1}/{len(questions)}:\n{q['question']}"[:300],
            options=cleaned_options,
            type="quiz",
            correct_option_id=correct_index,
            is_anonymous=False,
            explanation="To'g'ri javob belgilandi!"
        )
        
        game["current_poll_id"] = poll_msg.poll.id
        game["current_msg_id"] = poll_msg.message_id
        poll_to_chat[poll_msg.poll.id] = chat_id
        
        if game["task"] and not game["task"].done():
            game["task"].cancel()
            
        game["task"] = asyncio.create_task(wait_for_timer(chat_id, idx, game["time_limit"]))
    except Exception as e:
        logger.error(f"Poll yuborishda xatolik (Savol {idx+1}): {e}")
        game["current_index"] += 1
        await send_next_question(chat_id)

async def wait_for_timer(chat_id, question_idx, duration):
    await asyncio.sleep(duration)
    if chat_id in games:
        game = games[chat_id]
        
        if game["current_index"] != question_idx:
            return

        try:
            await bot.stop_poll(chat_id, game["current_msg_id"])
        except:
            pass
        
        if not game["current_poll_answered"]:
            game["unanswered_counter"] += 1
        else:
            game["unanswered_counter"] = 0

        if game["unanswered_counter"] >= 3:
            await bot.send_message(chat_id, "💤 Ketma-ket 3 ta savolga hech kim javob bermadi. Viktorina faollik yo'qligi sababli to'xtatildi.")
            await finish_quiz(chat_id, auto_paused=True)
            return
        
        await asyncio.sleep(1.5)
        game["current_index"] += 1
        await send_next_question(chat_id)

@dp.poll_answer()
async def handle_poll_answer(poll_answer: types.PollAnswer):
    poll_id = poll_answer.poll_id
    if poll_id not in poll_to_chat:
        return
        
    chat_id = poll_to_chat[poll_id]
    if chat_id not in games:
        return
        
    if not is_allowed(poll_answer.user.id):
        return

    game = games[chat_id]
    game["current_poll_answered"] = True
    
    user_id = poll_answer.user.id
    user_name = poll_answer.user.full_name
    
    if user_id not in game["results"]:
        game["results"][user_id] = {"name": user_name, "correct": 0, "total": 0}
        
    game["results"][user_id]["total"] += 1
    
    idx = game["current_index"]
    if idx >= len(game["questions"]):
        return
        
    # [O'ZGARTIRISH] Bu yerda tekshirishni dinamik aniqlangan `current_correct_idx` orqali qilamiz
    if poll_answer.option_ids and poll_answer.option_ids[0] == game["current_correct_idx"]:
        game["results"][user_id]["correct"] += 1

    if not game["is_group"]:
        if game["task"]:
            game["task"].cancel()
        try:
            await bot.stop_poll(chat_id, game["current_msg_id"])
        except:
            pass
            
        game["current_index"] += 1
        await asyncio.sleep(1)
        await send_next_question(chat_id)

async def finish_quiz(chat_id, auto_paused=False):
    if chat_id not in games:
        return
        
    game = games[chat_id]
    results = game["results"]
    
    if game["task"]:
        game["task"].cancel()
        
    try:
        await bot.stop_poll(chat_id, game["current_msg_id"])
    except:
        pass
        
    status_text = "pauza holatidagi" if auto_paused else "yakuniy"
    report = f"🏁 **{game['block_name']} bo'yicha {status_text} natijalar:**\n\n"
    
    if not results:
        report += "Hech kim qatnashmadi yoki savollarga to'g'ri javob berilmadi."
    else:
        sorted_results = sorted(results.items(), key=lambda x: x[1]["correct"], reverse=True)
        for i, (u_id, data) in enumerate(sorted_results, 1):
            report += f"{i}. 👤 {data['name']} ➔ **{data['correct']} ta** to'g'ri ({data['total']} tadan)\n"
            
    await bot.send_message(chat_id, report, parse_mode="Markdown")
    
    # Ushbu chatga tegishli barcha poll_id larni tozalash
    to_remove = [k for k, v in poll_to_chat.items() if v == chat_id]
    for k in to_remove:
        poll_to_chat.pop(k, None)
        
    del games[chat_id]

# --- RENDER UCHUN VEB-SERVER QISMI ---
async def web_handle(request):
    return web.Response(text="Quiz Bot is active and awake!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', web_handle)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Veb server {port}-portda muvaffaqiyatli ishga tushdi.")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
