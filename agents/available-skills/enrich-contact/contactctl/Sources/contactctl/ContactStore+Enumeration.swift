import Contacts
import Foundation

/// One contact's photo state: no image, or the header dimensions of what's there.
struct PhotoRow {
  let name: String
  let id: String
  let org: String
  let width: Int?
  let height: Int?
}

/// One member of a group, with their review stamp and image state.
struct MemberRow {
  let name: String
  let id: String
  let reviewed: DateComponents?
  let hasImage: Bool
}

/// One contact whose sort key matches an initial and carries no review stamp.
struct UnreviewedRow {
  let name: String
  let id: String
  let hasImage: Bool
  let org: String
}

/// Reads that enumerate the store. Split from `ContactStore.swift` to keep the
/// type's body inside the lint limit; the store itself stays the single
/// boundary to the Contacts framework.
extension ContactStore {
  // MARK: Enumeration

  /// Every contact in the store, with photo state for each: no image, or the
  /// header dimensions of whatever's there. ImageIO reads just the JPEG/PNG/
  /// TIFF header — no full decode — so this is cheap even for hundreds of
  /// cards. The 96/192 TIFFs left over from old iCloud thumbnails surface as
  /// `tiny` and are the typical blurry-photo culprits.
  func auditPhotos() throws -> [PhotoRow] {
    let keys: [CNKeyDescriptor] = [
      CNContactGivenNameKey, CNContactFamilyNameKey, CNContactOrganizationNameKey,
      CNContactImageDataKey, CNContactImageDataAvailableKey,
    ].map { $0 as CNKeyDescriptor }
    let request = CNContactFetchRequest(keysToFetch: keys)
    var results: [PhotoRow] = []
    try store.enumerateContacts(with: request) { contact, _ in
      let displayName: String = {
        let parts = [contact.givenName, contact.familyName].filter { !$0.isEmpty }
        if !parts.isEmpty { return parts.joined(separator: " ") }
        return contact.organizationName.isEmpty ? "(unnamed)" : contact.organizationName
      }()
      guard contact.imageDataAvailable, let data = contact.imageData else {
        results.append(
          PhotoRow(
            name: displayName, id: contact.identifier, org: contact.organizationName,
            width: nil, height: nil))
        return
      }
      let (width, height) = ImageHeader.dimensions(of: data) ?? (0, 0)
      results.append(
        PhotoRow(
          name: displayName, id: contact.identifier, org: contact.organizationName,
          width: width, height: height))
    }
    return results
  }

  /// Every contact whose sort key starts with `initial` and has no review stamp yet.
  func unreviewed(initial: Character) throws -> [UnreviewedRow] {
    let keys: [CNKeyDescriptor] = [
      CNContactGivenNameKey, CNContactFamilyNameKey, CNContactOrganizationNameKey,
      CNContactDatesKey, CNContactImageDataAvailableKey,
    ].map { $0 as CNKeyDescriptor }
    let request = CNContactFetchRequest(keysToFetch: keys)
    let target = String(initial).uppercased()
    var results: [UnreviewedRow] = []
    try store.enumerateContacts(with: request) { contact, _ in
      let sortKey = contact.familyName.isEmpty ? contact.givenName : contact.familyName
      guard let first = sortKey.first, String(first).uppercased() == target else { return }
      guard !contact.dates.contains(where: { $0.label == Self.reviewLabel }) else { return }
      let name = "\(contact.givenName) \(contact.familyName)".trimmingCharacters(in: .whitespaces)
      results.append(
        UnreviewedRow(
          name: name, id: contact.identifier, hasImage: contact.imageDataAvailable,
          org: contact.organizationName))
    }
    return results
  }

  /// Every member of `group`, with their stamp state — the backbone of any
  /// batch operation (re-stamp everyone we'd tagged, audit a section, etc).
  func members(of groupName: String) throws -> [MemberRow] {
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
      return MemberRow(
        name: name, id: contact.identifier, reviewed: stamp, hasImage: contact.imageDataAvailable)
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
