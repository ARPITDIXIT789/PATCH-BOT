import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler

BOT_TOKEN = "8774571585:AAFKay-2UKHotwYLEOu2NxF0Y9YvY6I7zuk"

(CHOOSING_LIB, CHOOSING_RET) = range(2)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

class PatchParser:
    def __init__(self):
        self.patches = []
        self.hooks = []
        
    def parse_input(self, text):
        self.patches.clear()
        self.hooks.clear()
        
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line: continue
                
            # Patch Found format
            patch_match = re.match(r'Patch Found:\s+(\S+)\s+->\s+0x([0-9A-Fa-f]+)\s+\[h\s+([0-9A-Fa-f\s]+)\]', line)
            if patch_match:
                lib = patch_match.group(1)
                offset = patch_match.group(2).upper()
                patch_hex = patch_match.group(3).strip()
                self.patches.append((lib, offset, patch_hex))
                continue
            
            # HOOK OFFSET format
            hook_match = re.match(r'(\S+)\s*-\s*0x([0-9A-Fa-f]+)\s+HOOK OFFSET', line, re.IGNORECASE)
            if hook_match:
                lib = hook_match.group(1)
                offset = hook_match.group(2).upper()
                self.hooks.append((lib, offset))
                continue
            
            # Hook Found format
            hook_list_match = re.match(r'Hook Found:\s+(\S+)\s+->\s+0x([0-9A-Fa-f]+)', line)
            if hook_list_match:
                lib = hook_list_match.group(1)
                offset = hook_list_match.group(2).upper()
                self.hooks.append((lib, offset))
                continue
            
            # lib - offset patch_hex
            lib_patch_match = re.match(r'(\S+)\s*-\s*0x([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+(?:\s+[0-9A-Fa-f]+)*)', line)
            if lib_patch_match:
                lib = lib_patch_match.group(1)
                offset = lib_patch_match.group(2).upper()
                patch_hex = lib_patch_match.group(3).strip()
                self.patches.append((lib, offset, patch_hex))
                continue
            
            # Standalone HOOK OFFSET
            standalone_hook = re.match(r'0x([0-9A-Fa-f]+)\s+HOOK OFFSET', line, re.IGNORECASE)
            if standalone_hook:
                offset = standalone_hook.group(1).upper()
                self.hooks.append(('unknown', offset))
                continue
        
        return bool(self.patches or self.hooks)
    
    def generate_patch_lib(self, lib_name="libanogs.so", ret_type="C0 03 5F D6"):
        result = []
        all_offsets = [(lib, offset) for lib, offset, _ in self.patches] + self.hooks
        
        for lib, offset in all_offsets:
            final_lib = lib if lib != 'unknown' else lib_name
            result.append(f'PATCH_LIB("{final_lib}","0x{offset}","{ret_type}");')
        
        return result

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎯 Patch Offset Parser\n\n"
        "Input bhejo ya sirf offset do (0x338680):\n"
        "• anogs.so - 0x228168 HOOK OFFSET\n"
        "• Patch Found: libUE4.so -> 0x5952F70 [...]\n"
        "• 0x212490 HOOK OFFSET"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    parser = PatchParser()
    
    # Check if valid format detected
    if parser.parse_input(text):
        patches = parser.generate_patch_lib()
        
        response = f"✅ **{len(patches)} PATCH_LIB generated:**\n\n"
        response += "```\n" + "\n".join(patches) + "\n```"
        
        keyboard = [[InlineKeyboardButton("🔄 New RET/NOP", callback_data="change_ret")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(response, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        # Manual offset mode
        offset_match = re.match(r'0x([0-9A-Fa-f]+)', text, re.IGNORECASE)
        if offset_match:
            context.user_data['manual_offset'] = offset_match.group(1).upper()
            await update.message.reply_text(
                "✅ Offset detect: `0x{}`\n\nLib name enter karo (libanogs.so):".format(context.user_data['manual_offset']),
                parse_mode='Markdown'
            )
            return CHOOSING_LIB
        else:
            await update.message.reply_text(
                "❌ Invalid format!\n\nSirf offset bhejo: `0x338680`\nYa full format:"
            )
    
    return ConversationHandler.END

async def choose_lib(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lib_name = update.message.text.strip()
    context.user_data['manual_lib'] = lib_name
    await update.message.reply_text(
        f"✅ Lib: `{lib_name}`\nOffset: `0x{context.user_data['manual_offset']}`\n\n"
        "RET type choose karo:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("RET (C0 03 5F D6)", callback_data="ret")],
            [InlineKeyboardButton("RET0 (00 00 80 D2)", callback_data="ret0")],
            [InlineKeyboardButton("NOP (1F 20 03 D5)", callback_data="nop")]
        ]),
        parse_mode='Markdown'
    )
    return CHOOSING_RET

async def choose_ret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    ret_map = {
        'ret': 'C0 03 5F D6',
        'ret0': '00 00 80 D2',
        'nop': '1F 20 03 D5'
    }
    
    ret_hex = ret_map.get(query.data, 'C0 03 5F D6')
    lib_name = context.user_data.get('manual_lib', 'libanogs.so')
    offset = context.user_data['manual_offset']
    
    patch_code = f'PATCH_LIB("{lib_name}","0x{offset}","{ret_hex}");'
    
    await query.edit_message_text(
        f"✅ **Generated:**\n\n"
        f"```{patch_code}```\n\n"
        f"Copy kar lo! 🎉"
    )
    return ConversationHandler.END

async def change_ret_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("RET (C0 03 5F D6)", callback_data="ret_all")],
        [InlineKeyboardButton("RET0 (00 00 80 D2)", callback_data="ret0_all")],
        [InlineKeyboardButton("NOP (1F 20 03 D5)", callback_data="nop_all")]
    ])
    
    await query.edit_message_text(
        "🔄 New RET type choose karo:",
        reply_markup=keyboard
    )

async def apply_ret_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    ret_map = {
        'ret_all': 'C0 03 5F D6',
        'ret0_all': '00 00 80 D2',
        'nop_all': '1F 20 03 D5'
    }
    
    ret_hex = ret_map.get(query.data, 'C0 03 5F D6')
    
    # Re-parse last input
    parser = PatchParser()
    parser.parse_input(context.user_data.get('last_text', query.message.reply_to_message.text))
    patches = parser.generate_patch_lib("libanogs.so", ret_hex)
    
    response = f"✅ **Applied `{ret_hex}`:**\n\n```\n" + "\n".join(patches) + "\n```"
    await query.edit_message_text(response, parse_mode='Markdown')

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
        states={
            CHOOSING_LIB: [MessageHandler(filters.TEXT, choose_lib)],
            CHOOSING_RET: [CallbackQueryHandler(choose_ret, pattern="^(ret|ret0|nop)$")]
        },
        fallbacks=[],
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(change_ret_callback, pattern="^change_ret$"))
    app.add_handler(CallbackQueryHandler(apply_ret_all, pattern="^(ret_all|ret0_all|nop_all)$"))
    
    print("🤖 Updated Bot Started!")
    app.run_polling()

if __name__ == '__main__':
    main()
