import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Bot token
BOT_TOKEN = "8774571585:AAFKay-2UKHotwYLEOu2NxF0Y9YvY6I7zuk"

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class PatchParser:
    def __init__(self):
        self.patches = []
        self.hooks = []
        self.extra_offsets = []
        
    def parse_input(self, text):
        """Parse the input text and extract patches, hooks, and extra offsets"""
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
        
        # Parse extra offsets (standalone lines)
        for line in lines:
            line = line.strip()
            # Pattern 1: libname - offset hex_value
            match1 = re.match(r'(\S+)\s*-\s*0x([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)', line)
            if match1:
                lib = match1.group(1)
                offset = match1.group(2).upper()
                patch_hex = match1.group(3)
                self.extra_offsets.append(('extra', offset, patch_hex))
                continue
            
            # Pattern 2: offset HOOK OFFSET
            match2 = re.match(r'0x([0-9A-Fa-f]+)\s+HOOK OFFSET', line)
            if match2:
                offset = match2.group(1).upper()
                self.hooks.append(('unknown', offset))
                continue
            
            # Pattern 3: offset patch_hex
            match3 = re.match(r'0x([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)', line)
            if match3:
                offset = match3.group(1).upper()
                patch_hex = match3.group(2)
                self.extra_offsets.append(('extra', offset, patch_hex))
    
    def generate_patch_lib(self, lib_filter=None):
        """Generate PATCH_LIB format for patches"""
        result = []
        for lib, offset, patch_hex in self.patches:
            if lib_filter and lib != lib_filter:
                continue
            result.append(f'PATCH_LIB("{lib}","0x{offset}","{patch_hex}");')
        return result
    
    def get_hooks(self):
        """Get hook offsets"""
        return [(lib, offset) for lib, offset in self.hooks]
    
    def get_extra_offsets(self):
        """Get extra offsets"""
        return self.extra_offsets

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    await update.message.reply_text(
        "🎯 **Patch Offset Parser Bot**\n\n"
        "Input bhejo jo tumhare paas hai (PATCH LIST, HOOK LIST wala text), "
        "main automatically parse kar ke PATCH_LIB format mein convert kar dunga!\n\n"
        "Example:\n"
        "```\n"
        "--- [ PATCH LIST ] ---\n"
        "Patch Found: libanogs.so -> 0x2234B0 [h 00 00 80 D2 C0 03 5F D6]\n"
        "--- [ HOOK LIST ] ---\n"
        "Hook Found: libanogs.so -> 0x2328F0\n"
        "```",
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle input messages"""
    parser = PatchParser()
    parser.parse_input(update.message.text)
    
    # Patch LIB generation
    patches = parser.generate_patch_lib()
    hooks = parser.get_hooks()
    extra_offsets = parser.get_extra_offsets()
    
    response = "📋 **Parsed Results:**\n\n"
    
    if patches:
        response += "🔧 **PATCH LIB Code:**\n```\n"
        response += '\n'.join(patches)
        response += "\n```\n\n"
    
    if hooks:
        response += "🎣 **HOOK Offsets:**\n"
        for lib, offset in hooks:
            lib_display = lib if lib != 'unknown' else '?'
            response += f"• `{lib_display}` -> `0x{offset}`\n"
        response += "\n"
    
    if extra_offsets:
        response += "📍 **Extra Offsets:**\n"
        for _, offset, hex_val in extra_offsets:
            response += f"• `0x{offset}` -> `{hex_val}`\n"
    
    if not patches and not hooks and not extra_offsets:
        response += "❌ Koi valid data nahi mila. Dobara try karo!"
    
    # Add patch options button
    keyboard = [[InlineKeyboardButton("✏️ Patch Options (RET/NOP)", callback_data="patch_options")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(response, parse_mode='Markdown', reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "patch_options":
        keyboard = [
            [InlineKeyboardButton("RET (C0 03 5F D6)", callback_data="patch_ret")],
            [InlineKeyboardButton("RET0 (00 00 80 D2)", callback_data="patch_ret0")],
            [InlineKeyboardButton("NOP (1F 20 03 D5)", callback_data="patch_nop")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⚙️ **Patch Value Select karo:**\n\n"
            "Yahan se sare offsets ko ek specific patch value se replace kar sakte ho:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

async def patch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle patch selection"""
    query = update.callback_query
    await query.answer()
    
    parser = PatchParser()
    # Re-parse from last message (simplified - in production store context)
    parser.parse_input(context.user_data.get('last_input', ''))
    
    patch_map = {
        'patch_ret': 'C0 03 5F D6',
        'patch_ret0': '00 00 80 D2',
        'patch_nop': '1F 20 03 D5'
    }
    
    if query.data in patch_map:
        patch_hex = patch_map[query.data]
        patches = []
        
        # Apply to all patches
        for lib, offset, _ in parser.patches:
            patches.append(f'PATCH_LIB("{lib}","0x{offset}","{patch_hex.replace(" ", "")}");')
        
        # Apply to extra offsets
        for _, offset, _ in parser.extra_offsets:
            patches.append(f'PATCH_LIB("libanogs.so","0x{offset}","{patch_hex.replace(" ", "")}");')
        
        response = f"✅ **Applied Patch: `{patch_hex}`**\n\n🔧 **Generated Code:**\n```\n" + '\n'.join(patches) + "\n```"
        
        keyboard = [[InlineKeyboardButton("🔙 New Input", callback_data="new_input")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(response, parse_mode='Markdown', reply_markup=reply_markup)

async def back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to main"""
    await update.callback_query.edit_message_text("Input bhejo!")

def main():
    """Start the bot"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^(patch_options|back)$"))
    application.add_handler(CallbackQueryHandler(patch_callback, pattern="^patch_"))
    
    print("🤖 Bot started...")
    application.run_polling()

if __name__ == '__main__':
    main()