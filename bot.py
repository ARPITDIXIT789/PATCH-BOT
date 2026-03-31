import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

BOT_TOKEN = "8774571585:AAFKay-2UKHotwYLEOu2NxF0Y9YvY6I7zuk"

class SimpleParser:
    def parse(self, text):
        offsets = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Extract all 0x offsets
            matches = re.findall(r'0x([0-9A-Fa-f]{6,8})', line, re.IGNORECASE)
            for match in matches:
                offsets.append(match.upper())
        
        return offsets

def generate_patch_lib(offsets, lib="libanogs.so", hex_val="00 00 80 D2 C0 03 5F D6"):
    result = []
    for offset in offsets:
        result.append(f'PATCH_LIB("{lib}","0x{offset}","{hex_val}");')
    return result

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎯 PATCH BOT\n\n"
        "Offsets bhejo (koi bhi format):\n"
        "0x123456\n"
        "anogs.so - 0xABCDEF\n"
        "Patch Found: ... 0x5952F70"
    )

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data['input'] = text
    
    parser = SimpleParser()
    offsets = parser.parse(text)
    
    if not offsets:
        await update.message.reply_text("❌ Offset nahi mila! 0x... format use karo")
        return
    
    # Default RET0
    patches = generate_patch_lib(offsets)
    
    response = f"✅ {len(patches)} offsets found!\n\n"
    response += "```\n" + "\n".join(patches) + "\n```"
    
    keyboard = [
        [InlineKeyboardButton("RET", callback_data="ret"), InlineKeyboardButton("RET0", callback_data="ret0")],
        [InlineKeyboardButton("NOP", callback_data="nop")]
    ]
    
    await update.message.reply_text(response, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    input_text = context.user_data.get('input', '')
    parser = SimpleParser()
    offsets = parser.parse(input_text)
    
    hex_map = {
        'ret': 'C0 03 5F D6',
        'ret0': '00 00 80 D2 C0 03 5F D6',
        'nop': '1F 20 03 D5'
    }
    
    hex_val = hex_map.get(query.data, '00 00 80 D2 C0 03 5F D6')
    patches = generate_patch_lib(offsets, "libanogs.so", hex_val)
    
    response = f"🔧 {query.data.upper()}\n\n"
    response += "```\n" + "\n".join(patches) + "\n```"
    
    await query.edit_message_text(response, parse_mode='Markdown')

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    app.add_handler(CallbackQueryHandler(button_click))
    
    print("✅ SIMPLE BOT STARTED - 100% WORKING!")
    app.run_polling()

if __name__ == '__main__':
    main()
