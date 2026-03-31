import re
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

BOT_TOKEN = "8774571585:AAFKay-2UKHotwYLEOu2NxF0Y9YvY6I7zuk"
HOOK_FILE = "hook.txt"

class AdvancedParser:
    def __init__(self):
        self.hooks = self.load_hooks()
    
    def load_hooks(self):
        """Load hooks from hook.txt file"""
        hooks = {}
        if os.path.exists(HOOK_FILE):
            with open(HOOK_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and 'HOOK OFFSET' in line:
                        # Parse format: "ANOGS - 0x1C79D4 HOOK OFFSET"
                        match = re.search(r'(\w+)\s*-\s*(0x[0-9A-Fa-f]+)\s+HOOK OFFSET', line, re.IGNORECASE)
                        if match:
                            lib = match.group(1)
                            offset = match.group(2).upper()
                            key = f"{lib}:{offset}"
                            hooks[key] = True
        return hooks
    
    def parse_patch_line(self, line):
        """Parse advanced patch format"""
        line = line.strip()
        if not line:
            return None
        
        # Format: "Patch Found: libUE4.so -> 0x5952F70 [h 00 00 80 D2 C0 03 5F D6]"
        patch_match = re.search(r'Patch Found:\s*(\w+\.so)\s*->\s*(0x[0-9A-Fa-f]+)\s*\[h\s*(.+?)\]', line, re.IGNORECASE)
        if patch_match:
            return {
                'type': 'patch',
                'lib': patch_match.group(1),
                'offset': patch_match.group(2).upper(),
                'hex': patch_match.group(3).strip()
            }
        
        # Format: "ANOGS - 0x1C79D4 HOOK OFFSET"
        hook_match = re.search(r'(\w+\.so)\s*-\s*(0x[0-9A-Fa-f]+)\s+HOOK OFFSET', line, re.IGNORECASE)
        if hook_match:
            return {
                'type': 'hook',
                'lib': hook_match.group(1),
                'offset': hook_match.group(2).upper(),
                'hex': None
            }
        
        # Format: "ANOGS - 0x268174 C0 03 5F D6"
        hex_match = re.search(r'(\w+\.so)\s*-\s*(0x[0-9A-Fa-f]+)\s+([0-9A-Fa-f\s]+)$', line, re.IGNORECASE)
        if hex_match:
            return {
                'type': 'patch',
                'lib': hex_match.group(1),
                'offset': hex_match.group(2).upper(),
                'hex': hex_match.group(3).strip()
            }
        
        return None
    
    def extract_offsets_with_info(self, text):
        """Extract offsets with their associated library and hex values"""
        results = []
        lines = text.split('\n')
        
        # First pass: try to parse advanced format
        for line in lines:
            parsed = self.parse_patch_line(line)
            if parsed:
                results.append(parsed)
                continue
            
            # Fallback: simple offset extraction
            simple_matches = re.findall(r'0x([0-9A-Fa-f]{6,8})', line, re.IGNORECASE)
            for match in simple_matches:
                offset = f"0x{match.upper()}"
                # Check if this offset is a hook
                key = f"libanogs.so:{offset}"
                is_hook = key in self.hooks
                
                # Try to detect lib from line
                lib_match = re.search(r'(\w+\.so)', line, re.IGNORECASE)
                lib = lib_match.group(1) if lib_match else "libanogs.so"
                
                # Try to detect hex from line
                hex_match = re.search(r'[h\s]+([0-9A-Fa-f]{2}\s+[0-9A-Fa-f]{2}\s+[0-9A-Fa-f]{2}\s+[0-9A-Fa-f]{2})', line, re.IGNORECASE)
                hex_val = hex_match.group(1) if hex_match else None
                
                results.append({
                    'type': 'hook' if is_hook else ('patch' if hex_val else 'offset'),
                    'lib': lib,
                    'offset': offset,
                    'hex': hex_val
                })
        
        return results

def generate_patch_string(lib, offset, hex_val):
    """Generate patch string with proper formatting"""
    if hex_val:
        return f'PATCH_LIB("{lib}","{offset}","{hex_val}");'
    return f'PATCH_LIB("{lib}","{offset}","00 00 80 D2 C0 03 5F D6");'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎯 ADVANCED PATCH BOT\n\n"
        "Send offsets in any format:\n"
        "• 0x123456\n"
        "• anogs.so - 0xABCDEF\n"
        "• Patch Found: libUE4.so -> 0x5952F70 [h 00 00 80 D2 C0 03 5F D6]\n"
        "• ANOGS - 0x1C79D4 HOOK OFFSET\n\n"
        f"📁 Hook file loaded: {len(AdvancedParser().hooks)} hooks"
    )

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data['input'] = text
    
    parser = AdvancedParser()
    parsed_items = parser.extract_offsets_with_info(text)
    
    if not parsed_items:
        await update.message.reply_text("❌ No valid offsets found! Use 0x... format")
        return
    
    # Group by type for display
    hooks = [item for item in parsed_items if item['type'] == 'hook']
    patches = [item for item in parsed_items if item['type'] == 'patch']
    offsets = [item for item in parsed_items if item['type'] == 'offset']
    
    response = f"✅ Found {len(parsed_items)} items:\n"
    response += f"   🔧 Patches: {len(patches)}\n"
    response += f"   🪝 Hooks: {len(hooks)}\n"
    response += f"   📍 Offsets: {len(offsets)}\n\n"
    
    # Show hooks found
    if hooks:
        response += "🪝 **HOOKS DETECTED:**\n"
        for hook in hooks:
            response += f"   • {hook['lib']} {hook['offset']}\n"
        response += "\n"
    
    # Store parsed items for later use
    context.user_data['parsed_items'] = parsed_items
    
    # Generate initial patches (using default hex or detected hex)
    patches_list = []
    for item in parsed_items:
        if item['type'] == 'hook':
            # For hooks, we still generate patch but mark as hook
            patches_list.append(generate_patch_string(item['lib'], item['offset'], None))
        else:
            hex_val = item.get('hex')
            patches_list.append(generate_patch_string(item['lib'], item['offset'], hex_val))
    
    response += "```\n" + "\n".join(patches_list) + "\n```"
    
    keyboard = [
        [InlineKeyboardButton("RET", callback_data="ret"), 
         InlineKeyboardButton("RET0", callback_data="ret0")],
        [InlineKeyboardButton("NOP", callback_data="nop"),
         InlineKeyboardButton("Show Hooks", callback_data="show_hooks")]
    ]
    
    await update.message.reply_text(
        response, 
        parse_mode='Markdown', 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "show_hooks":
        parser = AdvancedParser()
        if parser.hooks:
            response = "🪝 **HOOK LIST:**\n\n"
            for hook_key in sorted(parser.hooks.keys()):
                response += f"• {hook_key.replace(':', ' - ')}\n"
                if len(response) > 3500:  # Telegram message limit
                    response += "\n... and more"
                    break
            await query.edit_message_text(response, parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ No hooks found in hook.txt file")
        return
    
    parsed_items = context.user_data.get('parsed_items', [])
    if not parsed_items:
        await query.edit_message_text("❌ No data found! Please send offsets again.")
        return
    
    hex_map = {
        'ret': 'C0 03 5F D6',
        'ret0': '00 00 80 D2 C0 03 5F D6',
        'nop': '1F 20 03 D5'
    }
    
    hex_val = hex_map.get(query.data, '00 00 80 D2 C0 03 5F D6')
    
    # Generate patches with new hex value
    patches = []
    hook_count = 0
    
    for item in parsed_items:
        if item['type'] == 'hook':
            hook_count += 1
            # For hooks, we still patch but show warning
            patches.append(f"// HOOK OFFSET\n{generate_patch_string(item['lib'], item['offset'], hex_val)}")
        else:
            patches.append(generate_patch_string(item['lib'], item['offset'], hex_val))
    
    response = f"🔧 Applied: {query.data.upper()}\n"
    if hook_count > 0:
        response += f"⚠️ Warning: {hook_count} hook offset(s) detected!\n\n"
    response += "```\n" + "\n".join(patches) + "\n```"
    
    await query.edit_message_text(response, parse_mode='Markdown')

def main():
    # Create hook.txt if it doesn't exist
    if not os.path.exists(HOOK_FILE):
        with open(HOOK_FILE, 'w') as f:
            f.write("# Add hooks in format: libname.so - 0xOFFSET HOOK OFFSET\n")
            f.write("# Example: libanogs.so - 0x1C79D4 HOOK OFFSET\n")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    app.add_handler(CallbackQueryHandler(button_click))
    
    print("✅ ADVANCED BOT STARTED!")
    print(f"📁 Hook file: {HOOK_FILE}")
    print(f"🪝 Hooks loaded: {len(AdvancedParser().hooks)}")
    app.run_polling()

if __name__ == '__main__':
    main()
