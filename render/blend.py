# ============================================================ #
# Blending and Color Conversion
# ============================================================ #

import sys

import numpy as np
from numba import njit, prange

NUMBA_CACHE = not (getattr(sys, "frozen", False) or "__compiled__" in globals())

INV_255 = 1.0 / 255.0
INV_12_92 = 1.0 / 12.92
INV_2_4 = 1.0 / 2.4
ADOBE_RGB_GAMMA = 563.0 / 256.0
INV_ADOBE_RGB_GAMMA = 1.0 / ADOBE_RGB_GAMMA
INV_1_8 = 1.0 / 1.8
INV_1_055 = 1.0 / 1.055
LINEAR_0_5 = 0.5
PROPHOTO_LINEAR_LIMIT = 16.0 / 512.0
PROPHOTO_ENCODE_LIMIT = 1.0 / 512.0

BLEND_MODE_NONE = 0
BLEND_MODE_MIN = 1
BLEND_MODE_MAX = 2
BLEND_MODE_SCREEN = 3
BLEND_MODE_ADD = 4
BLEND_MODE_SUBTRACT = 5
BLEND_MODE_MULTIPLY = 6
BLEND_MODE_DIVIDE = 7
BLEND_MODE_OVERLAY = 8
BLEND_MODE_UNDERLAY = 9
BLEND_MODE_MINMAX = 10
BLEND_MODE_MAXMIN = 11
BLEND_MODE_ADDSUB = 12
BLEND_MODE_SUBADD = 13

TRANSFER_SRGB = 0
TRANSFER_GAMMA22 = 1
TRANSFER_PROPHOTO = 2
TRANSFER_LINEAR = 3

SRGB_TO_LINEAR_LUT = np.array(
    [
        (value / 255.0) / 12.92
        if value / 255.0 <= 0.04045 else
        (((value / 255.0) + 0.055) / 1.055) ** 2.4
        for value in range(256)
    ],
    dtype = np.float32,
)

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def SrgbToLinear(rgb):
    h, w, c = rgb.shape
    out = np.empty((h, w, c), dtype = np.float32)
    for i in prange(h):
        for j in range(w):
            for k in range(c):
                out[i, j, k] = SRGB_TO_LINEAR_LUT[rgb[i, j, k]]
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def LinearToSrgb(rgb):
    h, w, c = rgb.shape
    out = np.empty_like(rgb, dtype=np.float32)
    for i in prange(h):
        for j in range(w):
            for k in range(c):
                v = rgb[i, j, k]
                if v <= 0.0031308:
                    out[i, j, k] = v * 12.92 * 255.0
                else:
                    out[i, j, k] = (1.055 * (v ** INV_2_4) - 0.055) * 255.0
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def Gamma22ToLinear(rgb):
    h, w, c = rgb.shape
    out = np.empty_like(rgb, dtype=np.float32)
    for i in prange(h):
        for j in range(w):
            for k in range(c):
                out[i, j, k] = (rgb[i, j, k] * INV_255) ** ADOBE_RGB_GAMMA
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def LinearToGamma22(rgb):
    h, w, c = rgb.shape
    out = np.empty_like(rgb, dtype=np.float32)
    for i in prange(h):
        for j in range(w):
            for k in range(c):
                v = rgb[i, j, k]
                if v <= 0.0:
                    out[i, j, k] = 0.0
                else:
                    out[i, j, k] = (v ** INV_ADOBE_RGB_GAMMA) * 255.0
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def Gamma18ToLinear(rgb):
    h, w, c = rgb.shape
    out = np.empty_like(rgb, dtype=np.float32)
    for i in prange(h):
        for j in range(w):
            for k in range(c):
                out[i, j, k] = (rgb[i, j, k] * INV_255) ** 1.8
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def LinearToGamma18(rgb):
    h, w, c = rgb.shape
    out = np.empty_like(rgb, dtype=np.float32)
    for i in prange(h):
        for j in range(w):
            for k in range(c):
                v = rgb[i, j, k]
                if v <= 0.0:
                    out[i, j, k] = 0.0
                else:
                    out[i, j, k] = (v ** INV_1_8) * 255.0
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def ProPhotoToLinear(rgb):
    h, w, c = rgb.shape
    out = np.empty_like(rgb, dtype=np.float32)
    for i in prange(h):
        for j in range(w):
            for k in range(c):
                v = rgb[i, j, k] * INV_255
                if v < PROPHOTO_LINEAR_LIMIT:
                    out[i, j, k] = v / 16.0
                else:
                    out[i, j, k] = v ** 1.8
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def LinearToProPhoto(rgb):
    h, w, c = rgb.shape
    out = np.empty_like(rgb, dtype=np.float32)
    for i in prange(h):
        for j in range(w):
            for k in range(c):
                v = rgb[i, j, k]
                if v < PROPHOTO_ENCODE_LIMIT:
                    out[i, j, k] = v * 16.0 * 255.0
                else:
                    out[i, j, k] = (v ** INV_1_8) * 255.0
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def LinearTransferToLinear(rgb):
    h, w, c = rgb.shape
    out = np.empty((h, w, c), dtype = np.float32)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                out[y, x, k] = rgb[y, x, k] * INV_255
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def Uint8ToNormalizedFloat(rgb):
    h, w, c = rgb.shape
    out = np.empty((h, w, c), dtype=np.float32)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                out[y, x, k] = rgb[y, x, k] * INV_255
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def LinearToLinearTransfer(rgb):
    return rgb * 255.0

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def AlphaBlend(background, foreground, alpha):
    if alpha == 1.0:
        return foreground.copy()
    if alpha == 0.0:
        return background.copy()
    h, w, c = background.shape
    out = np.empty_like(background)
    invAlpha = 1.0 - alpha
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                out[y, x, k] = alpha * foreground[y, x, k] + invAlpha * background[y, x, k]
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def ScaleOffset(rgb, scale, offset, absoluteValues):
    h, w, c = rgb.shape
    out = np.empty_like(rgb)
    if scale == 0.0:
        for y in prange(h):
            for x in range(w):
                for k in range(c):
                    value = offset
                    if absoluteValues and value < 0.0:
                        value = -value
                    out[y, x, k] = value
        return out

    for y in prange(h):
        for x in range(w):
            for k in range(c):
                value = (rgb[y, x, k] * scale) + offset
                if absoluteValues and value < 0.0:
                    value = -value
                out[y, x, k] = value
    return out

@njit(fastmath = True, cache = NUMBA_CACHE)
def BlendValue(background, foreground, mode, middleGray):
    if mode == BLEND_MODE_MIN:
        return background if background < foreground else foreground
    if mode == BLEND_MODE_MAX:
        return background if background > foreground else foreground
    if mode == BLEND_MODE_SCREEN:
        return 1.0 - ((1.0 - background) * (1.0 - foreground))
    if mode == BLEND_MODE_ADD:
        v = background + foreground
        return 1.0 if v > 1.0 else v
    if mode == BLEND_MODE_SUBTRACT:
        v = background - foreground
        return 0.0 if v < 0.0 else v
    if mode == BLEND_MODE_MULTIPLY:
        return background * foreground
    if mode == BLEND_MODE_DIVIDE:
        if foreground <= 0.000001:
            return 1.0
        v = background / foreground
        return 1.0 if v > 1.0 else v
    if mode == BLEND_MODE_OVERLAY:
        if middleGray == LINEAR_0_5:
            if background <= LINEAR_0_5:
                return 2.0 * background * foreground
            return 1.0 - (2.0 * (1.0 - background) * (1.0 - foreground))
        if middleGray <= 0.0:
            if background <= 0.0:
                return foreground
            return 1.0 - ((1.0 - background) * (1.0 - foreground))
        if middleGray >= 1.0:
            return background * foreground
        if background <= middleGray:
            return (background * foreground) / middleGray
        return 1.0 - (((1.0 - background) * (1.0 - foreground)) / (1.0 - middleGray))
    if mode == BLEND_MODE_UNDERLAY:
        if middleGray == LINEAR_0_5:
            if foreground <= LINEAR_0_5:
                return 2.0 * foreground * background
            return 1.0 - (2.0 * (1.0 - foreground) * (1.0 - background))
        if middleGray <= 0.0:
            if foreground <= 0.0:
                return background
            return 1.0 - ((1.0 - foreground) * (1.0 - background))
        if middleGray >= 1.0:
            return foreground * background
        if foreground <= middleGray:
            return (foreground * background) / middleGray
        return 1.0 - (((1.0 - foreground) * (1.0 - background)) / (1.0 - middleGray))
    if mode == BLEND_MODE_MINMAX:
        if background > middleGray:
            return background if background < foreground else foreground
        return background if background > foreground else foreground
    if mode == BLEND_MODE_MAXMIN:
        if background < middleGray:
            return background if background < foreground else foreground
        return background if background > foreground else foreground
    if mode == BLEND_MODE_ADDSUB:
        if background < foreground:
            v = background + foreground
            return 1.0 if v > 1.0 else v
        v = background - foreground
        return 0.0 if v < 0.0 else v
    if mode == BLEND_MODE_SUBADD:
        if background > foreground:
            v = background + foreground
            return 1.0 if v > 1.0 else v
        v = background - foreground
        return 0.0 if v < 0.0 else v
    return foreground

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def BlendAndComposite(current, accumulated, mode, decay, scale, offset, absoluteValues, opacity, middleGray):
    h, w, c = current.shape
    adjust = scale != 1.0 or offset != 0.0 or absoluteValues
    zeroScale = scale == 0.0

    if not adjust and (mode == BLEND_MODE_NONE or opacity == 1.0):
        output = np.empty_like(current)
        if mode == BLEND_MODE_NONE:
            invOpacity = 1.0 - opacity
            for y in prange(h):
                for x in range(w):
                    for k in range(c):
                        output[y, x, k] = opacity * current[y, x, k] + invOpacity * accumulated[y, x, k]
            return output, output

        invDecay = 1.0 - decay
        for y in prange(h):
            for x in range(w):
                for k in range(c):
                    currentValue = current[y, x, k]
                    blendedValue = BlendValue(currentValue, accumulated[y, x, k], mode, middleGray)
                    output[y, x, k] = decay * blendedValue + invDecay * currentValue
        return output, output

    newAccumulated = np.empty_like(current)
    if mode == BLEND_MODE_NONE:
        invOpacity = 1.0 - opacity
        output = np.empty_like(current)
        for y in prange(h):
            for x in range(w):
                for k in range(c):
                    accumulatedValue = opacity * current[y, x, k] + invOpacity * accumulated[y, x, k]
                    newAccumulated[y, x, k] = accumulatedValue
                    if zeroScale:
                        adjustedValue = offset
                    elif adjust:
                        adjustedValue = (accumulatedValue * scale) + offset
                    else:
                        adjustedValue = accumulatedValue
                    if absoluteValues and adjustedValue < 0.0:
                        adjustedValue = -adjustedValue
                    output[y, x, k] = adjustedValue
        return newAccumulated, output

    output = np.empty_like(current)
    invDecay = 1.0 - decay
    invOpacity = 1.0 - opacity
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                currentValue = current[y, x, k]
                blendedValue = BlendValue(currentValue, accumulated[y, x, k], mode, middleGray)
                accumulatedValue = decay * blendedValue + invDecay * currentValue
                if zeroScale:
                    adjustedValue = offset
                elif adjust:
                    adjustedValue = (accumulatedValue * scale) + offset
                else:
                    adjustedValue = accumulatedValue
                if absoluteValues and adjustedValue < 0.0:
                    adjustedValue = -adjustedValue
                newAccumulated[y, x, k] = accumulatedValue
                output[y, x, k] = opacity * adjustedValue + invOpacity * currentValue
    return newAccumulated, output

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def AddWeightedImage(accumulated, image, weight):
    h, w, c = image.shape
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                accumulated[y, x, k] += image[y, x, k] * weight

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def BlendPair(current, previous, mode, opacity, middleGray):
    h, w, c = current.shape
    out = np.empty_like(current)

    if mode == BLEND_MODE_NONE:
        invOpacity = 1.0 - opacity
        for y in prange(h):
            for x in range(w):
                for k in range(c):
                    out[y, x, k] = opacity * current[y, x, k] + invOpacity * previous[y, x, k]
        return out

    for y in prange(h):
        for x in range(w):
            for k in range(c):
                out[y, x, k] = BlendValue(current[y, x, k], previous[y, x, k], mode, middleGray)
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def BlendPairAndComposite(current, previous, mode, scale, offset, absoluteValues, opacity, middleGray):
    h, w, c = current.shape
    out = np.empty_like(current)
    adjust = scale != 1.0 or offset != 0.0 or absoluteValues
    zeroScale = scale == 0.0

    if mode == BLEND_MODE_NONE:
        invOpacity = 1.0 - opacity
        for y in prange(h):
            for x in range(w):
                for k in range(c):
                    blendedValue = opacity * current[y, x, k] + invOpacity * previous[y, x, k]
                    if zeroScale:
                        adjustedValue = offset
                    elif adjust:
                        adjustedValue = (blendedValue * scale) + offset
                    else:
                        adjustedValue = blendedValue
                    if absoluteValues and adjustedValue < 0.0:
                        adjustedValue = -adjustedValue
                    out[y, x, k] = adjustedValue
        return out

    invOpacity = 1.0 - opacity
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                currentValue = current[y, x, k]
                blendedValue = BlendValue(currentValue, previous[y, x, k], mode, middleGray)
                if zeroScale:
                    adjustedValue = offset
                elif adjust:
                    adjustedValue = (blendedValue * scale) + offset
                else:
                    adjustedValue = blendedValue
                if absoluteValues and adjustedValue < 0.0:
                    adjustedValue = -adjustedValue
                out[y, x, k] = opacity * adjustedValue + invOpacity * currentValue
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def LinearToTransferUint8(rgb, transfer):
    h, w, c = rgb.shape
    out = np.empty((h, w, c), dtype=np.uint8)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                v = rgb[y, x, k]

                if transfer == TRANSFER_SRGB:
                    if v <= 0.0031308:
                        encoded = v * 12.92 * 255.0
                    else:
                        encoded = (1.055 * (v ** INV_2_4) - 0.055) * 255.0
                elif transfer == TRANSFER_GAMMA22:
                    encoded = 0.0 if v <= 0.0 else (v ** INV_ADOBE_RGB_GAMMA) * 255.0
                elif transfer == TRANSFER_PROPHOTO:
                    if v < PROPHOTO_ENCODE_LIMIT:
                        encoded = v * 16.0 * 255.0
                    else:
                        encoded = (v ** INV_1_8) * 255.0
                else:
                    encoded = v * 255.0

                if encoded <= 0.0:
                    out[y, x, k] = 0
                elif encoded >= 255.0:
                    out[y, x, k] = 255
                else:
                    out[y, x, k] = np.uint8(encoded)
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def ScreenBlend(background, foreground):
    h, w, c = background.shape
    out = np.empty_like(background)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                a = 1.0 - background[y, x, k]
                b = 1.0 - foreground[y, x, k]
                out[y, x, k] = 1.0 - (a * b)
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def AddBlend(background, foreground):
    h, w, c = background.shape
    out = np.empty_like(background)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                v = background[y, x, k] + foreground[y, x, k]
                out[y, x, k] = 1.0 if v > 1.0 else v
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def SubtractBlend(background, foreground):
    h, w, c = background.shape
    out = np.empty_like(background)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                v = background[y, x, k] - foreground[y, x, k]
                out[y, x, k] = 0.0 if v < 0.0 else v
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def MultiplyBlend(background, foreground):
    h, w, c = background.shape
    out = np.empty_like(background)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                out[y, x, k] = background[y, x, k] * foreground[y, x, k]
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def DivideBlend(background, foreground):
    h, w, c = background.shape
    out = np.empty_like(background)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                divisor = foreground[y, x, k]
                if divisor <= 0.000001:
                    out[y, x, k] = 1.0
                else:
                    v = background[y, x, k] / divisor
                    out[y, x, k] = 1.0 if v > 1.0 else v
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def OverlayBlend(background, foreground):
    h, w, c = background.shape
    out = np.empty_like(background)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                a = background[y, x, k]
                b = foreground[y, x, k]
                if a <= LINEAR_0_5:
                    out[y, x, k] = 2.0 * a * b
                else:
                    out[y, x, k] = 1.0 - (2.0 * (1.0 - a) * (1.0 - b))
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def UnderlayBlend(background, foreground):
    h, w, c = background.shape
    out = np.empty_like(background)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                a = background[y, x, k]
                b = foreground[y, x, k]
                if b <= LINEAR_0_5:
                    out[y, x, k] = 2.0 * a * b
                else:
                    out[y, x, k] = 1.0 - (2.0 * (1.0 - a) * (1.0 - b))
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def MaxBlend(background, foreground):
    h, w, c = background.shape
    out = np.empty_like(background)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                a = background[y, x, k]
                b = foreground[y, x, k]
                out[y, x, k] = a if a > b else b
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def MinBlend(background, foreground):
    h, w, c = background.shape
    out = np.empty_like(background)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                a = background[y, x, k]
                b = foreground[y, x, k]
                out[y, x, k] = a if a < b else b
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def MinMaxBlend(background, foreground):
    h, w, c = background.shape
    out = np.empty_like(background)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                a = background[y, x, k]
                b = foreground[y, x, k]
                if a > LINEAR_0_5:
                    out[y, x, k] = a if a < b else b
                else:
                    out[y, x, k] = a if a > b else b
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def MaxMinBlend(background, foreground):
    h, w, c = background.shape
    out = np.empty_like(background)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                a = background[y, x, k]
                b = foreground[y, x, k]
                if a < LINEAR_0_5:
                    out[y, x, k] = a if a < b else b
                else:
                    out[y, x, k] = a if a > b else b
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def AddSubBlend(background, foreground):
    h, w, c = background.shape
    out = np.empty_like(background)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                a = background[y, x, k]
                b = foreground[y, x, k]
                if a < b:
                    v = a + b
                    out[y, x, k] = 1.0 if v > 1.0 else v
                else:
                    v = a - b
                    out[y, x, k] = 0.0 if v < 0.0 else v
    return out

@njit(parallel = True, fastmath = True, cache = NUMBA_CACHE)
def SubAddBlend(background, foreground):
    h, w, c = background.shape
    out = np.empty_like(background)
    for y in prange(h):
        for x in range(w):
            for k in range(c):
                a = background[y, x, k]
                b = foreground[y, x, k]
                if a > b:
                    v = a + b
                    out[y, x, k] = 1.0 if v > 1.0 else v
                else:
                    v = a - b
                    out[y, x, k] = 0.0 if v < 0.0 else v
    return out
