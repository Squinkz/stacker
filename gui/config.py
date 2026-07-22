from render.renderer import BlendFunction


BLEND_MODES = {
    "(none) Alpha Only": None,
    "Min (Darken)": BlendFunction.MIN,
    "Max (Lighten)": BlendFunction.MAX,
    "Multiply": BlendFunction.MULTIPLY,
    "Divide": BlendFunction.DIVIDE,
    "Add (Linear Dodge)": BlendFunction.ADD,
    "Subtract (Linear Burn)": BlendFunction.SUBTRACT,
    "Screen": BlendFunction.SCREEN,
    "Overlay": BlendFunction.OVERLAY,
    "Underlay": BlendFunction.UNDERLAY,
    "Add/Sub": BlendFunction.ADDSUB,
    "Sub/Add": BlendFunction.SUBADD,
    "Max/Min": BlendFunction.MAXMIN,
    "Min/Max": BlendFunction.MINMAX,
}

INPUT_TYPES = ["jpg", "png", "tiff", "bmp"]
OUTPUT_TYPES = ["jpg", "png", "tiff", "bmp"]
CONFIG_FILENAME = "stacker.cfg"
