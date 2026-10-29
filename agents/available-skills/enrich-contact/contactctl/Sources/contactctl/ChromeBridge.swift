import Foundation

/// Drives the user's running Chrome (with their Facebook login cookies) via
/// AppleScript to extract a Facebook profile photo. The recipe — taught by the
/// owner — is: open the profile, find the `<h1>` that matches the profile name,
/// click the `<a aria-label="<that name>">` to open the photo viewer, then read
/// `<img data-visualcompletion="media-vc-image">.src`. Stashing that src into
/// `document.title` works around the in-browser tooling's auth-token redactor;
/// AppleScript reads it back as a plain string.
///
/// Permissions: requires "Google Chrome" automation access (System Settings ▸
/// Privacy & Security ▸ Automation ▸ contactctl → Google Chrome). First call
/// triggers the prompt.
enum ChromeBridge {
  /// Opens `facebookURL` in a new Chrome tab and returns the signed CDN URL
  /// of the appropriate image. Three URL shapes are handled:
  ///   1. Profile page (`facebook.com/<user>`) — click the profile pic, then
  ///      grab the photo viewer's image.
  ///   2. Photo viewer (`/photo.php?fbid=…` or `/photo/?fbid=…`) — the viewer
  ///      mounts directly; we just read its image. Use this to force a
  ///      specific photo (e.g. an older profile picture).
  ///   3. Direct CDN URL (`*.fbcdn.net/...`) — skip Chrome entirely and
  ///      return the URL as-is (no tab is opened).
  /// Everything from opening the tab to reading the image and closing it
  /// runs inside a single AppleScript invocation, so the tab reference can
  /// never get lost to a racing MCP/extension reordering windows.
  static func extractPhotoURL(from facebookURL: String) throws -> String {
    if facebookURL.contains("fbcdn") || facebookURL.contains("scontent") {
      return facebookURL
    }
    let isPhotoViewer = facebookURL.contains("/photo.php") || facebookURL.contains("/photo/")
    let script = singleShotScript(url: facebookURL, isPhotoViewer: isPhotoViewer)
    let raw = try runAppleScript(script).trimmingCharacters(in: .whitespacesAndNewlines)
    if raw.hasPrefix("ERR:") {
      throw ContactError("chrome scrape failed: \(String(raw.dropFirst(4)))")
    }
    guard raw.hasPrefix("https://") else {
      throw ContactError("unexpected Chrome response: \(raw)")
    }
    return raw
  }

  private static func singleShotScript(url: String, isPhotoViewer: Bool) -> String {
    let clickSection =
      isPhotoViewer
      ? ""
      : """
              set clickResult to execute newTab javascript "\(escape(clickProfileJS))"
              if clickResult does not start with "OK:" then
                  close newTab
                  return "ERR:" & clickResult
              end if
              delay 2.5

      """
    return """
      tell application "Google Chrome"
          activate
          if (count of windows) = 0 then make new window
          set newTab to make new tab at end of tabs of front window with properties {URL:"\(escape(url))"}
          repeat with attempt from 1 to 150
              if loading of newTab is false then exit repeat
              delay 0.2
          end repeat
          delay 1.5
      \(clickSection)
          set imgUrl to (execute newTab javascript "\(escape(grabImageJS))") as string
          close newTab
          if imgUrl does not start with "https://" then
              return "ERR:" & imgUrl
          end if
          return imgUrl
      end tell
      """
  }

  private static func runAppleScript(_ script: String) throws -> String {
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
    task.arguments = ["-e", script]
    let stdout = Pipe()
    let stderr = Pipe()
    task.standardOutput = stdout
    task.standardError = stderr
    try task.run()
    task.waitUntilExit()
    guard task.terminationStatus == 0 else {
      let err =
        String(data: stderr.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? "unknown error"
      // Surface the most common one-time setup errors with the actual
      // remediation, not just Chrome's raw stderr.
      if err.contains("Executing JavaScript through AppleScript is turned off") {
        throw ContactError(
          "Chrome's 'Allow JavaScript from Apple Events' is off. Enable it once: in Chrome's menu bar, View → Developer → Allow JavaScript from Apple Events, then retry."
        )
      }
      if err.contains("Not authorized") || err.contains("1743") {
        throw ContactError(
          "Chrome automation permission not granted. Grant it in System Settings → Privacy & Security → Automation → contactctl → Google Chrome, then retry."
        )
      }
      throw ContactError("chrome automation failed: \(err)")
    }
    return String(data: stdout.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
  }

  /// AppleScript string escaping — backslash first, then double-quotes.
  private static func escape(_ raw: String) -> String {
    raw.replacingOccurrences(of: "\\", with: "\\\\")
      .replacingOccurrences(of: "\"", with: "\\\"")
  }

  // MARK: JS payloads

  /// Filter out the messenger-sidebar "Chats" h1; the profile name is the
  /// other one. Then click the matching aria-labeled link to open the photo
  /// viewer. We return a sentinel string so the caller can distinguish each
  /// failure mode.
  private static let clickProfileJS = """
    (function() {
        var h1s = Array.from(document.querySelectorAll('h1')).map(function(h){return h.innerText.trim();}).filter(function(t){return t.length > 0 && t !== 'Chats';});
        var name = h1s[0];
        if (!name) return 'NO_H1';
        var link = Array.from(document.querySelectorAll('a[role=\"link\"]')).find(function(a){return a.getAttribute('aria-label') === name;});
        if (!link) return 'NO_LINK:' + name;
        link.click();
        return 'OK:' + name;
    })()
    """

  /// `data-visualcompletion="media-vc-image"` is Facebook's own marker for
  /// the canonical primary image of any media viewer.
  private static let grabImageJS = """
    (function() {
        var img = document.querySelector('img[data-visualcompletion=\"media-vc-image\"]');
        return img ? img.src : 'NO_IMG';
    })()
    """
}

/// Downloads a remote photo to disk by shelling to `curl`. The Facebook CDN
/// signs URLs with `_nc_oc` / `_nc_ohc` / `oh` tokens that don't require any
/// cookie context — they're per-URL signatures — so `curl` alone works.
enum PhotoDownloader {
  static func download(from urlString: String, to path: String) throws {
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/bin/curl")
    task.arguments = ["-sLf", "-A", "Mozilla/5.0", "-o", path, urlString]
    let stderr = Pipe()
    task.standardError = stderr
    try task.run()
    task.waitUntilExit()
    guard task.terminationStatus == 0 else {
      let err =
        String(data: stderr.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? "curl failed"
      throw ContactError("download failed: \(err)")
    }
  }
}
