BUILTIN_PRESETS = {
    "Light Trails": {
        "version":    1,
        "name":       "Light Trails",
        "renderMode": "Gather",
        "blend":      "Max (Lighten)",
        "spread":     1.0,
        "scale":      1.0,
        "lift":       0.0,
        "absolute":   False,
        "intensity":  1.00,
    },
    "Shadow Trails": {
        "version":    1,
        "name":       "Shadow Trails",
        "renderMode": "Gather",
        "blend":      "Min (Darken)",
        "spread":     1.0,
        "scale":      1.0,
        "lift":       0.0,
        "absolute":   False,
        "intensity":  1.00,
    },
    "Motion Mask Overlay (linear source)": {
        "version":    1,
        "name":       "Motion Mask Overlay (linear source)",
        "renderMode": "Pair",
        "blend":      "Subtract (Linear Burn)",
        "shift":      -1,
        "blur":       0,
        "kernel":     "Gaussian",
        "scale":      0.5,
        "lift":       0.214,
        "absolute":   False,
        "intensity":  1.0,
    },
    "Motion Mask Overlay (sRGB source)": {
        "version":    1,
        "name":       "Motion Mask Overlay (sRGB source)",
        "renderMode": "Pair",
        "blend":      "Subtract (Linear Burn)",
        "shift":      -1,
        "blur":       0,
        "kernel":     "Gaussian",
        "scale":      0.5,
        "lift":       0.5,
        "absolute":   False,
        "intensity":  1.0,
    },
    "Motion Mask Screen": {
        "version":    1,
        "name":       "Motion Mask Screen",
        "renderMode": "Pair",
        "blend":      "Subtract (Linear Burn)",
        "shift":      -1,
        "blur":       0,
        "kernel":     "Gaussian",
        "scale":      1.0,
        "lift":       0.0,
        "absolute":   True,
        "intensity":  1.0,
    },
}


    # "Template Gather Lighten": {
    #     "version":    1,
    #     "name":       "Template Gather Lighten",
    #     "renderMode": "Gather",
    #     "blend":      "Max (Lighten)",
    #     "spread":     0.92,
    #     "scale":      1.15,
    #     "lift":      -0.08,
    #     "absolute":   False,
    #     "intensity":  0.78,
    # },
    # "Template Pair Overlay": {
    #     "version":    1,
    #     "name":       "Template Pair Overlay",
    #     "renderMode": "Pair",
    #     "blend":      "Overlay",
    #     "shift":      -3,
    #     "blur":       0,
    #     "kernel":     "Gaussian",
    #     "scale":      0.85,
    #     "lift":       0.12,
    #     "absolute":   False,
    #     "intensity":  0.62,
    # },
    # "Template Stack Screen": {
    #     "version":    1,
    #     "name":       "Template Stack Screen",
    #     "renderMode": "Stack",
    #     "blend":      "Screen",
    #     "size":       7,
    #     "direction":  "Past",
    #     "scale":      1.35,
    #     "lift":       0.04,
    #     "absolute":   False,
    #     "intensity":  0.70,
    # },

# Assuming the count includes the original white frame:

# Visible frames	Spread
############################
# 30                0.7563
# 60                0.8717
# 120               0.9342
# 250               0.9680
# 500               0.9839
# 1000              0.9919

# These assume Gather + Max, linear-light blending, and 8-bit sRGB output.