// swift-tools-version:5.9
import PackageDescription

let package = Package(
  name: "contactctl",
  platforms: [.macOS(.v12)],
  targets: [
    .executableTarget(name: "contactctl", path: "Sources/contactctl")
  ]
)
