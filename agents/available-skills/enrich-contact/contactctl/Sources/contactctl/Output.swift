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
  static func json(_ c: CNContact, groups: [String]) -> [String: Any] {
    var card: [String: Any] = [
      "id": c.identifier,
      "name": "\(c.givenName) \(c.familyName)".trimmingCharacters(in: .whitespaces),
      "image": c.imageDataAvailable,
      "groups": groups,
    ]
    put(&card, "first", c.givenName)
    put(&card, "middle", c.middleName)
    put(&card, "last", c.familyName)
    put(&card, "nickname", c.nickname)
    put(&card, "organization", c.organizationName)
    put(&card, "jobTitle", c.jobTitle)
    put(&card, "department", c.departmentName)
    card["phones"] = c.phoneNumbers.map { labeled($0.label, $0.value.stringValue) }
    card["emails"] = c.emailAddresses.map { labeled($0.label, $0.value as String) }
    card["urls"] = c.urlAddresses.map { labeled($0.label, $0.value as String) }
    card["dates"] = c.dates.map { labeled($0.label, dateString($0.value as DateComponents)) }
    card["addresses"] = c.postalAddresses.map {
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

  private static func dateString(_ d: DateComponents) -> String {
    guard let m = d.month, let day = d.day else { return "" }
    if let y = d.year { return String(format: "%04d-%02d-%02d", y, m, day) }
    return String(format: "%02d-%02d", m, day)
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
