"""Kitty custom tab bar: equal-width tabs that fill the bar.

Kitty measures each tab and then shrinks it to that width, so a slant style
with a short title becomes a tiny peak and the rest of the bar stays empty.
The layout pass reports a 1-cell width so kitty does not reserve space. The
draw pass paints equal shares of the whole bar, with a fixed-width + button.
"""

from configparser import ConfigParser
from os.path import basename
from pathlib import Path
import re

from kitty.fast_data_types import (
    Screen,
    get_boss,
    get_options,
    get_window_being_dragged,
    split_into_graphemes,
    wcswidth,
)
from kitty.tab_bar import DrawData, ExtraData, TabBarData, apply_title_template, as_rgb
from kitty.utils import log_error

ICONS_CONF = Path(__file__).with_name("tab-icons.conf")

AGENT_PROCESSES = frozenset({"grok", "claude", "codex", "nvim"})
TITLE_SEP = " - "
ELLIPSIS = "…"
MAX_SPINNER_LEN = 2
THINKING = "Thinking"
RUNNING_PREFIX = "Running"
PLUS_WIDTH = 3
_SGR = re.compile(r"\x1b\[[0-9;:]*m")


def _is_status_segment(part: str) -> bool:
    text = part.strip()
    return (
        len(text) <= MAX_SPINNER_LEN
        or text == THINKING
        or text.startswith(RUNNING_PREFIX)
    )


def _is_user_title(title: str) -> bool:
    return (
        bool(title)
        and "/" not in title
        and TITLE_SEP not in title
        and not title.startswith(ELLIPSIS)
    )


def _task_name(title: str) -> str:
    parts = [p.strip() for p in title.split(TITLE_SEP) if p.strip()]
    if parts and parts[-1].lower() in AGENT_PROCESSES:
        parts = parts[:-1]
    if parts and _is_status_segment(parts[0]):
        parts = parts[1:]
    return parts[-1] if parts else ""


def _cwd_or_fallback(tab: object, title: str, exe: str) -> str:
    wd = str(getattr(tab, "active_wd", "") or "")
    if wd:
        name = basename(wd.rstrip("/"))
        if name:
            return name
    return title or exe


def _parse_glyph(value: str) -> str:
    text = value.strip()
    if text.lower().startswith("u+"):
        return chr(int(text[2:], 16))
    if text and len(text) <= 2 and not text.isascii():
        return text
    return ""


def _load_icon_maps(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    parser = ConfigParser(interpolation=None, inline_comment_prefixes=("#",))
    parser.optionxform = str
    if not parser.read(path, encoding="utf-8"):
        print(f"tab_bar.py: missing {path}", flush=True)
        return {}, {}
    icons = (
        {name.lower(): _parse_glyph(raw) for name, raw in parser.items("icons")}
        if parser.has_section("icons")
        else {}
    )
    exe_map = (
        {name.lower(): raw.strip() for name, raw in parser.items("exe")}
        if parser.has_section("exe")
        else {}
    )
    return exe_map, {name: glyph for name, glyph in icons.items() if glyph}


EXE_MAP, ICONS = _load_icon_maps(ICONS_CONF)


def _without_exe_word(label: str, exe: str) -> str:
    if not exe or not label:
        return label
    prefix = f"{exe} "
    if label.lower().startswith(prefix):
        return label[len(prefix) :].lstrip()
    return label


def _exe_stems(exe: str) -> list[str]:
    stems: list[str] = []
    name = exe.lower()
    for stem in (name, name.rstrip("0123456789.")):
        if stem and stem not in stems:
            stems.append(stem)
    return stems


def _resolve_ref(ref: str) -> str:
    glyph = _parse_glyph(ref)
    if glyph:
        return glyph
    return ICONS.get(ref.lower(), "")


def _icon_for(exe: str) -> str:
    if not exe:
        return ""
    for stem in _exe_stems(exe):
        if stem in EXE_MAP:
            glyph = _resolve_ref(EXE_MAP[stem])
            if glyph:
                return glyph
        if stem in ICONS:
            return ICONS[stem]
    return ""


def _with_icon(label: str, exe: str) -> str:
    identity = _without_exe_word(label, exe)
    icon = _icon_for(exe)
    if not icon:
        return identity
    if identity.startswith(icon):
        return identity
    if identity:
        return f"{icon} {identity}"
    return icon


def draw_title(data: dict[str, object]) -> str:
    title = str(data.get("title") or "")
    tab = data["tab"]
    exe = basename(str(getattr(tab, "active_exe", "") or "")).lower()
    if _is_user_title(title):
        identity = title
    elif TITLE_SEP in title:
        identity = _task_name(title) or _cwd_or_fallback(tab, title, exe)
    else:
        identity = _cwd_or_fallback(tab, title, exe)
    return _with_icon(identity, exe)


def _plain(text: str) -> str:
    return _SGR.sub("", text)


def _truncate(text: str, width: int) -> str:
    if width <= 0 or not text:
        return ""
    if wcswidth(text) <= width:
        return text
    ellipsis_width = max(1, wcswidth(ELLIPSIS))
    if width < ellipsis_width:
        return ""
    if width == ellipsis_width:
        return ELLIPSIS
    keep = width - ellipsis_width
    out: list[str] = []
    used = 0
    for grapheme in split_into_graphemes(text):
        grapheme_width = wcswidth(grapheme)
        if grapheme_width < 0 or used + grapheme_width > keep:
            break
        out.append(grapheme)
        used += grapheme_width
    return "".join(out) + ELLIPSIS


def _slot_widths(columns: int, n_real: int, plus_width: int) -> tuple[int, list[int]]:
    """Equal shares of the bar. Sum of shares plus the + button equals columns."""
    if n_real <= 0:
        return min(plus_width, max(0, columns)), []
    plus_width = min(plus_width, max(0, columns - n_real))
    budget = columns - plus_width
    if budget < n_real:
        return plus_width, [1 if i < budget else 0 for i in range(n_real)]
    base, remainder = divmod(budget, n_real)
    return plus_width, [base + (1 if i < remainder else 0) for i in range(n_real)]


def _real_tab_count(tab: TabBarData) -> int:
    try:
        boss = get_boss()
        manager = boss.os_window_map.get(tab.os_window_id)
        if manager is None:
            return 0
        return len(tuple(manager.tabs_to_be_shown_in_tab_bar))
    except Exception as error:
        log_error(f"tab_bar.py: tab count failed: {error}")
        return 0


def _plus_width() -> int:
    try:
        dragging = bool(get_window_being_dragged()[1])
        if get_options().tab_bar_show_new_tab_button or dragging:
            return PLUS_WIDTH
    except Exception as error:
        log_error(f"tab_bar.py: plus button check failed: {error}")
    return 0


def _title_for(draw_data: DrawData, tab: TabBarData, index: int, width: int) -> str:
    if tab.tab_id < 0:
        return tab.title or "+"
    return _plain(apply_title_template(draw_data, tab, index, width))


def _paint(screen: Screen, text: str, width: int) -> None:
    if width <= 0:
        return
    fitted = _truncate(text, width)
    drawn = wcswidth(fitted) if fitted else 0
    if fitted:
        screen.draw(fitted)
    pad = width - drawn
    if pad > 0:
        screen.draw(" " * pad)


def _draw_gap(screen: Screen, draw_data: DrawData) -> None:
    screen.cursor.bg = as_rgb(int(draw_data.default_bg))
    screen.draw(" ")


def _draw_plus(screen: Screen, draw_data: DrawData, before: int) -> int:
    room = max(0, screen.columns - before)
    width = min(PLUS_WIDTH, room)
    if width <= 0:
        return before
    screen.cursor.x = before
    screen.cursor.bg = as_rgb(int(draw_data.default_bg))
    screen.cursor.fg = as_rgb(int(draw_data.inactive_fg))
    label = "+" if width < 3 else " + "
    _paint(screen, label, width)
    return screen.cursor.x


def _draw_real(
    draw_data: DrawData,
    screen: Screen,
    tab: TabBarData,
    before: int,
    index: int,
    width: int,
    has_gap: bool,
) -> int:
    room = max(0, screen.columns - before)
    width = min(width, room)
    if width <= 0:
        return before
    screen.cursor.x = before
    gap = 1 if has_gap and width >= 2 else 0
    content = width - gap
    if content >= 3:
        screen.draw(" ")
        _paint(screen, _title_for(draw_data, tab, index, content - 1), content - 1)
    else:
        _paint(screen, _title_for(draw_data, tab, index, content), content)
    if gap:
        _draw_gap(screen, draw_data)
    return screen.cursor.x


def draw_tab(
    draw_data: DrawData,
    screen: Screen,
    tab: TabBarData,
    before: int,
    max_tab_length: int,
    index: int,
    is_last: bool,
    extra_data: ExtraData,
) -> int:
    if extra_data.for_layout:
        screen.cursor.x = before + 1
        return screen.cursor.x

    if tab.tab_id < 0:
        return _draw_plus(screen, draw_data, before)

    n_real = _real_tab_count(tab)
    if n_real <= 0:
        room = max(0, screen.columns - before)
        width = room if is_last else min(max(1, max_tab_length), room)
        return _draw_real(draw_data, screen, tab, before, index, width, not is_last)

    plus_width, widths = _slot_widths(screen.columns, n_real, _plus_width())
    slot = widths[index - 1] if 1 <= index <= len(widths) else 0
    plus_follows = plus_width > 0
    has_gap = slot >= 2 and (index != n_real or plus_follows)
    return _draw_real(draw_data, screen, tab, before, index, slot, has_gap)
