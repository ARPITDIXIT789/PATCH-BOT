import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

BOT_TOKEN = "8774571585:AAFKay-2UKHotwYLEOu2NxF0Y9YvY6I7zuk"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class PatchParser:
    def __init__(self):
        self.patches = []  # (lib, offset, patch_hex)
        self.hooks = []    # (lib, offset)
        self.extra_offsets = []  # (lib, offset, patch_hex) - no patch hex wale
        
    def parse_input(self, text):
        self.patches.clear()
        self.hooks.clear()
        self.extra_offsets.clear()
        
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 1. PATCH LIST format
            # Patch Found: libUE4.so -> 0x5952F70 [h 00 00 80 D2 C0 03 5F D6]
            patch_match = re.match(r'Patch Found:\s+(\S+)\s+->\s+0x([0-9A-Fa-f]+)\s+\[h\s+([0-9A-Fa-f\s]+)\]', line)
            if patch_match:
                lib = patch_match.group(1)
                offset = patch_match.group(2).upper()
                patch_hex = patch_match.group(3).strip().replace(' ', '')
                self.patches.append((lib, offset, patch_hex))
                continue
            
            # 2. HOOK OFFSET format
            # anogs.so - 0x228168 HOOK OFFSET
            hook_match = re.match(r'(\S+)\s*-\s*0x([0-9A-Fa-f]+)\s+HOOK OFFSET', line, re.IGNORECASE)
            if hook_match:
                lib = hook_match.group(1)
                offset = hook_match.group(2).upper()
                self.hooks.append((lib, offset))
                continue
            
            # 3. Standard HOOK LIST
            # Hook Found: libanogs.so -> 0x2328F0
            hook_list_match = re.match(r'Hook Found:\s+(\S+)\s+->\s+0x([0-9A-Fa-f]+)', line)
            if hook_list_match:
                lib = hook_list_match.group(1)
                offset = hook_list_match.group(2).upper()
                self.hooks.append((lib, offset))
                continue
            
            # 4. lib - offset patch_hex
            # anogs.so - 0x228164 C0 03 5F D6
            lib_patch_match = re.match(r'(\S+)\s*-\s*0x([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+(?:\s+[0-9A-Fa-f]+)*)', line)
            if lib_patch_match:
                lib = lib_patch_match.group(1)
                offset = lib_patch_match.group(2).upper()
                patch_hex = lib_patch_match.group(3).strip().replace(' ', '')
                self.patches.append((lib, offset, patch_hex))
                continue
            
            # 5. Standalone offset HOOK OFFSET
            # 0x212490 HOOK OFFSET
            standalone_hook = re.match(r'0x([0-9A-Fa-f]+)\s+HOOK OFFSET', line, re.IGNORECASE)
            if standalone_hook:
                offset = standalone_hook.group(1).upper()
                self.hooks.append(('unknown', offset))
                continue
            
            # 6. offset patch_hex (no lib)
            # 0x3D6B10 00 00 80 D2 C0 03 5F D6
            standalone_patch = re.match(r'0x([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+(?:\s+[0-9A-Fa-f]+)*)', line)
            if standalone_patch:
                offset = standalone_patch.group(1).upper()
                patch_hex = standalone_patch.group(2).strip().replace(' ', '')
                self.patches.append(('libanogs.so', offset, patch_hex))  # Default lib
                continue
    
    def generate_patch_lib(self):
        result = []
        all_patches = self.patches + [(lib, offset, hex_val) for lib, offset, hex_val in self.extra_offsets]
        
        for lib, offset, patch_hex in all_patches:
            result.append(f'PATCH_LIB("{lib}","0x{offset}","{patch_hex}");')
        return result
    
    def get_hooks_list(self):
        return self.hooks
    
    def get_stats(self):
        return len(self.patches), len(self.hooks)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
🎯 Patch Offset Parser Bot

Supported formats:
• Patch Found: libUE4.so -> 0x5952F70 [h 00 00 80 D2 C0 03 5F D6]
• anogs.so - 0x228168 HOOK OFFSET
• Hook Found: libanogs.so -> 0x2328F0
• anogs.so - 0x228164 C0 03 5F D6
• 0x212490 HOOK OFFSET

Input bhejo, main sab detect kar lunga!
    """
    await update.message.reply_text(welcome_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parser = PatchParser()
    parser.parse_input(update.message.text)
    
    patches = parser.generate_patch_lib()
    hooks = parser.get_hooks_list()
    patch_count, hook_count = parser.get_stats()
    
    response = f"📊 Found: {patch_count} patches, {hook_count} hooks\n\n"
    
    # PATCH LIB Code
    if patches:
        response += "🔧 PATCH LIB Code:\n```\n"
        for patch in patches:
            response += patch + "\n"
        response += "```\n\n"
    
    # HOOK List
    if hooks:
        response += "🎣 HOOK Offsets:\n"
        for lib, offset in hooks:
            lib_display = lib if lib != 'unknown' else '?'
            response += f"• `{lib_display}` -> `0x{offset}`\n"
        response += "\n"
    
    if not patches and not hooks:
        response += "❌ Koi valid data nahi mila!"
    
    # Buttons
    keyboard = [[InlineKeyboardButton("✏️ Apply RET/NOP", callback_data="patch_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(response, parse_mode='Markdown', reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "patch_menu":
        keyboard = [
            [InlineKeyboardButton("RET (C0 03 5F D6)", callback_data="ret")],
            [InlineKeyboardButton("RET0 (00 00 80 D2)", callback_data="ret0")],
            [InlineKeyboardButton("NOP (1F 20 03 D5)", callback_data="nop")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⚙️ Patch value select karo:\n\n"
            "Yahan click karke sare offsets ko RET/NOP se replace kar sakte ho:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def patch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    patch_map = {
        'ret': 'C0 03 5F D6',
        'ret0': '00 00 80 D2',
        'nop': '1F 20 03 D5'
    }
    
    if query.data in patch_map:
        patch_hex = patch_map[query.data]
        # Store original message for re-parsing
        context.user_data['last_input'] = query.message.reply_to_message.text if query.message.reply_to_message else ""
        context.user_data['patch_hex'] = patch_hex.replace(' ', '')
        
        response = f"✅ Applied `{patch_hex}` to all offsets!\n\n"
        response += "🔧 Generated PATCH LIB:\n\n"
        
        parser = PatchParser()
        parser.parse_input(context.user_data['last_input'])
        patches = parser.generate_patch_lib()
        
        # Override all patch hex values
        final_patches = []
        for lib, offset, _ in parser.patches + [(lib, offset, '') for lib, offset in parser.get_hooks_list()]:
            final_patches.append(f'PATCH_LIB("{lib}","0x{offset}","{context.user_data["patch_hex"]}");')
        
        response += "```\n" + "\n".join(final_patches) + "\n```"
        
        await query.edit_message_text(response, parse_mode='Markdown')

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^patch_menu$"))
    application.add_handler(CallbackQueryHandler(patch_callback, pattern="^(ret|ret0|nop)$"))
    
    print("🤖 Advanced Patch Parser Bot started!")
    application.run_polling()

if __name__ == '__main__':
    main()
