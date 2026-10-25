import Foundation

/// AppleScript bridge — the escape hatch for the small set of cards whose
/// CoreData record is held locked by iCloud sync (`NSCocoaErrorDomain 134092`).
/// Their AppleScript path uses a different code path and writes anyway.
///
/// Treat this as a fallback for `CNSaveRequest`, not a primary API. The native
/// framework is always tried first; we only fall back when the conflict error
/// surfaces. A few writes (notably image data) silently no-op via AppleScript
/// on these locked records — the caller for those gets a warning, not silence.
enum AppleScriptFallback {
  /// `<uuid>:ABPerson` is the form the macOS Contacts AppleEvents layer expects.
  private static func personRef(_ id: String) -> String {
    id.contains(":ABPerson") ? id : id + ":ABPerson"
  }

  static func tag(_ id: String, _ groupName: String) throws {
    let safe = groupName.replacingOccurrences(of: "\"", with: "\\\"")
    try run(
      """
      tell application "Contacts"
          if not (exists group "\(safe)") then make new group with properties {name:"\(safe)"}
          add (person id "\(personRef(id))") to group "\(safe)"
          save
      end tell
      """)
  }

  static func untag(_ id: String, _ groupName: String) throws {
    let safe = groupName.replacingOccurrences(of: "\"", with: "\\\"")
    try run(
      """
      tell application "Contacts"
          remove (person id "\(personRef(id))") from group "\(safe)"
          save
      end tell
      """)
  }

  static func stamp(_ id: String, on date: DateComponents) throws {
    // AppleScript records the date by calendar value, not components, so we
    // build today's date inside the script and trust the local timezone —
    // matches the CN path's `DateComponents.day` semantics.
    let day = date.day ?? 1
    let month = date.month ?? 1
    let year = date.year ?? 2000
    try run(
      """
      tell application "Contacts"
          set p to person id "\(personRef(id))"
          set dt to (current date)
          set year of dt to \(year)
          set month of dt to \(month)
          set day of dt to \(day)
          set time of dt to 0
          set found to false
          repeat with cd in custom dates of p
              if label of cd is "auto-reviewed" then
                  set value of cd to dt
                  set found to true
              end if
          end repeat
          if not found then
              make new custom date at end of custom dates of p with properties {label:"auto-reviewed", value:dt}
          end if
          save
      end tell
      """)
  }

  static func addURL(_ id: String, label: String, value: String) throws {
    let safeLabel = label.replacingOccurrences(of: "\"", with: "\\\"")
    let safeValue = value.replacingOccurrences(of: "\"", with: "\\\"")
    try run(
      """
      tell application "Contacts"
          set p to person id "\(personRef(id))"
          set found to false
          repeat with u in urls of p
              if (value of u) is "\(safeValue)" then set found to true
          end repeat
          if not found then
              make new url at end of urls of p with properties {label:"\(safeLabel)", value:"\(safeValue)"}
          end if
          save
      end tell
      """)
  }

  static func addEmail(_ id: String, label: String, value: String) throws {
    let safeLabel = label.replacingOccurrences(of: "\"", with: "\\\"")
    let safeValue = value.replacingOccurrences(of: "\"", with: "\\\"")
    try run(
      """
      tell application "Contacts"
          set p to person id "\(personRef(id))"
          set found to false
          repeat with em in emails of p
              if (value of em) is "\(safeValue)" then set found to true
          end repeat
          if not found then
              make new email at end of emails of p with properties {label:"\(safeLabel)", value:"\(safeValue)"}
          end if
          save
      end tell
      """)
  }

  static func setImage(_ id: String, fromFile path: String) throws {
    let safePath = path.replacingOccurrences(of: "\"", with: "\\\"")
    try run(
      """
      tell application "Contacts"
          set p to person id "\(personRef(id))"
          set image of p to (read (POSIX file "\(safePath)") as JPEG picture)
          save
      end tell
      """)
  }

  static func clearImage(_ id: String) throws {
    try run(
      """
      tell application "Contacts"
          set p to person id "\(personRef(id))"
          set image of p to missing value
          save
      end tell
      """)
  }

  private static func run(_ script: String) throws {
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
    task.arguments = ["-e", script]
    let stderr = Pipe()
    task.standardError = stderr
    task.standardOutput = Pipe()
    try task.run()
    task.waitUntilExit()
    guard task.terminationStatus == 0 else {
      let err =
        String(data: stderr.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? "unknown error"
      throw ContactError("applescript fallback failed: \(err)")
    }
  }
}
