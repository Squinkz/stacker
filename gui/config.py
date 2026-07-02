from render.renderer import BlendFunction


BLEND_MODES = {
    "(none) Alpha Only": None,
    "Min (Darken)": BlendFunction.MIN,
    "Max (Lighten)": BlendFunction.MAX,
    "Screen": BlendFunction.SCREEN,
    "Add": BlendFunction.ADD,
    "Subtract": BlendFunction.SUBTRACT,
    "Multiply": BlendFunction.MULTIPLY,
    "Divide": BlendFunction.DIVIDE,
    "Overlay": BlendFunction.OVERLAY,
    "Underlay": BlendFunction.UNDERLAY,
    "Min/Max": BlendFunction.MINMAX,
    "Max/Min": BlendFunction.MAXMIN,
}

INPUT_TYPES = ["jpg", "png", "tiff", "bmp"]
OUTPUT_TYPES = ["jpg", "png", "tiff", "bmp"]
CONFIG_FILENAME = "stacker.cfg"
