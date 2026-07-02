import io

from PIL import Image, ImageCms, ExifTags


def InferTransferFunction(profileName, exifColorSpace):
    name = (profileName or "").lower()

    if "linear" in name:
        return "Linear"
    if "prophoto" in name or "romm" in name:
        return "ProPhoto"
    if "adobe rgb" in name or "adobergb" in name:
        return "Adobe RGB"
    if "display p3" in name or "p3" in name or "srgb" in name:
        return "sRGB / Display P3"
    if exifColorSpace == 1:
        return "sRGB / Display P3"

    return "Unknown (sRGB / Display P3 assumed)"


def ExifColorSpaceName(value):
    if value == 1:
        return "sRGB"
    if value == 65535:
        return "Uncalibrated"
    if value is None:
        return None
    return f"EXIF {value}"


def ReadImageMetadata(filename):
    metadata = {
        "dimensions": "",
        "colorSpace": "Unknown (sRGB / Display P3 assumed)",
        "transfer": "Unknown (sRGB / Display P3 assumed)",
    }

    try:
        with Image.open(filename) as img:
            metadata["dimensions"] = f"{img.size[0]}x{img.size[1]}"

            profileName = ""
            iccProfile = img.info.get("icc_profile")
            if iccProfile:
                try:
                    profile = ImageCms.ImageCmsProfile(io.BytesIO(iccProfile))
                    profileName = ImageCms.getProfileName(profile).strip()
                except Exception:
                    profileName = "Embedded ICC"

            exifColorSpace = None
            try:
                exif = img.getexif()
                colorSpaceTag = next((tag for tag, name in ExifTags.TAGS.items() if name == "ColorSpace"), None)
                if colorSpaceTag:
                    exifColorSpace = exif.get(colorSpaceTag)
            except Exception:
                pass

            metadata["colorSpace"] = profileName or ExifColorSpaceName(exifColorSpace) or "Unknown (sRGB / Display P3 assumed)"
            metadata["transfer"] = InferTransferFunction(profileName, exifColorSpace)
    except Exception:
        pass

    return metadata


def ReadImageDimensions(filename):
    try:
        with Image.open(filename) as img:
            return img.size
    except Exception:
        return None


def IsUnknownTransferFunction(functionName):
    return str(functionName or "").strip().lower().startswith("unknown")


def IsUnknownColorSpace(colorSpaceName):
    return str(colorSpaceName or "").strip().lower().startswith("unknown")


def ColorSpaceLine(colorSpaceName):
    label = "Color space: "
    if IsUnknownColorSpace(colorSpaceName):
        return [
            (label, "OVERLAY_TEXT"),
            (str(colorSpaceName), "WARNING"),
        ]
    return f"{label}{colorSpaceName}"


def TransferFunctionLine(functionName):
    label = "Transfer Function: "
    if IsUnknownTransferFunction(functionName):
        return [
            (label, "OVERLAY_TEXT"),
            (str(functionName), "WARNING"),
        ]
    return f"{label}{functionName}"


def TransferOverrideLine(functionName):
    return [
        (f"Transfer Function: {functionName} ", "OVERLAY_TEXT"),
        ("(user override)", "WARNING"),
    ]


def DimensionsLine(label, width, height, status = None):
    line = [(f"{label}: {width}x{height}", "OVERLAY_TEXT")]
    if status == "inherited":
        line.extend([
            (" ", "OVERLAY_TEXT"),
            ("(inherited)", "WARNING"),
        ])
    elif status == "overridden":
        line.extend([
            (" ", "OVERLAY_TEXT"),
            ("(user override)", "WARNING"),
        ])
    return line
