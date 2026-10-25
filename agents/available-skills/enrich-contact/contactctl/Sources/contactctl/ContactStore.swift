import Contacts
import Foundation

/// The single boundary to the macOS Contacts framework.
///
/// Every Contacts read or write in this tool goes through here, so the rest of
/// the program never touches `CNContactStore` directly. Writes use
/// `CNSaveRequest`, which persists reliably — none of the AppleEvents-era
/// failure modes (image coercion that silently drops, custom-date deletes that
/// throw `-10000`, automation permission that evaporates) apply.
final class ContactStore {
  private let store = CNContactStore()

  /// The custom-date label that records when the main thread last reviewed a card.
  static let reviewLabel = "auto-reviewed"

  /// Prompts for Contacts access on first run, then returns immediately on later runs.
  func requestAccess() throws {
    let semaphore = DispatchSemaphore(value: 0)
    var granted = false
    var failure: Error?
    store.requestAccess(for: .contacts) { ok, error in
      granted = ok
      failure = error
      semaphore.signal()
    }
    semaphore.wait()
    if let failure { throw ContactError("contacts access error: \(failure.localizedDescription)") }
    guard granted else {
      throw ContactError(
        "contacts access denied — grant it in System Settings ▸ Privacy & Security ▸ Contacts")
    }
  }

  // MARK: Lookup

  /// CNContact identifiers in this store carry the `:ABPerson` suffix natively,
  /// so callers that pass a bare UUID get it appended (which matches the
  /// AppleScript form humans see in the rest of the pipeline).
  private func canonical(_ id: String) -> String {
    id.contains(":ABPerson") ? id : id + ":ABPerson"
  }

  func contact(_ id: String, keys: [CNKeyDescriptor]) throws -> CNContact {
    let identifier = canonical(id)
    do {
      return try store.unifiedContact(withIdentifier: identifier, keysToFetch: keys)
    } catch {
      throw ContactError("no contact with id \(identifier)")
    }
  }

  private func mutable(_ id: String, keys: [CNKeyDescriptor]) throws -> CNMutableContact {
    guard let copy = try contact(id, keys: keys).mutableCopy() as? CNMutableContact else {
      throw ContactError("could not open contact \(id) for editing")
    }
    return copy
  }

  private func commit(_ contact: CNMutableContact) throws {
    let request = CNSaveRequest()
    request.update(contact)
    try executeWithRetry(request)
  }

  /// `CNSaveRequest.execute` throws `NSCocoaErrorDomain 134092` when iCloud is
  /// mid-syncing the record we're trying to write. A few hundred ms of backoff
  /// clears most cases; persistent conflicts surface as the raw NSError so the
  /// caller can decide whether to fall back to AppleScript.
  private func executeWithRetry(_ request: CNSaveRequest) throws {
    let backoffs: [UInt32] = [200_000, 500_000, 1_000_000]
    for (attempt, delay) in backoffs.enumerated() {
      do {
        try store.execute(request)
        return
      } catch let error as NSError where isConflict(error) {
        if attempt == backoffs.count - 1 { throw error }
        usleep(delay)
      }
    }
  }

  func isConflict(_ error: NSError) -> Bool {
    error.domain == NSCocoaErrorDomain && error.code == 134092
  }

  /// CN first; on persistent iCloud-conflict, the AppleScript fallback.
  /// Image-shaped writes signal whether the fallback ran so callers can warn
  /// the operator that the change may not have actually persisted on disk.
  @discardableResult
  func nativeOrFallback(_ native: () throws -> Void, _ fallback: () throws -> Void) throws
    -> WriteOutcome
  {
    do {
      try native()
      return .native
    } catch let error as NSError where isConflict(error) {
      try fallback()
      return .appleScript
    }
  }

  // MARK: Mutations

  /// Sets the photo. On records iCloud has locked (CN 134092), AppleScript
  /// silently no-ops the image write — so the caller learns whether the
  /// fallback was used and can pass that signal back through the CLI to the
  /// operator, who then knows to retry once iCloud resolves the conflict.
  @discardableResult
  func setImage(_ id: String, fromFile path: String) throws -> WriteOutcome {
    let url = URL(fileURLWithPath: path)
    guard let data = try? Data(contentsOf: url) else {
      throw ContactError("could not read image file \(path)")
    }
    do {
      let contact = try mutable(id, keys: [CNContactImageDataKey as CNKeyDescriptor])
      contact.imageData = data
      try commit(contact)
      return .native
    } catch let error as NSError where isConflict(error) {
      try AppleScriptFallback.setImage(id, fromFile: path)
      return .applescriptUnreliableForImages
    }
  }

  func clearImage(_ id: String) throws {
    do {
      let contact = try mutable(id, keys: [CNContactImageDataKey as CNKeyDescriptor])
      contact.imageData = nil
      try commit(contact)
    } catch let error as NSError where isConflict(error) {
      try AppleScriptFallback.clearImage(id)
    }
  }

  func hasImage(_ id: String) throws -> Bool {
    try contact(id, keys: [CNContactImageDataAvailableKey as CNKeyDescriptor]).imageDataAvailable
  }

  func addURL(_ id: String, label: String, value: String) throws {
    try nativeOrFallback(
      {
        let contact = try self.mutable(id, keys: [CNContactUrlAddressesKey as CNKeyDescriptor])
        guard !contact.urlAddresses.contains(where: { ($0.value as String) == value }) else {
          return
        }
        contact.urlAddresses.append(CNLabeledValue(label: label, value: value as NSString))
        try self.commit(contact)
      },
      {
        try AppleScriptFallback.addURL(id, label: label, value: value)
      })
  }

  func addEmail(_ id: String, label: String, value: String) throws {
    try nativeOrFallback(
      {
        let contact = try self.mutable(id, keys: [CNContactEmailAddressesKey as CNKeyDescriptor])
        guard
          !contact.emailAddresses.contains(where: {
            ($0.value as String).caseInsensitiveCompare(value) == .orderedSame
          })
        else { return }
        contact.emailAddresses.append(CNLabeledValue(label: label, value: value as NSString))
        try self.commit(contact)
      },
      {
        try AppleScriptFallback.addEmail(id, label: label, value: value)
      })
  }

  /// Upserts the review stamp: replaces the existing `auto-reviewed` date in place,
  /// or appends one. Never deletes (the delete path is what threw `-10000`
  /// in the old AppleEvents world).
  func stampReviewed(_ id: String, on date: DateComponents) throws {
    try nativeOrFallback(
      {
        let contact = try self.mutable(id, keys: [CNContactDatesKey as CNKeyDescriptor])
        let stamp = CNLabeledValue(label: Self.reviewLabel, value: date as NSDateComponents)
        if let index = contact.dates.firstIndex(where: { $0.label == Self.reviewLabel }) {
          contact.dates[index] = stamp
        } else {
          contact.dates.append(stamp)
        }
        try self.commit(contact)
      },
      {
        try AppleScriptFallback.stamp(id, on: date)
      })
  }

  func reviewedOn(_ id: String) throws -> DateComponents? {
    let contact = try self.contact(id, keys: [CNContactDatesKey as CNKeyDescriptor])
    return contact.dates.first(where: { $0.label == Self.reviewLabel })?.value as DateComponents?
  }

  // MARK: Groups

  private func group(named name: String, createInContainerOf contact: CNContact?) throws -> CNGroup
  {
    if let existing = try store.groups(matching: nil).first(where: { $0.name == name }) {
      return existing
    }
    guard let contact else { throw ContactError("no group named \(name)") }
    let group = CNMutableGroup()
    group.name = name
    let containers = try store.containers(
      matching: CNContainer.predicateForContainerOfContact(withIdentifier: contact.identifier))
    let request = CNSaveRequest()
    request.add(group, toContainerWithIdentifier: containers.first?.identifier)
    try store.execute(request)
    return group
  }

  func addToGroup(_ id: String, _ name: String) throws {
    try nativeOrFallback(
      {
        let contact = try self.contact(id, keys: [CNContactIdentifierKey as CNKeyDescriptor])
        let group = try self.group(named: name, createInContainerOf: contact)
        let request = CNSaveRequest()
        request.addMember(contact, to: group)
        try self.executeWithRetry(request)
      },
      {
        try AppleScriptFallback.tag(id, name)
      })
  }

  func removeFromGroup(_ id: String, _ name: String) throws {
    try nativeOrFallback(
      {
        let contact = try self.contact(id, keys: [CNContactIdentifierKey as CNKeyDescriptor])
        let group = try self.group(named: name, createInContainerOf: nil)
        let request = CNSaveRequest()
        request.removeMember(contact, from: group)
        try self.executeWithRetry(request)
      },
      {
        try AppleScriptFallback.untag(id, name)
      })
  }

  func groupNames(_ id: String) throws -> [String] {
    let target = canonical(id)
    var names: [String] = []
    for group in try store.groups(matching: nil) {
      let members =
        (try? store.unifiedContacts(
          matching: CNContact.predicateForContactsInGroup(withIdentifier: group.identifier),
          keysToFetch: [CNContactIdentifierKey as CNKeyDescriptor])) ?? []
      if members.contains(where: { $0.identifier == target }) { names.append(group.name) }
    }
    return names
  }

  // MARK: Enumeration

  /// Every contact in the store, with photo state for each: no image, or the
  /// header dimensions of whatever's there. ImageIO reads just the JPEG/PNG/
  /// TIFF header — no full decode — so this is cheap even for hundreds of
  /// cards. The 96/192 TIFFs left over from old iCloud thumbnails surface as
  /// `tiny` and are the typical blurry-photo culprits.
  func auditPhotos() throws -> [(name: String, id: String, org: String, width: Int?, height: Int?)]
  {
    let keys: [CNKeyDescriptor] = [
      CNContactGivenNameKey, CNContactFamilyNameKey, CNContactOrganizationNameKey,
      CNContactImageDataKey, CNContactImageDataAvailableKey,
    ].map { $0 as CNKeyDescriptor }
    let request = CNContactFetchRequest(keysToFetch: keys)
    var results: [(name: String, id: String, org: String, width: Int?, height: Int?)] = []
    try store.enumerateContacts(with: request) { contact, _ in
      let displayName: String = {
        let parts = [contact.givenName, contact.familyName].filter { !$0.isEmpty }
        if !parts.isEmpty { return parts.joined(separator: " ") }
        return contact.organizationName.isEmpty ? "(unnamed)" : contact.organizationName
      }()
      guard contact.imageDataAvailable, let data = contact.imageData else {
        results.append((displayName, contact.identifier, contact.organizationName, nil, nil))
        return
      }
      let (w, h) = ImageHeader.dimensions(of: data) ?? (0, 0)
      results.append((displayName, contact.identifier, contact.organizationName, w, h))
    }
    return results
  }

  /// Every contact whose sort key starts with `initial` and has no review stamp yet.
  func unreviewed(initial: Character) throws -> [(
    name: String, id: String, hasImage: Bool, org: String
  )] {
    let keys: [CNKeyDescriptor] = [
      CNContactGivenNameKey, CNContactFamilyNameKey, CNContactOrganizationNameKey,
      CNContactDatesKey, CNContactImageDataAvailableKey,
    ].map { $0 as CNKeyDescriptor }
    let request = CNContactFetchRequest(keysToFetch: keys)
    let target = String(initial).uppercased()
    var results: [(name: String, id: String, hasImage: Bool, org: String)] = []
    try store.enumerateContacts(with: request) { contact, _ in
      let sortKey = contact.familyName.isEmpty ? contact.givenName : contact.familyName
      guard let first = sortKey.first, String(first).uppercased() == target else { return }
      guard !contact.dates.contains(where: { $0.label == Self.reviewLabel }) else { return }
      let name = "\(contact.givenName) \(contact.familyName)".trimmingCharacters(in: .whitespaces)
      results.append(
        (name, contact.identifier, contact.imageDataAvailable, contact.organizationName))
    }
    return results
  }

  /// Every member of `group`, with their stamp state — the backbone of any
  /// batch operation (re-stamp everyone we'd tagged, audit a section, etc).
  func members(of groupName: String) throws -> [(
    name: String, id: String, reviewed: DateComponents?, hasImage: Bool
  )] {
    guard let group = try store.groups(matching: nil).first(where: { $0.name == groupName }) else {
      return []
    }
    let keys: [CNKeyDescriptor] = [
      CNContactGivenNameKey, CNContactFamilyNameKey,
      CNContactDatesKey, CNContactImageDataAvailableKey,
    ].map { $0 as CNKeyDescriptor }
    let contacts = try store.unifiedContacts(
      matching: CNContact.predicateForContactsInGroup(withIdentifier: group.identifier),
      keysToFetch: keys)
    return contacts.map { contact in
      let stamp =
        contact.dates.first(where: { $0.label == Self.reviewLabel })?.value as DateComponents?
      let name = "\(contact.givenName) \(contact.familyName)".trimmingCharacters(in: .whitespaces)
      return (name, contact.identifier, stamp, contact.imageDataAvailable)
    }
  }

  func find(name query: String) throws -> [(name: String, id: String)] {
    let predicate = CNContact.predicateForContacts(matchingName: query)
    let keys = [CNContactGivenNameKey, CNContactFamilyNameKey].map { $0 as CNKeyDescriptor }
    return try store.unifiedContacts(matching: predicate, keysToFetch: keys).map {
      ("\($0.givenName) \($0.familyName)".trimmingCharacters(in: .whitespaces), $0.identifier)
    }
  }
}

struct ContactError: Error {
  let message: String
  init(_ m: String) { message = m }
}

/// Which write path succeeded — exposed so the CLI can warn the operator when
/// the AppleScript fallback ran for an image (where it can silently no-op).
enum WriteOutcome: String { case native, appleScript, applescriptUnreliableForImages }
