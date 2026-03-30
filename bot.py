import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

BOT_TOKEN = "8774571585:AAFKay-2UKHotwYLEOu2NxF0Y9YvY6I7zuk"  # Full token dalo

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class PatchParser:
    def __init__(self):
        self.patches = []
        self.hooks = []
        self.extra_offsets = []
        
    def parse_input(self, text):
        self.patches.clear()
        self.hooks.clear()
        self.extra_offsets.clear()
        
        lines = text.strip().split('\n')
        
        # Parse PATCH LIST
        in_patch_section = False
        for line in lines:
            line = line.strip()
            if '--- [ PATCH LIST ] ---' in line:
                in_patch_section = True
                continue
            if in_patch_section and line.startswith('Patch Found:'):
                match = re.match(r'Patch Found:\s+(\S+)\s+->\s+0x([0-9A-Fa-f]+)\s+\[h\s+([0-9A-Fa-f\s]+)\]', line)
                if match:
                    lib = match.group(1)
                    offset = match.group(2).upper()
                    patch_hex = match.group(3).strip().replace(' ', '')
                    self.patches.append((lib, offset, patch_hex))
        
        # Parse HOOK LIST
        in_hook_section = False
        for line in lines:
            line = line.strip()
            if '--- [ HOOK LIST ] ---' in line:
                in_hook_section = True
                continue
            if in_hook_section and line.startswith('Hook Found:'):
                match = re.match(r'Hook Found:\s+(\S+)\s+->\s+0x([0-9A-Fa-f]+)', line)
                if match:
                    lib = match.group(1)
                    offset = match.group(2).upper()
                    self.hooks.append((lib, offset))
        
        # Parse extra offsets
        for line in lines:
            line = line.strip()
            match1 = re.match(r'(\S+)\s*-\s*0x([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)', line)
            if match1:
                lib = match1.group(1)
                offset = match1.group(2).upper()
                patch_hex = match1.group(3)
                self.extra_offsets.append((lib, offset, patch_hex))
                continue
            
            match2 = re.match(r'0x([0-9A-Fa-f]+)\s+HOOK OFFSET', line)
            if match2:
                offset = match2.group(1).upper()
                self.hooks.append(('unknown', offset))
                continue
            
            match3 = re.match(r'0x([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)', line)
            if match3:
                offset = match3.group(1).upper()
                patch_hex = match3.group(3)
                self.extra_offsets.append(('extra', offset, patch_hex))
    
    def generate_patch_lib(self, lib_filter=None):
        result = []
        for lib, offset, patch_hex in self.patches:
            if lib_filter and lib != lib_filter:
                continue
            result.append(f'PATCH_LIB("{lib}","0x{offset}","{patch_hex}");')
        return result
    
    def get_hooks(self):
        return [(lib, offset) for lib, offset in self.hooks]
    
    def get_extra_offsets(self):
        return self.extra_offsets

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
🎯 Patch Offset Parser Bot

Input bhejo (PATCH LIST, HOOK LIST wala text), 
main PATCH_LIB format mein convert kar dunga!

Example:
--- [ PATCH LIST ] ---
Patch Found: libanogs.so -> 0x2234B0 [h 00 00 80 D2 C0 03 5F D6]
--- [ HOOK LIST ] ---
Hook Found: libanogs.so -> 0x2328F0
    """
    await update.message.reply_text(welcome_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parser = PatchParser()
    parser.parse_input(update.message.text)
    
    patches = parser.generate_patch_lib()
    hooks = parser.get_hooks()
    extra_offsets = parser.get_extra_offsets()
    
    response = "📋 Parsed Results:\n\n"
    
    if patches:
        response += "🔧 PATCH LIB Code:\n"
        for patch in patches:
            response += f"```{patch}```\n"
    
    if hooks:
        response += "\n🎣 HOOK Offsets:\n"
        for lib, offset in hooks:
            lib_display = lib if lib != 'unknown' else '?'
            response += f"• {lib_display} -> 0x{offset}\n"
    
    if extra_offsets:
        response += "\n📍 Extra Offsets:\n"
        for lib, offset, hex_val in extra_offsets:
            response += f"• 0x{offset} -> {hex_val}\n"
    
    if not patches and not hooks and not extra_offsets:
        response += "❌ Koi valid data nahi mila!"
    
    keyboard = [[InlineKeyboardButton("✏️ Patch Options", callback_data="patch_options")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(response, reply_markup=reply_markup, parse_mode=None)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "patch_options":
        keyboard = [
            [InlineKeyboardButton("RET", callback_data="patch_ret")],
            [InlineKeyboardButton("RET0", callback_data="patch_ret0")],
            [InlineKeyboardButton("NOP", callback_data="patch_nop")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⚙️ Patch Value select karo:\n"
            "RET: C0 03 5F D6\n"
            "RET0: 00 00 80 D2\n"
            "NOP: 1F 20 03 D5",
            reply_markup=reply_markup
        )

async def patch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Simple response for now
    patch_map = {
        'patch_ret': 'C0 03 5F D6',
        'patch_ret0': '00 00 80 D2', 
        'patch_nop': '1F 20 03 D5'
    }
    
    if query.data in patch_map:
        patch_hex = patch_map[query.data]
        await query.edit_message_text(
            f"✅ Applied: `{patch_hex}`\n\n"
            f"Paste apna input dobara for conversion!"
        )

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^patch_options$"))
    application.add_handler(CallbackQueryHandler(patch_callback, pattern="^patch_"))
    
    print("🤖 Bot started...")
    application.run_polling()

if __name__ == '__main__':
    main()
