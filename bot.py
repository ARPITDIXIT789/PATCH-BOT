import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

BOT_TOKEN = "8774571585:AAFKay-2UKHotwYLEOu2NxF0Y9YvY6I7zuk"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class AdvancedPatchParser:
    def __init__(self):
        self.all_patches = []  # (lib, offset, original_hex, type)
        self.hooks = []
        self.raw_input = ""
    
    def parse_all_formats(self, text):
        """Parse ALL possible formats with highest accuracy"""
        self.all_patches.clear()
        self.hooks.clear()
        self.raw_input = text
        
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        for line in lines:
            self._parse_line(line)
        
        # Merge patches and hooks for final output
        return self._get_final_results()
    
    def _parse_line(self, line):
        """Parse single line with multiple regex patterns"""
        
        patterns = [
            # 1. Patch Found: libUE4.so -> 0x5952F70 [h 00 00 80 D2 C0 03 5F D6]
            (r'Patch Found:\s+(\S+)\s+->\s+0x([0-9A-Fa-f]+)\s+\[h\s+(.+?)\]', 'patch'),
            
            # 2. anogs.so - 0x228168 HOOK OFFSET
            (r'^(\S+)\s*-\s*0x([0-9A-Fa-f]+)\s+HOOK OFFSET$', 'hook'),
            
            # 3. Hook Found: libanogs.so -> 0x2328F0
            (r'Hook Found:\s+(\S+)\s+->\s+0x([0-9A-Fa-f]+)', 'hook'),
            
            # 4. anogs.so - 0x228164 C0 03 5F D6
            (r'^(\S+)\s*-\s*0x([0-9A-Fa-f]+)\s+([0-9A-Fa-f\s]+)$', 'patch'),
            
            # 5. 0x212490 HOOK OFFSET
            (r'^0x([0-9A-Fa-f]+)\s+HOOK OFFSET$', 'hook'),
            
            # 6. 0x3D6B10 00 00 80 D2 C0 03 5F D6
            (r'^0x([0-9A-Fa-f]+)\s+([0-9A-Fa-f\s]+)$', 'patch'),
            
            # 7. Single offset: 0x338680
            (r'^(0x[0-9A-Fa-f]+)$', 'offset'),
        ]
        
        for pattern, ptype in patterns:
            match = re.match(pattern, line, re.IGNORECASE | re.MULTILINE)
            if match:
                if ptype == 'patch':
                    lib = match.group(1)
                    offset = match.group(2).upper()
                    hex_val = match.group(3).strip()
                    self.all_patches.append((lib, offset, hex_val, 'patch'))
                elif ptype == 'hook':
                    lib = match.group(1)
                    offset = match.group(2).upper()
                    self.hooks.append((lib if lib != '0x' else 'unknown', offset))
                elif ptype == 'offset':
                    offset = match.group(1).upper()
                    self.all_patches.append(('unknown', offset, '', 'manual'))
                return
        
        # Fallback: extract any 0x offset
        offset_match = re.search(r'0x([0-9A-Fa-f]+)', line)
        if offset_match:
            offset = offset_match.group(1).upper()
            lib_match = re.search(r'(\S+)\s*[-→]\s*0x', line)
            lib = lib_match.group(1) if lib_match else 'unknown'
            self.all_patches.append((lib, offset, '', 'fallback'))
    
    def _get_final_results(self):
        """Get stats and ready-to-copy output"""
        total_patches = len(self.all_patches)
        total_hooks = len(self.hooks)
        return total_patches, total_hooks
    
    def generate_patch_lib(self, lib_name="libanogs.so", patch_hex="00 00 80 D2 C0 03 5F D6"):
        """Generate perfect copy-paste ready PATCH_LIB code"""
        result = []
        
        # All offsets (patches + hooks)
        all_offsets = [(lib, offset) for lib, offset, _, _ in self.all_patches] + self.hooks
        
        for lib, offset in all_offsets:
            final_lib = lib if lib != 'unknown' else lib_name
            # Perfect format with spaces in hex
            result.append(f'PATCH_LIB("{final_lib}","0x{offset}","{patch_hex}");')
        
        return result, len(result)
    
    def get_debug_info(self):
        """Debug info for complex inputs"""
        info = f"📊 Parsed:\n"
        info += f"• Patches: {len(self.all_patches)}\n"
        info += f"• Hooks: {len(self.hooks)}\n"
        return info

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """
🤖 **Advanced Patch Parser v2.0**

**Supported Formats:**
**Just paste anything** - main detect kar lunga! 🚀
"""
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main input handler - fully robust"""
    text = update.message.text.strip()
    context.user_data['last_input'] = text  # Store for re-processing
    
    parser = AdvancedPatchParser()
    total_patches, total_hooks = parser.parse_all_formats(text)
    
    if total_patches + total_hooks == 0:
        await update.message.reply_text(
            "❌ No offsets found!\n\n"
            "Try: `0x123456` or `lib.so - 0x123456 HOOK OFFSET`",
            parse_mode='Markdown'
        )
        return
    
    # Store parser in context for later use
    context.user_data['parser'] = parser
    
    # Generate default RET0 output
    patches, count = parser.generate_patch_lib("libanogs.so", "00 00 80 D2 C0 03 5F D6")
    
    response = f"✅ **{count} PATCH_LIB Generated**\n\n"
    response += "```cpp\n" + "\n".join(patches) + "\n```\n\n"
    
    # Quick action buttons
    keyboard = [
        [InlineKeyboardButton("🔄 RET", callback_data="ret"), InlineKeyboardButton("RET0", callback_data="ret0")],
        [InlineKeyboardButton("NOP", callback_data="nop"), InlineKeyboardButton("CUSTOM", callback_data="custom")],
        [InlineKeyboardButton("📋 Copy All", callback_data="copy_all"), InlineKeyboardButton("🔍 Debug", callback_data="debug")]
    ]
    
    await update.message.reply_text(response, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button interactions"""
    query = update.callback_query
    await query.answer()
    
    parser = context.user_data.get('parser')
    if not parser:
        await query.edit_message_text("❌ No data found. New input bhejo!")
        return
    
    data = query.data
    
    if data == 'debug':
        debug_info = parser.get_debug_info()
        await query.edit_message_text(debug_info + "\nNew input bhejo for fresh parse!", parse_mode='Markdown')
        return
    
    if data == 'copy_all':
        patches, _ = parser.generate_patch_lib()
        await query.edit_message_text("📋 **Copy this:**\n\n```cpp\n" + "\n".join(patches) + "\n```", parse_mode='Markdown')
        return
    
    # Patch types
    patch_map = {
        'ret': 'C0 03 5F D6',
        'ret0': '00 00 80 D2 C0 03 5F D6',
        'nop': '1F 20 03 D5'
    }
    
    if data in patch_map:
        patch_hex = patch_map[data]
        patches, count = parser.generate_patch_lib("libanogs.so", patch_hex)
        
        response = f"✅ **{patch_hex} Applied** ({count} lines)\n\n"
        response += "```cpp\n" + "\n".join(patches) + "\n```"
        
        keyboard = [
            [InlineKeyboardButton("🔄 RET", callback_data="ret"), InlineKeyboardButton("RET0", callback_data="ret0")],
            [InlineKeyboardButton("NOP", callback_data="nop"), InlineKeyboardButton("CUSTOM", callback_data="custom")],
            [InlineKeyboardButton("📋 Copy", callback_data="copy_all")]
        ]
        
        await query.edit_message_text(
            response, 
            parse_mode='Markdown', 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == 'custom':
        await query.edit_message_text(
            "✏️ **Custom hex bhejo:**\n"
            "Example: `00 00 80 D2 C0 03 5F D6`",
            parse_mode='Markdown'
        )

async def custom_patch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom patch hex input"""
    custom_hex = update.message.text.strip()
    parser = context.user_data.get('parser')
    
    if parser:
        patches, count = parser.generate_patch_lib("libanogs.so", custom_hex)
        response = f"✅ **Custom `{custom_hex}` Applied** ({count} lines)\n\n"
        response += "```cpp\n" + "\n".join(patches) + "\n```"
        await update.message.reply_text(response, parse_mode='Markdown')

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^[0-9A-Fa-f\s]+$'), custom_patch))
    
    print("🚀 ADVANCED PATCH PARSER v2.0 - LIVE!")
    app.run_polling()

if __name__ == '__main__':
    main()
