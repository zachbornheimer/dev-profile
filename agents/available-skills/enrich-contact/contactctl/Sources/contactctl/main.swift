import Foundation

/// contactctl — a thin CLI over the macOS Contacts framework for the
/// enrich-contact pipeline. Reads and writes go through `ContactStore`
/// (the one boundary to `CNContactStore`); every command prints one JSON value.
let usage = """
  contactctl — update a macOS Contacts card

  USAGE
    contactctl get        <id>
    contactctl tag        <id> <group>
    contactctl untag      <id> <group>
    contactctl url        <id> <label> <value>
    contactctl email      <id> <label> <value>
    contactctl photo      <id> <imagePath>
    contactctl rmphoto    <id>
    contactctl stamp      <id> [YYYY-MM-DD]      # upsert the auto-reviewed date (default: today)
    contactctl reviewed   <id>                   # print the auto-reviewed date, or null
    contactctl unreviewed <letter>               # cards by surname-initial with no review stamp
    contactctl members    <group>                # everyone in a group, with stamp state
    contactctl find       <name>
    contactctl get-profile-picture <fbURL> [path]   # download FB profile photo via the user's logged-in Chrome

  NOTES
    <id> accepts a CNContact identifier or the AppleScript form <uuid>:ABPerson.
    First run prompts once for Contacts access (System Settings ▸ Privacy & Security ▸ Contacts).
  """

let arguments = Array(CommandLine.arguments.dropFirst())
guard let command = arguments.first else {
  print(usage)
  exit(2)
}

let store = ContactStore()
do {
  try store.requestAccess()
  try Commands.run(command, Array(arguments.dropFirst()), store: store)
} catch let error as ContactError {
  FileHandle.standardError.write(Data("error: \(error.message)\n".utf8))
  exit(1)
} catch {
  FileHandle.standardError.write(Data("error: \(error.localizedDescription)\n".utf8))
  exit(1)
}
