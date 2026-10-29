"""Bounded ChatGPT Accessibility walks. Never ask System Events for entire contents."""

from __future__ import annotations

import contextlib
import ctypes
import subprocess
import time
from dataclasses import dataclass

from chatgpt_control_claude.files_list import FileRow

CFTypeRef = ctypes.c_void_p
AXUIElementRef = ctypes.c_void_p
AXError = ctypes.c_int
CFStringRef = ctypes.c_void_p
kAXErrorSuccess = 0
kCFStringEncodingUTF8 = 0x08000100
kAXValueCGPointType = 1
kAXValueCGSizeType = 2

CHATGPT_PROCESS = "ChatGPT"
CLOSE_FILES_TITLE = "Close Files in chat tab"
MORE_TITLE = "More"
VIEW_FILES_TITLE = "View files in chat"
FILES_LIST_TITLE = "Files in chat"
DOWNLOAD_LABELS = frozenset({"download file", "download", "save"})


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


@dataclass(frozen=True, slots=True)
class AXNode:
    ref: int
    role: str
    title: str
    description: str
    x: float
    y: float
    width: float
    height: float

    @property
    def click_point(self) -> tuple[int, int]:
        return (int(self.x + self.width / 2), int(self.y + self.height / 2))

    def matches(self, label: str) -> bool:
        needle = label.casefold()
        return self.title.casefold() == needle or self.description.casefold() == needle


class Accessibility:
    def __init__(self) -> None:
        self._cf = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        self._ax = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        cf = self._cf
        ax = self._ax
        cf.CFStringCreateWithCString.restype = CFStringRef
        cf.CFStringCreateWithCString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint32,
        ]
        cf.CFStringGetLength.restype = ctypes.c_long
        cf.CFStringGetLength.argtypes = [CFStringRef]
        cf.CFStringGetCString.restype = ctypes.c_bool
        cf.CFStringGetCString.argtypes = [
            CFStringRef,
            ctypes.c_char_p,
            ctypes.c_long,
            ctypes.c_uint32,
        ]
        cf.CFGetTypeID.restype = ctypes.c_ulong
        cf.CFGetTypeID.argtypes = [CFTypeRef]
        cf.CFStringGetTypeID.restype = ctypes.c_ulong
        cf.CFArrayGetTypeID.restype = ctypes.c_ulong
        cf.CFArrayGetCount.restype = ctypes.c_long
        cf.CFArrayGetCount.argtypes = [CFTypeRef]
        cf.CFArrayGetValueAtIndex.restype = CFTypeRef
        cf.CFArrayGetValueAtIndex.argtypes = [CFTypeRef, ctypes.c_long]
        ax.AXUIElementCreateApplication.restype = AXUIElementRef
        ax.AXUIElementCreateApplication.argtypes = [ctypes.c_int32]
        ax.AXUIElementCopyAttributeValue.restype = AXError
        ax.AXUIElementCopyAttributeValue.argtypes = [
            AXUIElementRef,
            CFStringRef,
            ctypes.POINTER(CFTypeRef),
        ]
        ax.AXUIElementPerformAction.restype = AXError
        ax.AXUIElementPerformAction.argtypes = [AXUIElementRef, CFStringRef]
        ax.AXValueGetValue.restype = ctypes.c_bool
        ax.AXValueGetValue.argtypes = [CFTypeRef, ctypes.c_uint32, ctypes.c_void_p]

    def _cfstr(self, text: str) -> CFStringRef:
        return self._cf.CFStringCreateWithCString(
            None, text.encode(), kCFStringEncodingUTF8
        )

    def _pystr(self, ref: CFTypeRef | None) -> str:
        if not ref or self._cf.CFGetTypeID(ref) != self._cf.CFStringGetTypeID():
            return ""
        length = self._cf.CFStringGetLength(ref)
        buf = ctypes.create_string_buffer(length * 4 + 8)
        if not self._cf.CFStringGetCString(ref, buf, len(buf), kCFStringEncodingUTF8):
            return ""
        return buf.value.decode("utf-8", "replace")

    def _get(self, element: AXUIElementRef, name: str) -> CFTypeRef | None:
        out = CFTypeRef()
        err = self._ax.AXUIElementCopyAttributeValue(
            element, self._cfstr(name), ctypes.byref(out)
        )
        if err != kAXErrorSuccess:
            return None
        return out

    def perform(self, element: AXUIElementRef, action: str) -> None:
        err = self._ax.AXUIElementPerformAction(element, self._cfstr(action))
        if err != kAXErrorSuccess:
            raise RuntimeError(f"AX action {action} failed with {err}")

    def chatgpt_pid(self) -> int:
        completed = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get unix id of process "ChatGPT"',
            ],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            raise RuntimeError("ChatGPT process is not running")
        return int(completed.stdout.strip())

    def application(self) -> AXUIElementRef:
        return self._ax.AXUIElementCreateApplication(self.chatgpt_pid())

    def front_window(self) -> AXUIElementRef:
        app = self.application()
        windows = self._get(app, "AXWindows")
        if not windows or self._cf.CFGetTypeID(windows) != self._cf.CFArrayGetTypeID():
            raise RuntimeError("ChatGPT has no AX windows")
        if self._cf.CFArrayGetCount(windows) < 1:
            raise RuntimeError("ChatGPT has no AX windows")
        return self._cf.CFArrayGetValueAtIndex(windows, 0)

    def _point(self, element: AXUIElementRef) -> tuple[float, float]:
        value = self._get(element, "AXPosition")
        if not value:
            return (0.0, 0.0)
        point = CGPoint()
        if not self._ax.AXValueGetValue(
            value, kAXValueCGPointType, ctypes.byref(point)
        ):
            return (0.0, 0.0)
        return (point.x, point.y)

    def _size(self, element: AXUIElementRef) -> tuple[float, float]:
        value = self._get(element, "AXSize")
        if not value:
            return (0.0, 0.0)
        size = CGSize()
        if not self._ax.AXValueGetValue(value, kAXValueCGSizeType, ctypes.byref(size)):
            return (0.0, 0.0)
        return (size.width, size.height)

    def describe(self, element: AXUIElementRef) -> AXNode:
        x, y = self._point(element)
        width, height = self._size(element)
        return AXNode(
            ref=int(element) if element else 0,
            role=self._pystr(self._get(element, "AXRole")),
            title=self._pystr(self._get(element, "AXTitle")),
            description=self._pystr(self._get(element, "AXDescription")),
            x=x,
            y=y,
            width=width,
            height=height,
        )

    def walk(
        self,
        root: AXUIElementRef,
        *,
        max_nodes: int = 900,
        max_depth: int = 24,
        max_children: int = 80,
    ) -> list[tuple[AXUIElementRef, AXNode, int]]:
        queue: list[tuple[AXUIElementRef, int]] = [(root, 0)]
        found: list[tuple[AXUIElementRef, AXNode, int]] = []
        seen = 0
        while queue and seen < max_nodes:
            element, depth = queue.pop(0)
            seen += 1
            node = self.describe(element)
            found.append((element, node, depth))
            if depth >= max_depth:
                continue
            children = self._get(element, "AXChildren")
            if (
                not children
                or self._cf.CFGetTypeID(children) != self._cf.CFArrayGetTypeID()
            ):
                continue
            count = min(int(self._cf.CFArrayGetCount(children)), max_children)
            for index in range(count):
                queue.append(
                    (self._cf.CFArrayGetValueAtIndex(children, index), depth + 1)
                )
        return found

    def find_labeled(
        self, label: str, *, roles: frozenset[str] | None = None
    ) -> tuple[AXUIElementRef, AXNode] | None:
        for element, node, _depth in self.walk(self.front_window()):
            if roles and node.role not in roles:
                continue
            if node.matches(label):
                return (element, node)
        return None


def click_screen(x: int, y: int) -> None:
    """Post a real HID left-click. System Events `click at` misses Electron chrome."""
    cg = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    )
    k_mouse_down = 1
    k_mouse_up = 2
    k_hid_tap = 0
    k_left = 0
    cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    cg.CGEventCreateMouseEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        CGPoint,
        ctypes.c_uint32,
    ]
    cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    cf = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    point = CGPoint(x, y)
    down = cg.CGEventCreateMouseEvent(None, k_mouse_down, point, k_left)
    up = cg.CGEventCreateMouseEvent(None, k_mouse_up, point, k_left)
    if not down or not up:
        raise RuntimeError(f"could not create mouse events for ({x},{y})")
    cg.CGEventPost(k_hid_tap, down)
    cg.CGEventPost(k_hid_tap, up)
    cf.CFRelease(down)
    cf.CFRelease(up)
    time.sleep(0.12)


def files_list_open(ax: Accessibility) -> bool:
    if ax.find_labeled(CLOSE_FILES_TITLE, roles=frozenset({"AXButton"})) is not None:
        return True
    return ax.find_labeled(FILES_LIST_TITLE, roles=frozenset({"AXList"})) is not None


def close_files_pane(ax: Accessibility, *, timeout: float = 4.0) -> None:
    hit = ax.find_labeled(CLOSE_FILES_TITLE, roles=frozenset({"AXButton"}))
    if hit is None:
        return
    element, node = hit
    try:
        ax.perform(element, "AXPress")
    except RuntimeError:
        click_screen(*node.click_point)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ax.find_labeled(CLOSE_FILES_TITLE, roles=frozenset({"AXButton"})) is None:
            return
        time.sleep(0.15)
    click_screen(*node.click_point)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ax.find_labeled(CLOSE_FILES_TITLE, roles=frozenset({"AXButton"})) is None:
            return
        time.sleep(0.15)
    raise RuntimeError("Files in chat stayed open after Close")


def open_files_pane(ax: Accessibility, *, timeout: float = 6.0) -> None:
    more = ax.find_labeled(MORE_TITLE, roles=frozenset({"AXPopUpButton", "AXButton"}))
    if more is None:
        raise RuntimeError("ChatGPT More control was not in the AX tree")
    ax.perform(more[0], "AXShowMenu")
    time.sleep(0.35)
    view = ax.find_labeled(
        VIEW_FILES_TITLE, roles=frozenset({"AXMenuItem", "AXButton"})
    )
    if view is None:
        raise RuntimeError("View files in chat was not in the More menu")
    ax.perform(view[0], "AXPress")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if files_list_open(ax):
            return
        time.sleep(0.15)
    raise RuntimeError("View files in chat did not expose AXList Files in chat")


def _files_container(ax: Accessibility) -> AXUIElementRef | None:
    window = ax.front_window()
    group: AXUIElementRef | None = None
    for element, node, _depth in ax.walk(window):
        if node.matches(FILES_LIST_TITLE) and node.role == "AXList":
            return element
        if node.matches(FILES_LIST_TITLE) and node.role == "AXGroup":
            group = element
    return group


def scroll_files_list_to_end(ax: Accessibility) -> None:
    """Newest files sit at the bottom; reopening the pane resets to the top."""
    container = _files_container(ax)
    if container is None:
        return
    last_button = None
    for element, node, _depth in ax.walk(container, max_nodes=200, max_depth=8):
        if node.role == "AXButton" and node.title:
            last_button = element
    if last_button is None:
        return
    try:
        ax.perform(last_button, "AXScrollToVisible")
    except RuntimeError:
        return
    time.sleep(0.35)


def list_file_rows(ax: Accessibility, *, timeout: float = 4.0) -> list[FileRow]:
    deadline = time.monotonic() + timeout
    last_error = "AX Files in chat container is missing"
    while time.monotonic() < deadline:
        container = _files_container(ax)
        if container is None:
            time.sleep(0.15)
            continue
        rows: list[FileRow] = []
        for _element, node, _depth in ax.walk(container, max_nodes=200, max_depth=8):
            if node.role != "AXButton" or not node.title:
                continue
            rows.append(FileRow(name=node.title, y=node.y, x=node.x))
        if rows:
            return rows
        last_error = "Files in chat opened without file rows"
        time.sleep(0.15)
    raise RuntimeError(last_error)


def activate_named_file(ax: Accessibility, filename: str) -> None:
    container = _files_container(ax)
    if container is None:
        raise RuntimeError("AX Files in chat container is missing")
    for element, node, _depth in ax.walk(container, max_nodes=200, max_depth=8):
        if node.role != "AXButton" or node.title != filename:
            continue
        with contextlib.suppress(RuntimeError):
            ax.perform(element, "AXScrollToVisible")
        time.sleep(0.25)
        moved = ax.describe(element)
        click_screen(*moved.click_point)
        return
    raise RuntimeError(f"file row {filename!r} was not in the Files in chat list")


def find_download_control(ax: Accessibility) -> tuple[AXUIElementRef, AXNode] | None:
    """Preview toolbar button titled Download, not the chat's Download file link."""
    for element, node, _depth in ax.walk(
        ax.front_window(), max_nodes=1500, max_depth=28
    ):
        if node.role == "AXButton" and node.title.casefold() == "download":
            return (element, node)
    return None


def composer_action_buttons(ax: Accessibility) -> list[AXNode]:
    window = ax.front_window()
    frame = ax.describe(window)
    cutoff = frame.y + frame.height - 140
    found: list[AXNode] = []
    for _element, node, _depth in ax.walk(window, max_nodes=2500, max_depth=30):
        if node.role == "AXButton" and node.y >= cutoff:
            found.append(node)
    return found


def wait_for_composer_send(ax: Accessibility, *, timeout: float = 600.0) -> None:
    """Block until the stop square is gone and the Send arrow is back."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        titles = {node.title.casefold() for node in composer_action_buttons(ax)}
        if "send" in titles and "stop" not in titles:
            return
        time.sleep(0.4)
    raise RuntimeError("composer Send button did not return before timeout")


def wait_for_download_control(
    ax: Accessibility, *, timeout: float = 15.0
) -> tuple[AXUIElementRef, AXNode]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hit = find_download_control(ax)
        if hit is not None:
            return hit
        time.sleep(0.2)
    raise RuntimeError("Download button did not appear in the file preview")
