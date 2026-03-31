import re
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

BOT_TOKEN = "8774571585:AAFKay-2UKHotwYLEOu2NxF0Y9YvY6I7zuk"
HOOK_FILE = "hook.txt"

class AdvancedParser:
    def __init__(self):
        self.hooks = self.load_hooks()
        self.hook_details = self.load_hook_details()
        self.complete_hooks = self.load_complete_hooks()
    
    def load_hooks(self):
        """Load hooks from hook.txt file - supports multiple formats"""
        hooks = {}
        if os.path.exists(HOOK_FILE):
            with open(HOOK_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Format 1: HOOK_LIB("libanogs.so","0x2328F0", ...
                hook_lib_pattern = r'HOOK_LIB\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,'
                for match in re.finditer(hook_lib_pattern, content):
                    lib = match.group(1)
                    offset = match.group(2).upper()
                    key = f"{lib}:{offset}"
                    hooks[key] = {'type': 'HOOK_LIB', 'offset': offset, 'lib': lib}
                
                # Format 2: HOOK_LIB_NO_ORIG("libanogs.so","0x37FD78", ...
                hook_no_orig_pattern = r'HOOK_LIB_NO_ORIG\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,'
                for match in re.finditer(hook_no_orig_pattern, content):
                    lib = match.group(1)
                    offset = match.group(2).upper()
                    key = f"{lib}:{offset}"
                    hooks[key] = {'type': 'HOOK_LIB_NO_ORIG', 'offset': offset, 'lib': lib}
                
                # Format 3: Simple format: libanogs.so 0x2328F0 HOOK
                simple_pattern = r'(\w+\.so)\s+(0x[0-9A-Fa-f]+)\s+(?:HOOK|HOOK_LIB|HOOK_LIB_NO_ORIG)'
                for match in re.finditer(simple_pattern, content, re.IGNORECASE):
                    lib = match.group(1)
                    offset = match.group(2).upper()
                    key = f"{lib}:{offset}"
                    if key not in hooks:
                        hooks[key] = {'type': 'HOOK', 'offset': offset, 'lib': lib}
                
                # Format 4: ANOGS - 0x1C79D4 HOOK OFFSET
                hook_offset_pattern = r'(\w+\.so)\s*-\s*(0x[0-9A-Fa-f]+)\s+HOOK OFFSET'
                for match in re.finditer(hook_offset_pattern, content, re.IGNORECASE):
                    lib = match.group(1)
                    offset = match.group(2).upper()
                    key = f"{lib}:{offset}"
                    if key not in hooks:
                        hooks[key] = {'type': 'HOOK', 'offset': offset, 'lib': lib}
        
        return hooks
    
    def load_complete_hooks(self):
        """Load complete hook code (including function definitions) from hook.txt"""
        complete_hooks = {}
        if os.path.exists(HOOK_FILE):
            with open(HOOK_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Split by HOOK_LIB or HOOK_LIB_NO_ORIG to get complete hook blocks
                # Pattern to match complete hook blocks (function definition + HOOK_LIB)
                hook_block_pattern = r'((?:__int64\s+.*?\{[^}]*\})\s*(?:HOOK_LIB(?:_NO_ORIG)?\s*\([^;]+\);))'
                matches = re.finditer(hook_block_pattern, content, re.DOTALL)
                
                for match in matches:
                    block = match.group(1)
                    # Extract offset from the block
                    offset_match = re.search(r'HOOK_LIB(?:_NO_ORIG)?\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"', block)
                    if offset_match:
                        lib = offset_match.group(1)
                        offset = offset_match.group(2).upper()
                        key = f"{lib}:{offset}"
                        complete_hooks[key] = block.strip()
                
                # Also handle cases where only HOOK_LIB without function definition
                hook_only_pattern = r'HOOK_LIB(?:_NO_ORIG)?\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*([^,]+)(?:,\s*([^)]+))?\s*\);'
                for match in re.finditer(hook_only_pattern, content):
                    lib = match.group(1)
                    offset = match.group(2).upper()
                    key = f"{lib}:{offset}"
                    if key not in complete_hooks:
                        complete_hooks[key] = match.group(0).strip()
        
        return complete_hooks
    
    def load_hook_details(self):
        """Load detailed hook information from hook.txt"""
        details = {}
        if os.path.exists(HOOK_FILE):
            with open(HOOK_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Extract function names and details
                hook_pattern = r'HOOK_LIB\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*(\w+)\s*,\s*(\w+)\s*\)'
                for match in re.finditer(hook_pattern, content):
                    lib = match.group(1)
                    offset = match.group(2).upper()
                    hook_func = match.group(3)
                    orig_func = match.group(4)
                    key = f"{lib}:{offset}"
                    details[key] = f"HOOK_LIB with function {hook_func} (original: {orig_func})"
                
                hook_no_orig_pattern = r'HOOK_LIB_NO_ORIG\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*(\w+)\s*\)'
                for match in re.finditer(hook_no_orig_pattern, content):
                    lib = match.group(1)
                    offset = match.group(2).upper()
                    hook_func = match.group(3)
                    key = f"{lib}:{offset}"
                    details[key] = f"HOOK_LIB_NO_ORIG with function {hook_func}"
        
        return details
    
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
                # Check if this offset is a hook
                key = f"{parsed['lib']}:{parsed['offset']}"
                if key in self.hooks:
                    parsed['is_hook'] = True
                    parsed['hook_type'] = self.hooks[key]['type']
                    parsed['hook_details'] = self.hook_details.get(key, '')
                    parsed['complete_hook'] = self.complete_hooks.get(key, '')
                else:
                    parsed['is_hook'] = False
                results.append(parsed)
                continue
            
            # Fallback: simple offset extraction
            simple_matches = re.findall(r'0x([0-9A-Fa-f]{6,8})', line, re.IGNORECASE)
            for match in simple_matches:
                offset = f"0x{match.upper()}"
                
                # Try to detect lib from line
                lib_match = re.search(r'(\w+\.so)', line, re.IGNORECASE)
                lib = lib_match.group(1) if lib_match else "libanogs.so"
                
                # Check if this offset is a hook
                key = f"{lib}:{offset}"
                is_hook = key in self.hooks
                hook_type = self.hooks[key]['type'] if is_hook else None
                hook_details = self.hook_details.get(key, '') if is_hook else ''
                complete_hook = self.complete_hooks.get(key, '') if is_hook else ''
                
                # Try to detect hex from line
                hex_match = re.search(r'[h\s]+([0-9A-Fa-f]{2}\s+[0-9A-Fa-f]{2}\s+[0-9A-Fa-f]{2}\s+[0-9A-Fa-f]{2})', line, re.IGNORECASE)
                hex_val = hex_match.group(1) if hex_match else None
                
                results.append({
                    'type': 'hook' if is_hook else ('patch' if hex_val else 'offset'),
                    'lib': lib,
                    'offset': offset,
                    'hex': hex_val,
                    'is_hook': is_hook,
                    'hook_type': hook_type,
                    'hook_details': hook_details,
                    'complete_hook': complete_hook
                })
        
        return results

def generate_patch_string(lib, offset, hex_val, is_hook=False, hook_type=None):
    """Generate patch string with proper formatting"""
    if is_hook:
        if hook_type == 'HOOK_LIB_NO_ORIG':
            return f'// ⚠️ HOOK DETECTED: {hook_type}\n// {lib} {offset} requires hook function\nPATCH_LIB("{lib}","{offset}","{hex_val if hex_val else "00 00 80 D2 C0 03 5F D6"}"); // HOOK OFFSET - USE WITH CAUTION'
        else:
            return f'// ⚠️ HOOK DETECTED: {hook_type if hook_type else "HOOK"}\nPATCH_LIB("{lib}","{offset}","{hex_val if hex_val else "00 00 80 D2 C0 03 5F D6"}"); // HOOK OFFSET'
    
    if hex_val:
        return f'PATCH_LIB("{lib}","{offset}","{hex_val}");'
    return f'PATCH_LIB("{lib}","{offset}","00 00 80 D2 C0 03 5F D6");'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parser = AdvancedParser()
    await update.message.reply_text(
        "🎯 ADVANCED PATCH BOT\n\n"
        "Send offsets in any format:\n"
        "• 0x123456\n"
        "• anogs.so - 0xABCDEF\n"
        "• Patch Found: libUE4.so -> 0x5952F70 [h 00 00 80 D2 C0 03 5F D6]\n"
        "• ANOGS - 0x1C79D4 HOOK OFFSET\n\n"
        f"📁 Hook file loaded: {len(parser.hooks)} hooks\n"
        f"🪝 Complete hooks: {len(parser.complete_hooks)}\n"
        f"⚡ If hook offset is detected, complete hook code will be shown!"
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
    hooks = [item for item in parsed_items if item.get('is_hook', False)]
    patches = [item for item in parsed_items if item['type'] == 'patch' and not item.get('is_hook')]
    offsets = [item for item in parsed_items if item['type'] == 'offset' and not item.get('is_hook')]
    
    response = f"✅ Found {len(parsed_items)} items:\n"
    response += f"   🔧 Patches: {len(patches)}\n"
    response += f"   🪝 Hooks: {len(hooks)}\n"
    response += f"   📍 Offsets: {len(offsets)}\n\n"
    
    # Show complete hook code if found
    if hooks:
        response += "🪝 **COMPLETE HOOK CODE FOUND:**\n\n"
        for hook in hooks:
            if hook.get('complete_hook'):
                response += f"**Offset: {hook['offset']}**\n"
                response += "```c\n"
                response += hook['complete_hook']
                response += "\n```\n\n"
            else:
                response += f"⚠️ Hook {hook['offset']} found but complete code not available\n"
        response += "---\n\n"
    
    # Store parsed items for later use
    context.user_data['parsed_items'] = parsed_items
    
    # Generate initial patches
    patches_list = []
    for item in parsed_items:
        patches_list.append(generate_patch_string(
            item['lib'], 
            item['offset'], 
            item.get('hex'),
            item.get('is_hook', False),
            item.get('hook_type')
        ))
    
    response += "**PATCH CODE:**\n"
    response += "```\n" + "\n".join(patches_list) + "\n```"
    
    keyboard = [
        [InlineKeyboardButton("RET", callback_data="ret"), 
         InlineKeyboardButton("RET0", callback_data="ret0")],
        [InlineKeyboardButton("NOP", callback_data="nop"),
         InlineKeyboardButton("📋 All Hooks", callback_data="show_hooks")]
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
        if parser.complete_hooks:
            response = "🪝 **ALL COMPLETE HOOKS:**\n\n"
            for key, hook_code in sorted(parser.complete_hooks.items()):
                lib, offset = key.split(':')
                response += f"**{lib} {offset}**\n"
                response += "```c\n"
                # Truncate if too long
                if len(hook_code) > 800:
                    response += hook_code[:800] + "\n... (truncated)"
                else:
                    response += hook_code
                response += "\n```\n\n"
                if len(response) > 3500:  # Telegram message limit
                    response += "\n... and more hooks available"
                    break
            await query.edit_message_text(response, parse_mode='Markdown')
        elif parser.hooks:
            response = "🪝 **HOOK OFFSETS:**\n\n"
            for key, hook in sorted(parser.hooks.items()):
                lib, offset = key.split(':')
                response += f"• {lib} {offset} [{hook['type']}]\n"
                if len(response) > 3500:
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
    hook_lib_no_orig_count = 0
    
    for item in parsed_items:
        if item.get('is_hook'):
            hook_count += 1
            if item.get('hook_type') == 'HOOK_LIB_NO_ORIG':
                hook_lib_no_orig_count += 1
            patches.append(generate_patch_string(
                item['lib'], 
                item['offset'], 
                hex_val,
                True,
                item.get('hook_type')
            ))
        else:
            patches.append(generate_patch_string(item['lib'], item['offset'], hex_val))
    
    response = f"🔧 Applied: {query.data.upper()}\n"
    if hook_count > 0:
        response += f"⚠️ **WARNING:** {hook_count} hook offset(s) detected!\n"
        if hook_lib_no_orig_count > 0:
            response += f"   🔴 {hook_lib_no_orig_count} HOOK_LIB_NO_ORIG offsets - These require hook functions!\n"
        response += "   ⚡ Patching hooks may cause crashes or instability\n\n"
    
    response += "```\n" + "\n".join(patches) + "\n```"
    
    await query.edit_message_text(response, parse_mode='Markdown')

def main():
    # Create hook.txt if it doesn't exist
    if not os.path.exists(HOOK_FILE):
        with open(HOOK_FILE, 'w', encoding='utf-8') as f:
            f.write("""// Example Hook File
// Complete hook with function definition and HOOK_LIB

__int64 (*osub_2328F0)(__int64 a1, const char *a2, __int64 a3);
__int64 hsub_2328F0(__int64 a1, const char *a2, __int64 a3) {
    auto case16 = reinterpret_cast<uintptr_t>(__builtin_return_address(0));
    std::string str_a2(a2);
    if (strstr(a2, oxorany("XTask_builtin.zip_vm_main.img"))) {
        sleep(100000);
    }
    if (strstr(a2, oxorany("crash")) || strstr(a2, oxorany("opcode"))){
        return 0LL;
    } else {
        auto case16 = osub_2328F0(a1, a2, a3);
        return case16;
    }
}
HOOK_LIB("libanogs.so","0x2328F0", hsub_2328F0, osub_2328F0);

// HOOK_LIB_NO_ORIG example
__int64 __fastcall hsub_37FD78(_QWORD *a1, __int64 a2, unsigned __int64 a3, unsigned int a4) {
    return 1LL;  // Always safe!
}
HOOK_LIB_NO_ORIG("libanogs.so", "0x37FD78", hsub_37FD78);

// Simple hook offset
libanogs.so 0x275A0C HOOK
""")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    app.add_handler(CallbackQueryHandler(button_click))
    
    parser = AdvancedParser()
    print("✅ ADVANCED BOT STARTED!")
    print(f"📁 Hook file: {HOOK_FILE}")
    print(f"🪝 Hooks loaded: {len(parser.hooks)}")
    print(f"📝 Complete hooks with code: {len(parser.complete_hooks)}")
    print("⚡ Now bot will show complete hook code when hook offset is detected!")
    app.run_polling()

if __name__ == '__main__':
    main()
