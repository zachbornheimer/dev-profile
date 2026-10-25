import Foundation
import ImageIO

/// Reads JPEG/PNG/TIFF dimensions from raw bytes without decoding the full
/// image — `CGImageSourceCopyPropertiesAtIndex` looks at the header only.
/// Used by `photo-audit` to surface tiny iCloud-thumbnail TIFFs (96×96 or
/// 192×192) as blurry candidates.
enum ImageHeader {
  static func dimensions(of data: Data) -> (width: Int, height: Int)? {
    guard let src = CGImageSourceCreateWithData(data as CFData, nil),
      let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any],
      let w = props[kCGImagePropertyPixelWidth] as? Int,
      let h = props[kCGImagePropertyPixelHeight] as? Int
    else { return nil }
    return (w, h)
  }
}
