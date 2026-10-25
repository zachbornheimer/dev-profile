import Contacts
import Foundation

/// Maps argv to `ContactStore` calls and prints JSON to stdout.
/// Every command prints a single JSON value so callers (the enrichment
/// subagents) can parse the result without scraping prose.
enum Commands {
  static func run(_ command: String, _ args: [String], store: ContactStore) throws {
    switch command {
    case "get": try get(args, store)
    case "tag": try tag(args, store)
    case "untag": try untag(args, store)
    case "url": try url(args, store)
    case "email": try email(args, store)
    case "photo": try photo(args, store)
    case "rmphoto": try rmphoto(args, store)
    case "stamp": try stamp(args, store)
    case "reviewed": try reviewed(args, store)
    case "unreviewed": try unreviewed(args, store)
    case "find": try find(args, store)
    case "members": try members(args, store)
    case "get-profile-picture": try getProfilePicture(args)
    case "photo-audit": try photoAudit(store)
    default: throw ContactError("unknown command '\(command)' — run with no arguments for usage")
    }
  }

  /// Lists every contact's photo state, classified into missing / tiny /
  /// small / ok. "Tiny" (≤192px) covers the legacy iCloud thumbnails that
  /// look blurry on a modern display; "small" (193-400px) is borderline.
  private static func photoAudit(_ store: ContactStore) throws {
    let rows = try store.auditPhotos()
    func bucket(_ w: Int?, _ h: Int?) -> String {
      guard let w, let h, w > 0, h > 0 else { return "missing" }
      let min = Swift.min(w, h)
      if min <= 192 { return "tiny" }
      if min <= 400 { return "small" }
      return "ok"
    }
    let serialized = rows.map { row -> [String: Any] in
      let dim: Any = (row.width.map { "\($0)x\(row.height ?? 0)" } ?? "")
      return [
        "name": row.name,
        "id": row.id,
        "org": row.org,
        "dim": dim,
        "bucket": bucket(row.width, row.height),
      ]
    }
    let counts = Dictionary(grouping: serialized, by: { $0["bucket"] as? String ?? "?" })
      .mapValues { $0.count }
    Output.print([
      "total": rows.count,
      "counts": counts,
      "contacts": serialized,
    ])
  }

  /// Drives Chrome to grab a Facebook photo and saves it to disk. Doesn't
  /// touch any contact — that's the caller's next step. The input URL can be
  /// a profile page (we'll click the profile pic), a photo viewer (we go
  /// straight to that specific photo — use this to force an older or
  /// non-current image), or a direct CDN URL (we skip Chrome and curl it).
  private static func getProfilePicture(_ args: [String]) throws {
    guard let url = args.first, !url.isEmpty else {
      throw ContactError("usage: get-profile-picture <facebook URL or image URL> [outputPath]")
    }
    let isFacebook =
      url.contains("facebook.com") || url.contains("fbcdn") || url.contains("scontent")
    guard isFacebook else {
      throw ContactError("only Facebook URLs are supported; got: \(url)")
    }
    let photoURL = try ChromeBridge.extractPhotoURL(from: url)
    let outPath = args.count > 1 ? args[1] : defaultOutputPath(for: url)
    try PhotoDownloader.download(from: photoURL, to: outPath)
    Output.print([
      "ok": true,
      "source_url": photoURL,
      "saved_to": outPath,
    ])
  }

  /// `https://www.facebook.com/mike.bassett.562` → `/tmp/mike_bassett_562_profile.jpg`.
  /// Keeps unrelated downloads from colliding while staying predictable.
  private static func defaultOutputPath(for fbURL: String) -> String {
    let slug =
      fbURL
      .replacingOccurrences(of: "https://", with: "")
      .replacingOccurrences(of: "http://", with: "")
      .replacingOccurrences(of: "www.facebook.com/", with: "")
      .replacingOccurrences(of: "facebook.com/", with: "")
      .split(whereSeparator: { ["/", "?", "&", " "].contains($0) })
      .first.map(String.init) ?? "fb"
    let safe = slug.replacingOccurrences(of: ".", with: "_")
    return "/tmp/\(safe)_profile.jpg"
  }

  private static func members(_ args: [String], _ store: ContactStore) throws {
    guard let group = args.first, !group.isEmpty else { throw ContactError("members <group>") }
    let rows = try store.members(of: group).map { m -> [String: Any] in
      let reviewed: Any =
        m.reviewed.map {
          String(format: "%04d-%02d-%02d", $0.year ?? 0, $0.month ?? 0, $0.day ?? 0)
        } ?? NSNull()
      return ["name": m.name, "id": m.id, "image": m.hasImage, "reviewed": reviewed]
    }
    Output.print(["group": group, "count": rows.count, "members": rows])
  }

  private static func id(_ args: [String], _ command: String) throws -> String {
    guard let id = args.first, !id.isEmpty else {
      throw ContactError("\(command) needs a contact id")
    }
    return id
  }

  // MARK: Read

  private static func get(_ args: [String], _ store: ContactStore) throws {
    let contact = try store.contact(try id(args, "get"), keys: detailKeys)
    Output.print(CardEncoder.json(contact, groups: try store.groupNames(contact.identifier)))
  }

  private static func reviewed(_ args: [String], _ store: ContactStore) throws {
    let date = try store.reviewedOn(try id(args, "reviewed"))
    let value: Any = date.map(format) ?? NSNull()
    Output.print(["reviewed": value])
  }

  private static func unreviewed(_ args: [String], _ store: ContactStore) throws {
    guard let letter = args.first?.first else {
      throw ContactError("unreviewed needs a letter, e.g. 'unreviewed G'")
    }
    let rows = try store.unreviewed(initial: letter).map {
      ["name": $0.name, "id": $0.id, "image": $0.hasImage, "org": $0.org] as [String: Any]
    }
    Output.print(["count": rows.count, "contacts": rows])
  }

  private static func find(_ args: [String], _ store: ContactStore) throws {
    guard let query = args.first else { throw ContactError("find needs a name") }
    Output.print(["matches": try store.find(name: query).map { ["name": $0.name, "id": $0.id] }])
  }

  // MARK: Write

  private static func tag(_ args: [String], _ store: ContactStore) throws {
    let group = try requireSecond(args, "tag <id> <group>")
    try store.addToGroup(try id(args, "tag"), group)
    Output.print(["ok": true, "tagged": group])
  }

  private static func untag(_ args: [String], _ store: ContactStore) throws {
    let group = try requireSecond(args, "untag <id> <group>")
    try store.removeFromGroup(try id(args, "untag"), group)
    Output.print(["ok": true, "untagged": group])
  }

  private static func url(_ args: [String], _ store: ContactStore) throws {
    let (label, value) = try requireLabelValue(args, "url <id> <label> <value>")
    try store.addURL(try id(args, "url"), label: label, value: value)
    Output.print(["ok": true, "url": value])
  }

  private static func email(_ args: [String], _ store: ContactStore) throws {
    let (label, value) = try requireLabelValue(args, "email <id> <label> <value>")
    try store.addEmail(try id(args, "email"), label: label, value: value)
    Output.print(["ok": true, "email": value])
  }

  private static func photo(_ args: [String], _ store: ContactStore) throws {
    let path = try requireSecond(args, "photo <id> <imagePath>")
    let contactID = try id(args, "photo")
    let outcome = try store.setImage(contactID, fromFile: path)
    let persisted = try store.hasImage(contactID)
    var result: [String: Any] = ["ok": persisted, "image": persisted, "via": outcome.rawValue]
    if outcome != .native && !persisted {
      result["warning"] =
        "iCloud held this record locked; AppleScript fallback did not persist the image. Retry after the operator confirms iCloud has finished syncing."
    }
    Output.print(result)
  }

  private static func rmphoto(_ args: [String], _ store: ContactStore) throws {
    let contactID = try id(args, "rmphoto")
    try store.clearImage(contactID)
    Output.print(["ok": true, "image": try store.hasImage(contactID)])
  }

  private static func stamp(_ args: [String], _ store: ContactStore) throws {
    let contactID = try id(args, "stamp")
    let date = args.count > 1 ? try parse(date: args[1]) : today()
    try store.stampReviewed(contactID, on: date)
    Output.print(["ok": true, "reviewed": format(date)])
  }

  // MARK: Argument + date helpers

  private static func requireSecond(_ args: [String], _ usage: String) throws -> String {
    guard args.count > 1, !args[1].isEmpty else { throw ContactError("usage: \(usage)") }
    return args[1]
  }

  private static func requireLabelValue(_ args: [String], _ usage: String) throws -> (
    String, String
  ) {
    guard args.count > 2, !args[1].isEmpty, !args[2].isEmpty else {
      throw ContactError("usage: \(usage)")
    }
    return (args[1], args[2])
  }

  private static func today() -> DateComponents {
    Calendar.current.dateComponents([.year, .month, .day], from: Date())
  }

  private static func parse(date text: String) throws -> DateComponents {
    let parts = text.split(separator: "-").compactMap { Int($0) }
    guard parts.count == 3 else { throw ContactError("date must be YYYY-MM-DD, got '\(text)'") }
    return DateComponents(year: parts[0], month: parts[1], day: parts[2])
  }

  private static func format(_ date: DateComponents) -> String {
    String(format: "%04d-%02d-%02d", date.year ?? 0, date.month ?? 0, date.day ?? 0)
  }
}
