import html
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from telegram import Document, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN")
HOOK_FILE = Path(os.getenv("HOOK_FILE", "hook.txt"))
DEFAULT_PATCH_HEX = "00 00 80 D2 C0 03 5F D6"
MAX_MESSAGE_LENGTH = 3800
MAX_UPLOAD_SIZE = 1024 * 1024
CUSTOM_HEX_CALLBACK = "custom_hex"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
)
LOGGER = logging.getLogger("patch-bot")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@dataclass
class HookEntry:
    hook_type: str
    lib: str
    offset: str
    hook_func: Optional[str] = None
    orig_func: Optional[str] = None
    details: str = ""
    complete_hook: str = ""


@dataclass
class ParsedItem:
    item_type: str
    lib: str
    offset: str
    hex_value: Optional[str] = None
    is_hook: bool = False
    hook_type: Optional[str] = None
    hook_details: str = ""
    complete_hook: str = ""

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "item_type": self.item_type,
            "lib": self.lib,
            "offset": self.offset,
            "hex_value": self.hex_value,
            "is_hook": self.is_hook,
            "hook_type": self.hook_type,
            "hook_details": self.hook_details,
            "complete_hook": self.complete_hook,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Optional[str]]) -> "ParsedItem":
        return cls(
            item_type=str(data.get("item_type", "offset")),
            lib=str(data.get("lib", "libanogs.so")),
            offset=str(data.get("offset", "0x0")),
            hex_value=data.get("hex_value"),
            is_hook=bool(data.get("is_hook", False)),
            hook_type=data.get("hook_type"),
            hook_details=str(data.get("hook_details", "")),
            complete_hook=str(data.get("complete_hook", "")),
        )


class AdvancedParser:
    hook_lib_pattern = re.compile(
        r'HOOK_LIB\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*([\w:]+)\s*,\s*([\w:]+)\s*\)',
        re.IGNORECASE,
    )
    hook_no_orig_pattern = re.compile(
        r'HOOK_LIB_NO_ORIG\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*([\w:]+)\s*\)',
        re.IGNORECASE,
    )
    simple_hook_pattern = re.compile(
        r'(\w+\.so)\s+(0x[0-9A-Fa-f]+)\s+(?:HOOK|HOOK_LIB|HOOK_LIB_NO_ORIG)',
        re.IGNORECASE,
    )
    hook_offset_pattern = re.compile(
        r'(\w+\.so)\s*-\s*(0x[0-9A-Fa-f]+)\s+HOOK OFFSET',
        re.IGNORECASE,
    )
    patch_found_pattern = re.compile(
        r'Patch Found:\s*(\w+\.so)\s*->\s*(0x[0-9A-Fa-f]+)\s*\[h\s*(.+?)\]',
        re.IGNORECASE,
    )
    raw_hex_patch_pattern = re.compile(
        r'(\w+\.so)\s*-\s*(0x[0-9A-Fa-f]+)\s+([0-9A-Fa-f\s]+)$',
        re.IGNORECASE,
    )
    offset_pattern = re.compile(r'0x([0-9A-Fa-f]{6,8})', re.IGNORECASE)
    lib_pattern = re.compile(r'(\w+\.so)', re.IGNORECASE)
    compact_hex_pattern = re.compile(
        r'([0-9A-Fa-f]{2}(?:\s+[0-9A-Fa-f]{2}){3,})',
        re.IGNORECASE,
    )
    hook_block_pattern = re.compile(
        r'((?:[\w\s\*\(\),:&<>]+\s+[\w:]+\s*\([^)]*\)\s*\{.*?\})\s*'
        r'(?:HOOK_LIB(?:_NO_ORIG)?\s*\([^;]+\);))',
        re.DOTALL,
    )
    hook_only_pattern = re.compile(
        r'HOOK_LIB(?:_NO_ORIG)?\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*([^)]+?)\s*\);',
        re.IGNORECASE,
    )

    def __init__(self, hook_file: Path) -> None:
        self.hook_file = hook_file
        self._last_mtime: Optional[float] = None
        self.hooks: Dict[str, HookEntry] = {}

    def ensure_loaded(self, force: bool = False) -> None:
        if not self.hook_file.exists():
            if self.hooks:
                LOGGER.warning("Hook file %s is missing. Clearing cache.", self.hook_file)
            self.hooks = {}
            self._last_mtime = None
            return

        mtime = self.hook_file.stat().st_mtime
        if not force and self._last_mtime == mtime:
            return

        content = self.hook_file.read_text(encoding="utf-8", errors="ignore")
        self.hooks = self._parse_hook_content(content)
        self._last_mtime = mtime
        LOGGER.info("Reloaded %s hook entries from %s", len(self.hooks), self.hook_file)

    def _parse_hook_content(self, content: str) -> Dict[str, HookEntry]:
        hooks: Dict[str, HookEntry] = {}

        for match in self.hook_lib_pattern.finditer(content):
            lib, offset, hook_func, orig_func = match.groups()
            key = self._make_key(lib, offset)
            hooks[key] = HookEntry(
                hook_type="HOOK_LIB",
                lib=lib,
                offset=offset.upper(),
                hook_func=hook_func,
                orig_func=orig_func,
                details=f"HOOK_LIB with function {hook_func} (original: {orig_func})",
            )

        for match in self.hook_no_orig_pattern.finditer(content):
            lib, offset, hook_func = match.groups()
            key = self._make_key(lib, offset)
            hooks[key] = HookEntry(
                hook_type="HOOK_LIB_NO_ORIG",
                lib=lib,
                offset=offset.upper(),
                hook_func=hook_func,
                details=f"HOOK_LIB_NO_ORIG with function {hook_func}",
            )

        for match in self.simple_hook_pattern.finditer(content):
            lib, offset = match.groups()
            key = self._make_key(lib, offset)
            hooks.setdefault(
                key,
                HookEntry(
                    hook_type="HOOK",
                    lib=lib,
                    offset=offset.upper(),
                    details="Simple hook offset",
                ),
            )

        for match in self.hook_offset_pattern.finditer(content):
            lib, offset = match.groups()
            key = self._make_key(lib, offset)
            hooks.setdefault(
                key,
                HookEntry(
                    hook_type="HOOK",
                    lib=lib,
                    offset=offset.upper(),
                    details="Hook offset",
                ),
            )

        for match in self.hook_block_pattern.finditer(content):
            block = match.group(1).strip()
            hook_ref = re.search(
                r'HOOK_LIB(?:_NO_ORIG)?\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"',
                block,
                re.IGNORECASE,
            )
            if not hook_ref:
                continue
            lib, offset = hook_ref.groups()
            key = self._make_key(lib, offset)
            hooks.setdefault(
                key,
                HookEntry(hook_type="HOOK", lib=lib, offset=offset.upper()),
            ).complete_hook = block

        for match in self.hook_only_pattern.finditer(content):
            lib, offset, _ = match.groups()
            key = self._make_key(lib, offset)
            hooks.setdefault(
                key,
                HookEntry(hook_type="HOOK", lib=lib, offset=offset.upper()),
            ).complete_hook = hooks[key].complete_hook or match.group(0).strip()

        return hooks

    def parse_patch_line(self, line: str) -> Optional[ParsedItem]:
        stripped = line.strip()
        if not stripped:
            return None

        patch_match = self.patch_found_pattern.search(stripped)
        if patch_match:
            lib, offset, hex_value = patch_match.groups()
            return self._attach_hook_info(
                ParsedItem(
                    item_type="patch",
                    lib=lib,
                    offset=offset.upper(),
                    hex_value=self._normalize_hex(hex_value),
                )
            )

        hook_match = self.hook_offset_pattern.search(stripped)
        if hook_match:
            lib, offset = hook_match.groups()
            return self._attach_hook_info(
                ParsedItem(item_type="hook", lib=lib, offset=offset.upper())
            )

        raw_hex_match = self.raw_hex_patch_pattern.search(stripped)
        if raw_hex_match:
            lib, offset, hex_value = raw_hex_match.groups()
            return self._attach_hook_info(
                ParsedItem(
                    item_type="patch",
                    lib=lib,
                    offset=offset.upper(),
                    hex_value=self._normalize_hex(hex_value),
                )
            )

        return None

    def extract_offsets_with_info(self, text: str) -> List[ParsedItem]:
        self.ensure_loaded()
        results: List[ParsedItem] = []
        seen = set()

        for line in text.splitlines():
            parsed = self.parse_patch_line(line)
            if parsed:
                key = (parsed.lib, parsed.offset, parsed.hex_value, parsed.item_type)
                if key not in seen:
                    seen.add(key)
                    results.append(parsed)
                continue

            for match in self.offset_pattern.findall(line):
                offset = f"0x{match.upper()}"
                lib_match = self.lib_pattern.search(line)
                lib = lib_match.group(1) if lib_match else "libanogs.so"
                hex_match = self.compact_hex_pattern.search(line)
                hex_value = self._normalize_hex(hex_match.group(1)) if hex_match else None
                item_type = "patch" if hex_value else "offset"
                parsed = self._attach_hook_info(
                    ParsedItem(
                        item_type=item_type,
                        lib=lib,
                        offset=offset,
                        hex_value=hex_value,
                    )
                )
                key = (parsed.lib, parsed.offset, parsed.hex_value, parsed.item_type)
                if key not in seen:
                    seen.add(key)
                    results.append(parsed)

        return results

    def get_all_hooks(self) -> List[HookEntry]:
        self.ensure_loaded()
        return [self.hooks[key] for key in sorted(self.hooks)]

    def stats(self) -> Dict[str, int]:
        self.ensure_loaded()
        complete_hook_count = sum(1 for hook in self.hooks.values() if hook.complete_hook)
        no_orig_count = sum(
            1 for hook in self.hooks.values() if hook.hook_type == "HOOK_LIB_NO_ORIG"
        )
        return {
            "hooks": len(self.hooks),
            "complete_hooks": complete_hook_count,
            "no_orig_hooks": no_orig_count,
        }

    def analyze_health(self) -> Tuple[List[str], List[str]]:
        self.ensure_loaded(force=True)
        warnings: List[str] = []
        info: List[str] = []

        if not self.hook_file.exists():
            return ["hook.txt is missing."], info

        content = self.hook_file.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()

        brace_balance = 0
        for line_number, line in enumerate(lines, 1):
            brace_balance += line.count("{")
            brace_balance -= line.count("}")
            if brace_balance < 0:
                warnings.append(f"Line {line_number}: closing brace appears before an opening brace.")
                brace_balance = 0

        if brace_balance != 0:
            warnings.append("Brace count is unbalanced in hook.txt.")

        macro_offsets: Dict[str, int] = {}
        macro_pattern = re.compile(
            r'HOOK_LIB(?:_NO_ORIG)?\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"',
            re.IGNORECASE,
        )
        for line_number, line in enumerate(lines, 1):
            match = macro_pattern.search(line)
            if not match:
                continue
            key = self._make_key(match.group(1), match.group(2))
            if key in macro_offsets:
                warnings.append(
                    f"Line {line_number}: duplicate hook macro for {key} "
                    f"(first seen on line {macro_offsets[key]})."
                )
            else:
                macro_offsets[key] = line_number

        missing_hook_macros = self._find_missing_hook_macros(lines, macro_offsets)
        warnings.extend(missing_hook_macros)

        info.append(f"Parsed hooks: {len(self.hooks)}")
        info.append(f"Macro offsets: {len(macro_offsets)}")
        info.append(f"Complete hook blocks: {sum(1 for hook in self.hooks.values() if hook.complete_hook)}")
        return warnings, info

    def _find_missing_hook_macros(
        self, lines: List[str], macro_offsets: Dict[str, int]
    ) -> List[str]:
        warnings: List[str] = []
        pending: Optional[Tuple[str, str]] = None
        func_pattern = re.compile(
            r'(?:hsub|sub|hook_sub)_(?P<offset>[0-9A-Fa-f]{6,8})',
            re.IGNORECASE,
        )

        for line_number, line in enumerate(lines, 1):
            func_match = func_pattern.search(line)
            if func_match:
                pending = ("libanogs.so", f"0x{func_match.group('offset').upper()}")

            macro_match = re.search(
                r'HOOK_LIB(?:_NO_ORIG)?\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"',
                line,
                re.IGNORECASE,
            )
            if macro_match and pending:
                macro_key = self._make_key(macro_match.group(1), macro_match.group(2))
                pending_key = self._make_key(*pending)
                if macro_key == pending_key:
                    pending = None

            if line.strip() == "" and pending:
                pending_key = self._make_key(*pending)
                if pending_key not in macro_offsets:
                    warnings.append(
                        f"Near line {line_number}: found hook function for {pending_key} without a matching hook macro."
                    )
                pending = None

        if pending:
            pending_key = self._make_key(*pending)
            if pending_key not in macro_offsets:
                warnings.append(
                    f"End of file: found hook function for {pending_key} without a matching hook macro."
                )

        return warnings

    def _attach_hook_info(self, item: ParsedItem) -> ParsedItem:
        hook = self.hooks.get(self._make_key(item.lib, item.offset))
        if not hook:
            return item

        item.is_hook = True
        item.hook_type = hook.hook_type
        item.hook_details = hook.details
        item.complete_hook = hook.complete_hook
        if item.item_type == "offset":
            item.item_type = "hook"
        return item

    @staticmethod
    def _normalize_hex(hex_value: str) -> str:
        parts = re.findall(r"[0-9A-Fa-f]{2}", hex_value)
        return " ".join(part.upper() for part in parts)

    @staticmethod
    def _make_key(lib: str, offset: str) -> str:
        return f"{lib}:{offset.upper()}"


PARSER = AdvancedParser(HOOK_FILE)


def escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def render_code_block(code: str) -> str:
    return f"<pre>{escape_html(code)}</pre>"


def normalize_custom_hex(text: str) -> Optional[str]:
    parts = re.findall(r"[0-9A-Fa-f]{2}", text)
    joined = re.sub(r"\s+", "", text)
    if not parts or len("".join(parts)) != len(joined):
        return None
    return " ".join(part.upper() for part in parts)


def generate_patch_string(item: ParsedItem, override_hex: Optional[str] = None) -> str:
    hex_value = override_hex or item.hex_value or DEFAULT_PATCH_HEX
    if item.is_hook:
        lines = [f"// HOOK DETECTED: {item.hook_type or 'HOOK'}"]
        if item.hook_type == "HOOK_LIB_NO_ORIG":
            lines.append(f"// {item.lib} {item.offset} requires hook function wiring")
            lines.append(
                f'PATCH_LIB("{item.lib}","{item.offset}","{hex_value}"); // HOOK OFFSET - USE WITH CAUTION'
            )
            return "\n".join(lines)

        lines.append(
            f'PATCH_LIB("{item.lib}","{item.offset}","{hex_value}"); // HOOK OFFSET'
        )
        return "\n".join(lines)

    return f'PATCH_LIB("{item.lib}","{item.offset}","{hex_value}");'


def chunk_text(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> List[str]:
    if len(text) <= max_length:
        return [text]

    chunks: List[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= max_length:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(block) <= max_length:
            current = block
            continue
        for index in range(0, len(block), max_length):
            chunks.append(block[index : index + max_length])
        current = ""
    if current:
        chunks.append(current)
    return chunks


async def send_long_message(
    target_message,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    chunks = chunk_text(text)
    for index, chunk in enumerate(chunks):
        markup = reply_markup if index == len(chunks) - 1 else None
        await target_message.reply_text(
            chunk,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            disable_web_page_preview=True,
        )


def store_parsed_items(context: ContextTypes.DEFAULT_TYPE, parsed_items: List[ParsedItem]) -> None:
    context.user_data["parsed_items"] = [item.to_dict() for item in parsed_items]


async def present_parsed_items(
    target_message,
    context: ContextTypes.DEFAULT_TYPE,
    parsed_items: List[ParsedItem],
    source_label: str,
) -> None:
    store_parsed_items(context, parsed_items)
    hooks = [item for item in parsed_items if item.is_hook]
    sections = [f"<b>Source</b>: {escape_html(source_label)}", summarize_items(parsed_items)]
    if hooks:
        sections.append("<b>Complete Hook Preview</b>\n\n" + build_hook_preview(hooks[:3]))
    sections.append("<b>Patch Code</b>\n\n" + build_patch_output(parsed_items))

    await send_long_message(
        target_message,
        "\n\n".join(section for section in sections if section.strip()),
        reply_markup=build_keyboard(),
    )


async def parse_and_present_input(
    target_message,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    source_label: str,
) -> None:
    parsed_items = PARSER.extract_offsets_with_info(text)
    if not parsed_items:
        await target_message.reply_text(
            "No valid offsets found. Send values like <code>0x123456</code>, patch lines, or upload a text file.",
            parse_mode=ParseMode.HTML,
        )
        return

    await present_parsed_items(target_message, context, parsed_items, source_label)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    stats = PARSER.stats()
    message = (
        "<b>Advanced Patch Bot</b>\n\n"
        "Send offsets in any of these formats:\n"
        "- <code>0x123456</code>\n"
        "- <code>libanogs.so - 0xABCDEF</code>\n"
        "- <code>Patch Found: libUE4.so -&gt; 0x5952F70 [h 00 00 80 D2 C0 03 5F D6]</code>\n"
        "- <code>libanogs.so - 0x1C79D4 HOOK OFFSET</code>\n\n"
        f"Loaded hooks: <b>{stats['hooks']}</b>\n"
        f"Complete hook blocks: <b>{stats['complete_hooks']}</b>\n"
        f"HOOK_LIB_NO_ORIG entries: <b>{stats['no_orig_hooks']}</b>\n\n"
        "Commands: /help, /stats, /health, /reload"
    )
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    context.user_data.pop("parsed_items", None)
    context.user_data.pop("awaiting_custom_hex", None)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "<b>How to use the bot</b>\n\n"
        "Send one or many offsets in a message and the bot will:\n"
        "- detect patch-style entries\n"
        "- detect hook offsets from <code>hook.txt</code>\n"
        "- generate ready-to-copy <code>PATCH_LIB</code> lines\n"
        "- let you quickly convert all results to RET, RET0, or NOP\n\n"
        "Tips:\n"
        "- Add a library name like <code>libUE4.so</code> for better matching\n"
        "- Upload a <code>.txt</code>, <code>.log</code>, or source file to parse offsets from file content\n"
        "- Use the Custom Hex button after parsing offsets to apply your own opcode bytes\n"
        "- Keep <code>hook.txt</code> updated, then use /reload\n"
        "- Run <code>/health</code> to check hook.txt for duplicates or missing macros\n"
        "- Set the Telegram token with the <code>BOT_TOKEN</code> environment variable"
    )
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    stats = PARSER.stats()
    message = (
        "<b>Parser Stats</b>\n\n"
        f"Hook file: <code>{escape_html(str(HOOK_FILE))}</code>\n"
        f"Total hooks: <b>{stats['hooks']}</b>\n"
        f"Complete hook blocks: <b>{stats['complete_hooks']}</b>\n"
        f"HOOK_LIB_NO_ORIG entries: <b>{stats['no_orig_hooks']}</b>"
    )
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)


async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    PARSER.ensure_loaded(force=True)
    stats = PARSER.stats()
    await update.message.reply_text(
        (
            "<b>Reload complete</b>\n\n"
            f"Hooks loaded: <b>{stats['hooks']}</b>\n"
            f"Complete hook blocks: <b>{stats['complete_hooks']}</b>"
        ),
        parse_mode=ParseMode.HTML,
    )


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    warnings, info = PARSER.analyze_health()
    sections = ["<b>Hook File Health</b>"]
    if warnings:
        sections.append("<b>Warnings</b>\n" + "\n".join(f"- {escape_html(item)}" for item in warnings[:20]))
        if len(warnings) > 20:
            sections.append(f"Showing 20 of {len(warnings)} warnings.")
    else:
        sections.append("No structural issues were found in <code>hook.txt</code>.")

    if info:
        sections.append("<b>Summary</b>\n" + "\n".join(f"- {escape_html(item)}" for item in info))

    await update.message.reply_text("\n\n".join(sections), parse_mode=ParseMode.HTML)


def build_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("RET", callback_data="ret"),
                InlineKeyboardButton("RET0", callback_data="ret0"),
            ],
            [
                InlineKeyboardButton("NOP", callback_data="nop"),
                InlineKeyboardButton("Custom Hex", callback_data=CUSTOM_HEX_CALLBACK),
            ],
            [
                InlineKeyboardButton("Matched Hooks", callback_data="show_hooks"),
            ],
        ]
    )


def summarize_items(items: List[ParsedItem]) -> str:
    hooks = [item for item in items if item.is_hook]
    patches = [item for item in items if item.item_type == "patch" and not item.is_hook]
    offsets = [item for item in items if item.item_type == "offset" and not item.is_hook]

    lines = [
        f"Found <b>{len(items)}</b> items",
        f"Patches: <b>{len(patches)}</b>",
        f"Hooks: <b>{len(hooks)}</b>",
        f"Offsets: <b>{len(offsets)}</b>",
    ]

    if hooks:
        lines.append("")
        lines.append("<b>Detected hook offsets</b>")
        for hook in hooks[:10]:
            detail = f" [{escape_html(hook.hook_type)}]" if hook.hook_type else ""
            lines.append(
                f"- <code>{escape_html(hook.lib)} {escape_html(hook.offset)}</code>{detail}"
            )
        if len(hooks) > 10:
            lines.append(f"- ... and {len(hooks) - 10} more")

    return "\n".join(lines)


def build_hook_preview(items: List[ParsedItem]) -> str:
    previews = []
    for hook in items:
        if not hook.complete_hook:
            previews.append(
                f"- <code>{escape_html(hook.lib)} {escape_html(hook.offset)}</code> complete code not available"
            )
            continue
        previews.append(
            f"<b>{escape_html(hook.lib)} {escape_html(hook.offset)}</b>\n"
            f"{render_code_block(hook.complete_hook[:1200])}"
        )
    return "\n\n".join(previews)


def build_patch_output(items: List[ParsedItem], override_hex: Optional[str] = None) -> str:
    patch_lines = [generate_patch_string(item, override_hex=override_hex) for item in items]
    return render_code_block("\n".join(patch_lines))


async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    pending_custom_hex = context.user_data.get("awaiting_custom_hex", False)
    if pending_custom_hex:
        parsed_items = get_saved_items(context)
        if not parsed_items:
            context.user_data.pop("awaiting_custom_hex", None)
            await update.message.reply_text(
                "No saved offsets found. Send offsets first, then try Custom Hex again.",
                parse_mode=ParseMode.HTML,
            )
            return

        custom_hex = normalize_custom_hex(update.message.text)
        if not custom_hex:
            await update.message.reply_text(
                "Invalid hex format. Send bytes like <code>C0 03 5F D6</code> or <code>000080D2C0035FD6</code>.",
                parse_mode=ParseMode.HTML,
            )
            return

        context.user_data.pop("awaiting_custom_hex", None)
        sections = [
            f"<b>Applied Custom Hex</b>\n<code>{escape_html(custom_hex)}</code>",
            build_patch_output(parsed_items, override_hex=custom_hex),
        ]
        await update.message.reply_text(
            "\n\n".join(sections),
            parse_mode=ParseMode.HTML,
            reply_markup=build_keyboard(),
        )
        return

    await parse_and_present_input(
        update.message,
        context,
        update.message.text,
        "text message",
    )


async def process_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.document:
        return

    document: Document = update.message.document
    if document.file_size and document.file_size > MAX_UPLOAD_SIZE:
        await update.message.reply_text(
            f"File is too large. Keep uploads under {MAX_UPLOAD_SIZE // 1024} KB.",
            parse_mode=ParseMode.HTML,
        )
        return

    allowed_suffixes = {".txt", ".log", ".cpp", ".h", ".hpp", ".c"}
    suffix = Path(document.file_name or "").suffix.lower()
    if suffix and suffix not in allowed_suffixes:
        await update.message.reply_text(
            "Unsupported file type. Upload a text-based file like .txt, .log, .c, .cpp, or .h.",
            parse_mode=ParseMode.HTML,
        )
        return

    telegram_file = await document.get_file()
    file_bytes = await telegram_file.download_as_bytearray()
    file_text = bytes(file_bytes).decode("utf-8", errors="ignore")
    combined_text = file_text
    if update.message.caption:
        combined_text = f"{update.message.caption}\n{file_text}"

    await parse_and_present_input(
        update.message,
        context,
        combined_text,
        f"file upload: {document.file_name or 'attachment'}",
    )


def get_saved_items(context: ContextTypes.DEFAULT_TYPE) -> List[ParsedItem]:
    raw_items = context.user_data.get("parsed_items", [])
    return [ParsedItem.from_dict(item) for item in raw_items]


async def show_hooks(query, items: List[ParsedItem]) -> None:
    matched_hooks = [item for item in items if item.is_hook]
    if not matched_hooks:
        await query.edit_message_text(
            "No matching hooks were found for the offsets in your last message.",
            parse_mode=ParseMode.HTML,
            reply_markup=build_keyboard(),
        )
        return

    parts = ["<b>Matched Hooks From Your Input</b>"]
    for hook in matched_hooks:
        line = (
            f"- <code>{escape_html(hook.lib)} {escape_html(hook.offset)}</code> "
            f"[{escape_html(hook.hook_type or 'HOOK')}]"
        )
        if hook.complete_hook:
            snippet = hook.complete_hook[:1200]
            line += "\n" + render_code_block(snippet)
        elif hook.hook_details:
            line += "\n" + escape_html(hook.hook_details)
        else:
            line += "\nComplete hook code not available."
        parts.append(line)

    await query.edit_message_text(
        "\n\n".join(parts),
        parse_mode=ParseMode.HTML,
        reply_markup=build_keyboard(),
    )


async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    await query.answer()
    parsed_items = get_saved_items(context)

    if query.data == "show_hooks":
        await show_hooks(query, parsed_items)
        return

    if query.data == CUSTOM_HEX_CALLBACK:
        if not parsed_items:
            await query.edit_message_text(
                "No saved offsets found. Send the offsets again to rebuild the patch list.",
                parse_mode=ParseMode.HTML,
                reply_markup=build_keyboard(),
            )
            return

        context.user_data["awaiting_custom_hex"] = True
        await query.message.reply_text(
            "Send custom hex bytes now, for example <code>C0 03 5F D6</code> or <code>000080D2C0035FD6</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    if not parsed_items:
        await query.edit_message_text(
            "No saved offsets found. Send the offsets again to rebuild the patch list.",
            parse_mode=ParseMode.HTML,
        )
        return

    hex_map = {
        "ret": "C0 03 5F D6",
        "ret0": DEFAULT_PATCH_HEX,
        "nop": "1F 20 03 D5",
    }
    override_hex = hex_map.get(query.data, DEFAULT_PATCH_HEX)
    hook_count = sum(1 for item in parsed_items if item.is_hook)
    no_orig_count = sum(
        1 for item in parsed_items if item.hook_type == "HOOK_LIB_NO_ORIG"
    )

    sections = [f"<b>Applied {escape_html(query.data.upper())}</b>"]
    if hook_count:
        warning_lines = [f"Hook offsets detected: <b>{hook_count}</b>"]
        if no_orig_count:
            warning_lines.append(f"HOOK_LIB_NO_ORIG entries: <b>{no_orig_count}</b>")
        warning_lines.append("Patching hook offsets can crash the target if the hook wiring is incomplete.")
        sections.append("\n".join(warning_lines))
    sections.append(build_patch_output(parsed_items, override_hex=override_hex))

    await query.edit_message_text(
        "\n\n".join(sections),
        parse_mode=ParseMode.HTML,
        reply_markup=build_keyboard(),
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    LOGGER.exception("Unhandled bot error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Something went wrong while processing that request. Check the logs and try again."
        )


def validate_runtime() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is not set. Export your Telegram bot token before starting the bot."
        )


def main() -> None:
    validate_runtime()
    PARSER.ensure_loaded(force=True)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("health", health_command))
    app.add_handler(CommandHandler("reload", reload_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    app.add_handler(MessageHandler(filters.Document.ALL, process_document))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_error_handler(error_handler)

    stats = PARSER.stats()
    LOGGER.info("Advanced Patch Bot started")
    LOGGER.info("Hook file: %s", HOOK_FILE)
    LOGGER.info("Hooks loaded: %s", stats["hooks"])
    LOGGER.info("Complete hook blocks: %s", stats["complete_hooks"])
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
