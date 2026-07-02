from PIL import Image, ImageCms, ExifTags
import numpy as np
import io, os, time
from . import blend as bnc
from .logging import LOG_BAR, Logger

class BlendFunction:
    MIN = bnc.MinBlend
    MAX = bnc.MaxBlend
    SCREEN = bnc.ScreenBlend
    ADD = bnc.AddBlend
    SUBTRACT = bnc.SubtractBlend
    MULTIPLY = bnc.MultiplyBlend
    DIVIDE = bnc.DivideBlend
    OVERLAY = bnc.OverlayBlend
    UNDERLAY = bnc.UnderlayBlend
    MINMAX = bnc.MinMaxBlend
    MAXMIN = bnc.MaxMinBlend

LOG_FILENAME = "log"
BUFFER_LENGTH_FPS = 10

FILE_TYPE_ALIASES = {
    "jpg": ("jpg", "jpeg"),
    "tiff": ("tif", "tiff"),
}

TRANSFER_FUNCTIONS = {
    "sRGB / Display P3": {
        "decode": bnc.SrgbToLinear,
        "encode": bnc.LinearToSrgb,
    },
    "Adobe RGB": {
        "decode": bnc.Gamma22ToLinear,
        "encode": bnc.LinearToGamma22,
    },
    "ProPhoto": {
        "decode": bnc.ProPhotoToLinear,
        "encode": bnc.LinearToProPhoto,
    },
    "Linear": {
        "decode": bnc.LinearTransferToLinear,
        "encode": bnc.LinearToLinearTransfer,
    },
}

BLEND_MODE_IDS = {
    None: bnc.BLEND_MODE_NONE,
    bnc.MinBlend: bnc.BLEND_MODE_MIN,
    bnc.MaxBlend: bnc.BLEND_MODE_MAX,
    bnc.ScreenBlend: bnc.BLEND_MODE_SCREEN,
    bnc.AddBlend: bnc.BLEND_MODE_ADD,
    bnc.SubtractBlend: bnc.BLEND_MODE_SUBTRACT,
    bnc.MultiplyBlend: bnc.BLEND_MODE_MULTIPLY,
    bnc.DivideBlend: bnc.BLEND_MODE_DIVIDE,
    bnc.OverlayBlend: bnc.BLEND_MODE_OVERLAY,
    bnc.UnderlayBlend: bnc.BLEND_MODE_UNDERLAY,
    bnc.MinMaxBlend: bnc.BLEND_MODE_MINMAX,
    bnc.MaxMinBlend: bnc.BLEND_MODE_MAXMIN,
}

TRANSFER_IDS = {
    "sRGB / Display P3": bnc.TRANSFER_SRGB,
    "Adobe RGB": bnc.TRANSFER_GAMMA22,
    "ProPhoto": bnc.TRANSFER_PROPHOTO,
    "Linear": bnc.TRANSFER_LINEAR,
}

RESIZE_FILTERS = {
    "Nearest": Image.Resampling.NEAREST,
    "Box": Image.Resampling.BOX,
    "Bilinear": Image.Resampling.BILINEAR,
    "Hamming": Image.Resampling.HAMMING,
    "Bicubic": Image.Resampling.BICUBIC,
    "Lanczos": Image.Resampling.LANCZOS,
}

SRGB_ICC_PROFILE = None

# ============================================================ #

class RenderCancelled(Exception):
    pass

class CallbackLogger:

    def __init__(self, onPrint = None):
        self.onPrint = onPrint

    def _Emit(self, msg):
        if self.onPrint:
            self.onPrint(msg)

    def _PrependTime(self, msg):
        return f"[{time.strftime('%H:%M:%S')}] - {msg}"

    def _Bar(self):
        return LOG_BAR

    def Log(self, _msg):
        pass

    def LogTime(self, _msg):
        pass

    def PrintLog(self, msg):
        self._Emit(msg)

    def PrintTime(self, msg):
        self._Emit(self._PrependTime(msg))

    def PrintLogTime(self, msg):
        self._Emit(self._PrependTime(msg))

    def PrintLine(self):
        self._Emit("")

    def LogLine(self):
        pass

    def PrintLogLine(self):
        self._Emit("")

    def PrintBar(self):
        self._Emit(self._Bar())

    def LogBar(self):
        pass

    def PrintLogBar(self):
        self._Emit(self._Bar())

    def LogError(self, _err):
        pass

    def PrintLogError(self, err):
        self.PrintLine()
        self.PrintBar()
        self._Emit("|| ERROR:\t" + err)
        self.PrintBar()
        self.PrintLine()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class NullLogger:

    def __getattr__(self, _name):
        return self._NoOp

    def _NoOp(self, *_args, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

def CheckCancelled(shouldCancel, logger):
    if shouldCancel and shouldCancel():
        msg = "Render cancelled."
        logger.PrintLogTime(msg)
        raise RenderCancelled(msg)

def CheckPaused(shouldPause, shouldCancel, logger):
    if not shouldPause or not shouldPause():
        return False

    logger.PrintLogTime("Render paused.")

    while shouldPause():
        CheckCancelled(shouldCancel, logger)
        time.sleep(0.1)

    logger.PrintLogTime("Render resumed.")
    return True

def ReportProgress(onProgress, currentFrame, frameCount):
    if onProgress:
        onProgress(currentFrame, frameCount)

def ReportFps(onFps, fps):
    if onFps:
        onFps(fps)

def ReportRemaining(onRemaining, seconds):
    if onRemaining:
        onRemaining(seconds)

def ReportPreview(onPreview, rgb, force = False):
    if onPreview:
        onPreview(rgb, force)

def ExtractProfileName(img):
    iccProfile = img.info.get("icc_profile")
    if not iccProfile:
        return ""

    try:
        profile = ImageCms.ImageCmsProfile(io.BytesIO(iccProfile))
        return ImageCms.getProfileName(profile).strip()
    except Exception:
        return "Embedded ICC"

def ExtractExifColorSpace(img):
    try:
        exif = img.getexif()
        colorSpaceTag = next((tag for tag, name in ExifTags.TAGS.items() if name == "ColorSpace"), None)
        if colorSpaceTag:
            return exif.get(colorSpaceTag)
    except Exception:
        pass

    return None

def DetectTransferFunction(profileName, exifColorSpace):
    name = (profileName or "").lower()

    if "linear" in name:
        return "Linear", bnc.LinearTransferToLinear
    if "prophoto" in name or "romm" in name:
        return "ProPhoto", bnc.ProPhotoToLinear
    if "adobe rgb" in name or "adobergb" in name:
        return "Adobe RGB", bnc.Gamma22ToLinear
    if "display p3" in name or "p3" in name or "srgb" in name:
        return "sRGB / Display P3", bnc.SrgbToLinear
    if exifColorSpace == 1:
        return "sRGB / Display P3", bnc.SrgbToLinear

    return "Unknown (sRGB / Display P3 assumed)", bnc.SrgbToLinear

def TransferFunctionNames():
    return tuple(TRANSFER_FUNCTIONS.keys())

def ResizeFilterNames():
    return tuple(RESIZE_FILTERS.keys())

def ResizeFilterName(name, fallback = "Lanczos"):
    return name if name in RESIZE_FILTERS else fallback

def ResizeFilter(name):
    return RESIZE_FILTERS[ResizeFilterName(name)]

def TransferFunctionName(name, fallback = "sRGB / Display P3"):
    return name if name in TRANSFER_FUNCTIONS else fallback

def DecodeTransferFunction(name):
    return TRANSFER_FUNCTIONS[TransferFunctionName(name)]["decode"]

def EncodeTransferFunction(name):
    return TRANSFER_FUNCTIONS[TransferFunctionName(name)]["encode"]

def EncodeTransferFunctionId(name):
    return TRANSFER_IDS[TransferFunctionName(name)]

def BlendModeId(mode):
    if mode in BLEND_MODE_IDS:
        return BLEND_MODE_IDS[mode]

    pyFunc = getattr(mode, "py_func", None)
    if pyFunc is not None:
        for blendFunction, modeId in BLEND_MODE_IDS.items():
            if getattr(blendFunction, "py_func", None) is pyFunc:
                return modeId

    return None

def SrgbIccProfile():
    global SRGB_ICC_PROFILE
    if SRGB_ICC_PROFILE is None:
        SRGB_ICC_PROFILE = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    return SRGB_ICC_PROFILE

def ExportMetadataParms(fileType, transferName):
    fileType = CanonicalFileType(fileType)
    transferName = TransferFunctionName(transferName)

    if transferName != "sRGB / Display P3":
        return {}

    parms = {"icc_profile": SrgbIccProfile()}
    if fileType in ("jpg", "tiff"):
        exif = Image.Exif()
        exif[40961] = 1 # ColorSpace: sRGB
        parms["exif"] = exif
    return parms

def ReadImage(filename, logger, downsampleScale = 1, transferOverride = None, targetSize = None, resizeFilterName = "Lanczos", blendInLinear = True):
    rgb = None
    with Image.open(filename) as img:
        profileName = ExtractProfileName(img)
        exifColorSpace = ExtractExifColorSpace(img)
        if transferOverride:
            transferName = TransferFunctionName(transferOverride)
            transferFunction = DecodeTransferFunction(transferName)
            transferName = f"{transferName} (override)"
        else:
            transferName, transferFunction = DetectTransferFunction(profileName, exifColorSpace)
        if not blendInLinear:
            transferName = f"{transferName} (not linearized)"
            transferFunction = bnc.LinearTransferToLinear
        logger.PrintLogTime(f"Reading image \"{os.path.basename(filename)}\" ({transferName})...")

        img._getexif = lambda: None
        img = img.convert("RGB")
        downsampleScale = max(1, int(downsampleScale))

        if downsampleScale > 1:
            width, height = img.size
            size = (
                max(1, width // downsampleScale),
                max(1, height // downsampleScale),
            )
            img = img.resize(size, Image.Resampling.BOX)

        if targetSize and img.size != targetSize:
            logger.PrintLogTime(
                f"Resizing \"{os.path.basename(filename)}\" from "
                f"{img.size[0]}x{img.size[1]} to {targetSize[0]}x{targetSize[1]} "
                f"using {ResizeFilterName(resizeFilterName)}..."
            )
            img = img.resize(targetSize, ResizeFilter(resizeFilterName))

        if blendInLinear:
            rgb = transferFunction(np.array(img, dtype = np.float32))
        else:
            rgb = bnc.Uint8ToNormalizedFloat(np.asarray(img, dtype = np.uint8))
    return rgb

def SaveFrame(rgb, outSettings, frameNumber, logger):
    if outSettings.get("onlyExportFinalFrame", False):
        filename = f"{outSettings["outputFileName"]}.{outSettings["outputFileType"]}"
    else:
        filename = f"{outSettings["outputFileName"]}_{frameNumber:04d}.{outSettings["outputFileType"]}"
    logger.PrintLogTime(f"Saved \"{filename}\"")
    transferName = TransferFunctionName(outSettings.get("exportTransferFunction", "sRGB / Display P3"))
    transferId = EncodeTransferFunctionId(transferName) if outSettings.get("blendInLinear", True) else bnc.TRANSFER_LINEAR
    outImg = Image.fromarray(bnc.LinearToTransferUint8(rgb, transferId))
    saveParms = {
        **outSettings["outputParms"],
        **outSettings.get("outputMetadataParms", {}),
    }
    outImg.save(os.path.join(outSettings["outputDirectory"], filename), **saveParms)

def FormatShape(shape):
    return f"{shape[1]}x{shape[0]}x{shape[2]}"

def CanonicalFileType(fileType):
    fileType = fileType.strip().lower().lstrip(".")
    if fileType in ("", "mixed", "all", "images"):
        return fileType or "mixed"
    if fileType == "jpeg":
        return "jpg"
    if fileType == "tif":
        return "tiff"
    return fileType

def FileTypeExtensions(fileType):
    fileType = CanonicalFileType(fileType)
    return FILE_TYPE_ALIASES.get(fileType, (fileType,))

def FindFilenames(directory, fileType):
    extensions = set(FileTypeExtensions(fileType))
    filenames = []

    for filename in os.listdir(directory):
        path = os.path.join(directory, filename)
        if os.path.isfile(path):
            extension = os.path.splitext(filename)[1].lower().lstrip(".")
            if extension in extensions:
                filenames.append(path)

    return sorted(filenames)

def ClampSettings(settings):
    settings = {
        key: value.copy() if isinstance(value, dict) else value
        for key, value in settings.items()
    }
    if not isinstance(settings.get("render"), dict):
        settings["render"] = {}
    settings["render"]["path"]           = min(max(0, int(settings["render"].get("path", 0))), 2)
    settings["render"]["windowSize"]     = max(1, int(settings["render"].get("windowSize", 5)))
    settings["render"]["pairOffset"]     = int(settings["render"].get("pairOffset", -1))
    settings["render"]["blendInLinear"]   = bool(settings["render"].get("blendInLinear", True))
    settings["blend"]["decay"]            = float(min(max(0.0, settings["blend"]["decay"]), 1.0))
    settings["blend"]["scale"]            = float(settings["blend"].get("scale", 1.0))
    settings["blend"]["lift"]             = float(settings["blend"].get("lift", 0.0))
    settings["blend"]["opacity"]          = float(min(max(0.0, settings["blend"]["opacity"]), 1.0))
    settings["blend"]["middleGray"]       = float(min(max(0.0, settings["blend"].get("middleGray", bnc.LINEAR_0_5)), 1.0))
    settings["input"]["inputDirectory"]   = os.path.normpath(settings["input"]["inputDirectory"])
    settings["input"]["inputFileType"]    = CanonicalFileType(settings["input"]["inputFileType"])
    settings["input"]["startAt"]          = int(max(0, settings["input"]["startAt"]))
    settings["input"]["skipInput"]        = int(max(1, settings["input"]["skipInput"]))
    inputFilenames = settings["input"].get("inputFilenames")
    if isinstance(inputFilenames, (list, tuple)):
        settings["input"]["inputFilenames"] = [
            os.path.normpath(str(filename))
            for filename in inputFilenames
            if str(filename).strip()
        ]
    else:
        settings["input"]["inputFilenames"] = None
    if isinstance(settings["input"].get("inputIndices"), (list, tuple)):
        settings["input"]["inputIndices"] = [
            int(index)
            for index in settings["input"]["inputIndices"]
            if int(index) >= 0
        ]
    else:
        settings["input"]["inputIndices"] = None
    excludedFilenames = settings["input"].get("excludedFilenames", [])
    settings["input"]["excludedFilenames"] = {
        os.path.normcase(str(filename))
        for filename in excludedFilenames
    }
    settings["input"]["transferFunctionOverride"] = (
        TransferFunctionName(settings["input"].get("transferFunction"))
        if settings["input"].get("overrideTransferFunction") else
        None
    )
    settings["input"]["resolutionOverrideSize"] = (
        (
            int(max(1, settings["input"].get("width", 1))),
            int(max(1, settings["input"].get("height", 1))),
        )
        if settings["input"].get("overrideResolution") else
        None
    )
    settings["input"]["resizeFilter"] = ResizeFilterName(settings["input"].get("resizeFilter", "Lanczos"))
    settings["input"]["blendInLinear"] = settings["render"]["blendInLinear"]
    settings["output"]["outputDirectory"] = os.path.normpath(settings["output"]["outputDirectory"])
    settings["output"]["outputFileType"]  = CanonicalFileType(settings["output"]["outputFileType"])
    settings["output"]["stopAfter"]       = int(max(0, settings["output"]["stopAfter"]))
    settings["output"]["skipOutput"]      = int(max(1, settings["output"]["skipOutput"]))
    settings["output"]["exportTransferFunction"] = (
        TransferFunctionName(settings["output"].get("transferFunction"))
        if settings["output"].get("overrideTransferFunction") else
        "sRGB / Display P3"
    )
    settings["output"]["outputMetadataParms"] = ExportMetadataParms(
        settings["output"]["outputFileType"],
        settings["output"]["exportTransferFunction"],
    )
    settings["output"]["blendInLinear"] = settings["render"]["blendInLinear"]
    return settings

def BlendModeName(mode):
    if mode is None:
        return "None"

    for name in dir(BlendFunction):
        if name.startswith("_"):
            continue
        if getattr(BlendFunction, name) is mode:
            return name.title().replace("Minmax", "Min/Max").replace("Maxmin", "Max/Min")

    return getattr(mode, "__name__", str(mode))

def FormatBool(value):
    return "Yes" if value else "No"

def FormatTransferSetting(enabled, transferName):
    transferName = TransferFunctionName(transferName)
    return f"{transferName} (override)" if enabled else f"{transferName} (default)"

def FormatOutputName(outSettings):
    return outSettings["outputFileName"]

def RenderModeName(renderSettings):
    return {
        0: "Gather",
        1: "Pair",
        2: "Stack",
    }.get(renderSettings.get("path"), "Gather")

def OutputResolutionText(inpSettings, imageFilenames, inputIndices):
    overrideSize = inpSettings.get("resolutionOverrideSize")
    if overrideSize:
        return f"{overrideSize[0]}x{overrideSize[1]}"

    if imageFilenames and inputIndices:
        try:
            with Image.open(imageFilenames[inputIndices[0]]) as img:
                return f"{img.width}x{img.height}"
        except OSError:
            return "Unknown"

    return "Unknown"

def WriteLogSection(logger, title, rows):
    logger.Log(f"[{title}]")
    for label, value in rows:
        if value is None or value == "":
            continue
        logger.Log(f"    {label}: {value}")
    logger.LogLine()

def WriteSettingsToFile(logger, settings, imageFilenames = None, inputIndices = None, frameCount = None):
    inpSettings = settings["input"]
    blendSettings = settings["blend"]
    outSettings = settings["output"]
    renderSettings = settings["render"]

    imageFilenames = imageFilenames or []
    inputIndices = inputIndices or []
    outputMode = "Final blend only" if outSettings.get("onlyExportFinalFrame", False) else "Image sequence"
    inputCurve = (
        FormatTransferSetting(True, inpSettings["transferFunctionOverride"])
        if inpSettings.get("transferFunctionOverride") else
        "Detected from image metadata"
    )
    resolution = OutputResolutionText(inpSettings, imageFilenames, inputIndices)
    saveOptions = {
        key: value
        for key, value in outSettings.get("outputParms", {}).items()
        if key not in ("icc_profile", "exif")
    }
    blendRows = [
        ("Mode", RenderModeName(renderSettings)),
        ("Blend", BlendModeName(blendSettings.get("mode"))),
    ]
    if renderSettings["path"] == 0:
        blendRows.append(("Spread", f"{blendSettings['decay']:.3f}"))
    elif renderSettings["path"] == 1:
        blendRows.append(("Shift", renderSettings.get("pairOffset", -1)))
    elif renderSettings["path"] == 2:
        blendRows.append(("Size", renderSettings["windowSize"] + 1))
    blendRows.extend((
        ("Gain", f"{blendSettings['scale']:.3f}"),
        ("Lift", f"{blendSettings['lift']:.3f}"),
        ("Intensity", f"{blendSettings['opacity']:.3f}"),
        ("Blend in Linear", FormatBool(renderSettings.get("blendInLinear", True))),
        ("Middle Gray", f"{blendSettings['middleGray']:.3f}"),
    ))

    logger.LogBar()
    logger.Log("Render Settings")
    logger.LogLine()
    WriteLogSection(logger, "Input", (
        ("Frames", len(inputIndices)),
        ("Input curve", inputCurve),
        ("Mixed resolutions", "Some images will be resized" if inpSettings.get("mixedDimensions") else None),
    ))
    WriteLogSection(logger, "Blend", blendRows)
    WriteLogSection(logger, "Export", (
        ("Mode", outputMode),
        ("Folder", outSettings["outputDirectory"]),
        ("Filename", FormatOutputName(outSettings)),
        ("Filetype", outSettings["outputFileType"]),
        ("Resolution", resolution),
        ("Export Scaling", inpSettings["resizeFilter"]),
        ("Export every", f"{outSettings['skipOutput']} frame(s)"),
        ("Save options", saveOptions if saveOptions else "Default"),
        ("Output curve", FormatTransferSetting(bool(outSettings.get("overrideTransferFunction")), outSettings.get("exportTransferFunction", "sRGB / Display P3"))),
    ))
    logger.LogBar()

def GetFilenames(settings, logger):
    if settings.get("inputFilenames") is not None:
        imageFilenames = list(settings["inputFilenames"])
        if not imageFilenames:
            msg = "No input files in render list."
            logger.PrintLogError(msg)
            raise FileNotFoundError(msg)
        missingFilenames = [filename for filename in imageFilenames if not os.path.isfile(filename)]
        if missingFilenames:
            msg = f"Input file not found: {missingFilenames[0]}"
            if len(missingFilenames) > 1:
                msg += f" ({len(missingFilenames) - 1} more missing file(s))"
            logger.PrintLogError(msg)
            raise FileNotFoundError(msg)
        return imageFilenames

    imageFilenames = FindFilenames(settings["inputDirectory"], settings["inputFileType"])
    excludedFilenames = settings.get("excludedFilenames") or set()
    if excludedFilenames:
        imageFilenames = [
            filename for filename in imageFilenames
            if os.path.normcase(os.path.basename(filename)) not in excludedFilenames
        ]
    if not imageFilenames:
        extensions = ", ".join(f".{extension}" for extension in FileTypeExtensions(settings["inputFileType"]))
        msg = f"No {extensions} files found in \"{settings["inputDirectory"]}\""
        logger.PrintLogError(msg)
        raise FileNotFoundError(msg)
    return imageFilenames

def InputFrameIndices(imageCount, inpSettings):
    if inpSettings.get("inputIndices") is not None:
        return [
            index
            for index in inpSettings["inputIndices"]
            if 0 <= index < imageCount
        ]

    return list(range(inpSettings["startAt"], imageCount, inpSettings["skipInput"]))

def RenderFrameCount(inputIndices, renderSettings, stopAfter):
    if not inputIndices:
        return 0

    frameCount = len(inputIndices)
    return int(min(frameCount, stopAfter))

def RenderPathDescription(renderSettings):
    renderPath = renderSettings["path"]
    if renderPath == 1:
        offset = int(renderSettings.get("pairOffset", 0))
        sign = "+" if offset >= 0 else ""
        return f"Pair (n{sign}{offset})"
    if renderPath == 2:
        return f"Stack ({renderSettings['windowSize'] + 1} frames)"
    return "Gather"

def ReadRenderImage(imageFilenames, imageIndex, logger, inpSettings, previewRenderScale, overrideTargetSize, expectedShape):
    targetSize = overrideTargetSize
    if targetSize is None and expectedShape is not None:
        targetSize = (expectedShape[1], expectedShape[0])

    return ReadImage(
        imageFilenames[imageIndex],
        logger,
        previewRenderScale,
        inpSettings.get("transferFunctionOverride"),
        targetSize,
        inpSettings.get("resizeFilter", "Lanczos"),
        inpSettings.get("blendInLinear", True),
    )

def ApplyModeBlend(currentImg, previousImg, blendSettings, blendModeId = None):
    if previousImg is None:
        return currentImg

    if blendModeId is not None:
        return bnc.BlendPair(currentImg, previousImg, blendModeId, blendSettings["opacity"], blendSettings["middleGray"])

    if blendSettings["mode"] is None:
        return bnc.AlphaBlend(previousImg, currentImg, blendSettings["opacity"])

    return blendSettings["mode"](currentImg, previousImg)

def ApplyPairBlendAndComposite(currentImg, previousImg, blendSettings, blendModeId):
    if previousImg is None:
        return currentImg

    if blendModeId is not None:
        return bnc.BlendPairAndComposite(
            currentImg,
            previousImg,
            blendModeId,
            blendSettings["scale"],
            blendSettings["lift"],
            blendSettings["opacity"],
            blendSettings["middleGray"],
        )

    blendResult = ApplyModeBlend(currentImg, previousImg, blendSettings)
    return ApplyFinalComposite(blendResult, currentImg, blendSettings)

def ApplyFinalComposite(blendResult, currentImg, blendSettings, blendModeId = None):
    needsAdjustment = blendSettings["scale"] != 1.0 or blendSettings["lift"] != 0.0
    if blendResult is currentImg and not needsAdjustment:
        return currentImg
    if needsAdjustment:
        blendResult = bnc.ScaleOffset(blendResult, blendSettings["scale"], blendSettings["lift"])
    if blendModeId == bnc.BLEND_MODE_NONE:
        return blendResult
    return bnc.AlphaBlend(currentImg, blendResult, blendSettings["opacity"])

def ApplyStackBlend(imageStack, blendSettings, blendModeId = None):
    if not imageStack:
        return None

    blended = imageStack[0]
    for image in imageStack[1:]:
        blended = ApplyModeBlend(image, blended, blendSettings, blendModeId)
    return blended

def RenderAccumulatorPath(currentFrame, inputIndices, imageFilenames, logger, inpSettings, blendSettings, blendModeId, renderState, previewRenderScale, overrideTargetSize):
    imageIndex = inputIndices[currentFrame]
    currentImg = ReadRenderImage(
        imageFilenames,
        imageIndex,
        logger,
        inpSettings,
        previewRenderScale,
        overrideTargetSize,
        renderState.get("expectedShape"),
    )

    if renderState.get("blendImg") is None:
        renderState["blendImg"] = currentImg
        renderState["expectedShape"] = currentImg.shape
    elif blendModeId is not None:
        renderState["blendImg"], currentImg = bnc.BlendAndComposite(
            currentImg,
            renderState["blendImg"],
            blendModeId,
            blendSettings["decay"],
            blendSettings["scale"],
            blendSettings["lift"],
            blendSettings["opacity"],
            blendSettings["middleGray"],
        )
    else:
        renderState["blendImg"] = bnc.AlphaBlend(
            currentImg,
            blendSettings["mode"](currentImg, renderState["blendImg"]),
            blendSettings["decay"],
        )
        currentImg = ApplyFinalComposite(renderState["blendImg"], currentImg, blendSettings)

    return currentImg

def RenderPairPath(currentFrame, frameCount, inputIndices, imageFilenames, logger, inpSettings, blendSettings, renderSettings, blendModeId, renderState, previewRenderScale, overrideTargetSize):
    imageIndex = inputIndices[currentFrame]
    currentImg = ReadRenderImage(
        imageFilenames,
        imageIndex,
        logger,
        inpSettings,
        previewRenderScale,
        overrideTargetSize,
        renderState.get("expectedShape"),
    )

    if renderState.get("expectedShape") is None:
        renderState["expectedShape"] = currentImg.shape

    pairedFrame = currentFrame + int(renderSettings.get("pairOffset", 0))
    if pairedFrame < 0 or pairedFrame >= frameCount:
        return currentImg

    pairedImg = ReadRenderImage(
        imageFilenames,
        inputIndices[pairedFrame],
        logger,
        inpSettings,
        previewRenderScale,
        overrideTargetSize,
        renderState.get("expectedShape"),
    )
    return ApplyPairBlendAndComposite(currentImg, pairedImg, blendSettings, blendModeId)

def RenderStackPath(currentFrame, inputIndices, imageFilenames, logger, inpSettings, blendSettings, blendModeId, renderState, previewRenderScale, overrideTargetSize, lookbackFrames):
    imageStack = renderState.setdefault("imageStack", [])
    imageIndex = inputIndices[currentFrame]
    image = ReadRenderImage(
        imageFilenames,
        imageIndex,
        logger,
        inpSettings,
        previewRenderScale,
        overrideTargetSize,
        renderState.get("expectedShape"),
    )
    if renderState.get("expectedShape") is None:
        renderState["expectedShape"] = image.shape

    imageStack.append(image)
    maxStackLength = lookbackFrames + 1
    while len(imageStack) > maxStackLength:
        imageStack.pop(0)

    blendResult = ApplyStackBlend(imageStack[::-1], blendSettings, blendModeId)
    return ApplyFinalComposite(blendResult, imageStack[-1], blendSettings, blendModeId)

def RenderPathFrame(currentFrame, frameCount, inputIndices, imageFilenames, logger, settings, renderState, blendModeId, previewRenderScale, overrideTargetSize):
    inpSettings = settings["input"]
    blendSettings = settings["blend"]
    renderSettings = settings["render"]
    renderPath = renderSettings["path"]

    if renderPath == 1:
        return RenderPairPath(
            currentFrame,
            frameCount,
            inputIndices,
            imageFilenames,
            logger,
            inpSettings,
            blendSettings,
            renderSettings,
            blendModeId,
            renderState,
            previewRenderScale,
            overrideTargetSize,
        )

    if renderPath == 2:
        return RenderStackPath(
            currentFrame,
            inputIndices,
            imageFilenames,
            logger,
            inpSettings,
            blendSettings,
            blendModeId,
            renderState,
            previewRenderScale,
            overrideTargetSize,
            renderSettings["windowSize"],
        )

    return RenderAccumulatorPath(
        currentFrame,
        inputIndices,
        imageFilenames,
        logger,
        inpSettings,
        blendSettings,
        blendModeId,
        renderState,
        previewRenderScale,
        overrideTargetSize,
    )

def BlendAndExport(settings, onLog = None, onProgress = None, onFps = None, onRemaining = None, onPreview = None, shouldCancel = None, shouldPause = None, printToConsole = True, exportFrames = True, writeLog = True):

    startTimeSequence = time.time()

    settings = ClampSettings(settings)

    inpSettings = settings["input"]
    blendSettings = settings["blend"]
    outSettings = settings["output"]
    renderSettings = settings["render"]
    blendModeId = BlendModeId(blendSettings["mode"])

    if exportFrames or writeLog:
        if not os.path.exists(outSettings["outputDirectory"]):
            os.makedirs(outSettings["outputDirectory"])

    loggerContext = (
        Logger(outSettings["outputDirectory"], LOG_FILENAME, onPrint = onLog, printToConsole = printToConsole)
        if writeLog else
        CallbackLogger(onLog) if onLog else NullLogger()
    )

    with loggerContext as logger:
        imageFilenames = GetFilenames(inpSettings, logger)

        if inpSettings.get("reverse"):
            imageFilenames = imageFilenames[::-1]

        stopAfter = outSettings["stopAfter"] if outSettings["stopAfter"] else np.inf

        startTimeFrame = time.time()
        elapsedTime = []
        inputIndices = InputFrameIndices(len(imageFilenames), inpSettings)
        frameCount = RenderFrameCount(inputIndices, renderSettings, stopAfter)
        WriteSettingsToFile(logger, settings, imageFilenames, inputIndices, frameCount)

        if frameCount <= 0:
            msg = (
                f"startAt is {inpSettings["startAt"]}, but only "
                f"{len(imageFilenames)} {inpSettings["inputFileType"]} files were found."
            )
            logger.PrintLogError(msg)
            raise ValueError(msg)

        renderState = {}
        previewRenderScale = max(1, int(settings.get("preview", {}).get("renderScale", 1)))
        overrideTargetSize = inpSettings.get("resolutionOverrideSize")
        if overrideTargetSize:
            overrideTargetSize = (
                max(1, overrideTargetSize[0] // previewRenderScale),
                max(1, overrideTargetSize[1] // previewRenderScale),
            )

        logger.PrintLogLine()
        logger.PrintLog("Compiling Sequence...")
        logger.PrintLog(f"Render mode: {RenderModeName(renderSettings)}")
        logger.PrintLogBar()
        ReportProgress(onProgress, 0, frameCount)

        for currentFrame in range(frameCount):
            CheckCancelled(shouldCancel, logger)
            if CheckPaused(shouldPause, shouldCancel, logger):
                startTimeFrame = time.time()

            currentImg = RenderPathFrame(
                currentFrame,
                frameCount,
                inputIndices,
                imageFilenames,
                logger,
                settings,
                renderState,
                blendModeId,
                previewRenderScale,
                overrideTargetSize,
            )

            logger.PrintLogTime(f"{currentFrame + 1} images blended...")
            ReportProgress(onProgress, currentFrame + 1, frameCount)
            ReportPreview(onPreview, currentImg, currentFrame == frameCount - 1)

            # Track render speed per input frame, even when output is skipped.
            if (len(elapsedTime) >= BUFFER_LENGTH_FPS):
                elapsedTime.pop(0)
            elapsedTime.append(time.time() - startTimeFrame)
            avgTime = sum(elapsedTime) / len(elapsedTime)
            startTimeFrame = time.time()
            fps = 1.0 / avgTime
            secondsRemaining = avgTime * (frameCount - currentFrame - 1)
            ReportFps(onFps, fps)
            ReportRemaining(onRemaining, secondsRemaining)

            if (currentFrame % outSettings["skipOutput"] == 0):

                realFrameNumber = currentFrame // outSettings["skipOutput"]
                realFrameCount = (frameCount - 1) // outSettings["skipOutput"]

                if realFrameNumber < realFrameCount and outSettings["onlyExportFinalFrame"]:
                    continue

                if exportFrames:
                    SaveFrame(currentImg, outSettings, realFrameNumber, logger)

                # log stuff
                logger.PrintLogLine()
                logger.PrintLog(f"[{realFrameNumber + 1}/{realFrameCount + 1}] Frame rendered in {elapsedTime[-1]:.2f} seconds")
                logger.PrintLog(f"~{secondsRemaining:.2f} seconds remaining at {fps:.1f} fps")
                logger.PrintLogBar()

                if realFrameNumber >= realFrameCount:
                    break

        totalElapsedTime = int(time.time() - startTimeSequence)
        hours, remainder = divmod(totalElapsedTime, 3600)
        minutes, seconds = divmod(remainder, 60)

        logger.PrintLogTime(f"Sequence exported in {hours:d}:{minutes:02d}:{seconds:02d}")
        logger.PrintLogLine()
        logger.PrintLogBar()
        logger.PrintLogBar()

# ============================================================ #
