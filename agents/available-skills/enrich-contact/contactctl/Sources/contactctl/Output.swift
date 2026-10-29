import Contacts
import Foundation

/// The keys `get` fetches to dump a full card.
let detailKeys: [CNKeyDescriptor] = [
  CNContactIdentifierKey, CNContactGivenNameKey, CNContactMiddleNameKey, CNContactFamilyNameKey,
  CNContactNicknameKey, CNContactNamePrefixKey, CNContactNameSuffixKey,
  CNContactOrganizationNameKey, CNContactJobTitleKey, CNContactDepartmentNameKey,
  CNContactPhoneNumbersKey, CNContactEmailAddressesKey, CNContactUrlAddressesKey,
  CNContactPostalAddressesKey, CNContactBirthdayKey, CNContactDatesKey,
  CNContactSocialProfilesKey, CNContactInstantMessageAddressesKey,
  CNContactImageDataAvailableKey,
].map { $0 as CNKeyDescriptor }

/// Serializes a card to a JSON-ready dictionary. Reading is generous: a missing
/// note key or restricted field degrades to omission rather than a crash.
enum CardEncoder {
  static func json(_ contact: CNContact, groups: [String]) -> [String: Any] {
    var card: [String: Any] = [
      "id": contact.identifier,
      "name": "\(contact.givenName) \(contact.familyName)".trimmingCharacters(in: .whitespaces),
      "image": contact.imageDataAvailable,
      "groups": groups,
    ]
    put(&card, "first", contact.givenName)
    put(&card, "middle", contact.middleName)
    put(&card, "last", contact.familyName)
    put(&card, "nickname", contact.nickname)
    put(&card, "organization", contact.organizationName)
    put(&card, "jobTitle", contact.jobTitle)
    put(&card, "department", contact.departmentName)
    card["phones"] = contact.phoneNumbers.map { labeled($0.label, $0.value.stringValue) }
    card["emails"] = contact.emailAddresses.map { labeled($0.label, $0.value as String) }
    card["urls"] = contact.urlAddresses.map { labeled($0.label, $0.value as String) }
    card["dates"] = contact.dates.map { labeled($0.label, dateString($0.value as DateComponents)) }
    card["addresses"] = contact.postalAddresses.map {
      labeled(
        $0.label,
        CNPostalAddressFormatter.string(from: $0.value, style: .mailingAddress)
          .replacingOccurrences(of: "\n", with: ", "))
    }
    return card
  }

  private static func put(_ card: inout [String: Any], _ key: String, _ value: String) {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    if !trimmed.isEmpty { card[key] = trimmed }
  }

  private static func labeled(_ label: String?, _ value: String) -> [String: String] {
    ["label": CNLabeledValue<NSString>.localizedString(forLabel: label ?? ""), "value": value]
  }

  private static func dateString(_ parts: DateComponents) -> String {
    guard let month = parts.month, let day = parts.day else { return "" }
    if let year = parts.year { return String(format: "%04d-%02d-%02d", year, month, day) }
    return String(format: "%02d-%02d", month, day)
  }
}

/// stdout JSON writer. A single value per invocation keeps callers' parsing trivial.
enum Output {
  static func print(_ value: Any) {
    guard
      let data = try? JSONSerialization.data(
        withJSONObject: value, options: [.prettyPrinted, .sortedKeys]),
      let text = String(data: data, encoding: .utf8)
    else {
      Swift.print("{\"error\":\"could not encode result\"}")
      return
    }
    Swift.print(text)
  }
}
