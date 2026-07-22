# Stacker

Stacker is a desktop image sequence blender for creating trails, motion effects, and experimental composites. It can make classic star trails, shadow trails, frame-to-frame motion extractions, rolling stack blends, and stranger looks when you get creative with the settings.

It is built for working through image sequences quickly: load images, set an export/blend range, scrub the timeline, tune the blend settings, generate a preview, then export the result.

## Highlights

- Three render modes:
  - **Gather**: an accumulating blend for trails and long-form composites.
  - **Pair**: blends the current frame with another frame in time, useful for motion extraction and difference-style looks.
  - **Stack**: blends a fixed-size moving window of frames, with past, future, or centered direction.
- Blend modes including Min, Max, Multiply, Divide, Add, Subtract, Screen, Overlay, Underlay, Add/Sub, Sub/Add, Max/Min, and Min/Max.
- Preview cache with timeline playback and scrubbing.
- Trim ranges, skipped frames, hidden frames, manual list ordering, and project files.
- Per-file transfer-function overrides, linear-light blending, and custom middle gray.
- Export a complete image sequence or only final blend.

## Supported Files

Input:

- JPG
- PNG
- TIFF
- BMP

Export:

- JPG
- PNG
- TIFF
- BMP

## Render Modes

**Gather** builds an accumulator over time. This is the mode for classic trails: each new frame contributes to the running blend, then a final composite controls how strongly the current frame appears in the output.

**Pair** compares or blends two moments in time. The offset can look backward or forward, and temporal blur can soften the paired frames before the blend.

**Stack** blends a fixed window of frames around the current frame. It is a more controlled alternative to Gather when you want a limited trail length or a rolling composite.

## Blend Settings

The Blend tab controls how frames are combined before export. The active render mode changes which mode-specific controls are visible.

### Mode-Specific Settings

**Gather**

- **Spread** controls how strongly each new blended result is folded into the accumulator. Higher values preserve more of the running trail. Lower values make the trail fall away more quickly.

**Pair**

- **Shift** chooses the second frame used for the pair blend. Negative values compare against earlier frames; positive values compare against later frames.
- **Temporal Blur** blends neighboring frames around each paired source frame before the pair blend happens. A value of `0` disables temporal blur.
- **Kernel** controls the weighting shape used by Temporal Blur. Box is a plain average, while Triangle, Semicircle, Gaussian, Cosine, and Exponential give different falloff shapes around the current frame.

**Stack**

- **Size** controls how many neighboring frames are included in the moving stack. Large values can create smoother or longer effects, but they can also use more memory and slow the render.
- **Direction** chooses where the stack gathers frames from: Past, Future, or Centered.

### Shared Blend Settings

- **Preset** loads a built-in or user-saved blend setup. Changing blend controls after loading a preset marks it as modified. Save Preset stores the current blend setup as a user preset.
- **Blend** chooses the mathematical blend mode. `(none) Alpha Only` skips the mode blend and uses alpha compositing only.
- **Gain** multiplies the blended result after the mode-specific blend.
- **Lift** adds or subtracts a constant value after Gain.
- **Absolute Values** folds negative adjusted RGB values back above zero. This is mainly useful for experimental looks and motion-style blends.
- **Intensity** controls the final composite between the current frame and the blended result. Higher values show more of the current frame in the final output.

## Viewport Workflow

Stacker uses three viewport tabs so you can separate source inspection, preview generation, and exported results.

**Input** is where you inspect the source image list. The timeline shows every enabled, readable image, with the active trim range highlighted. Use this tab to scrub through the source sequence, set marks, check image metadata, and decide what should be rendered.

**Preview Cache** shows generated previews. Generate Preview renders into memory instead of writing files to disk, so you can scrub and play back the cached result before committing to an export.

**View Export** shows files found in the export folder that match the current export filename and file type. During export, this tab displays the live export preview if Live Export Preview is enabled.

The viewport supports zooming, panning, fullscreen mode, timeline playback, mark in/out controls, and context-menu options for visibility labels, zoom, copying the displayed image, and opening file information.

## Images Tab

The Images tab builds the render list. The order shown here is the order sent to the renderer.

- **Add Images** adds one or more individual image files. Images are appended to the end of the list.
- **Add Folder** scans a folder and adds all supported image files it finds.
- **Move Up / Move Down** moves the selected image or block of images through the list.
- **Reverse** flips the current file list order.
- **Sort Alphabetically** sorts by filename.
- **Sort Numerically** sorts by detected number order, useful for numbered image sequences.
- **Mark In / Mark Out** sets the trim range from the selected file.
- **Clear Range** removes the active trim range.
- **Sync** links the file list selection and Input timeline position. Selecting a file moves the timeline, and moving the timeline selects the displayed file.
- **Remove** removes the selected image or images from the project list.
- **Remove All** clears the image list after confirmation.
- **Only read every** skips source frames before rendering. Skipped frames remain visible in the list but are not sent to the renderer.

The file list also supports drag-and-drop, manual reordering from the reorder handle, multi-selection, per-file transfer-curve overrides, hiding images from the render, and image info from the context menu.

## Export Tab

The Export tab controls where files are written and how the rendered frames are encoded.

**Output**

- **Folder** chooses the export folder.
- **Filename** sets the base output name. Sequence exports append the frame number automatically; final-blend exports save without the sequence suffix.
- **File type** chooses JPG, PNG, TIFF, or BMP.
- **File export options** opens format-specific save settings.

**Resolution**

- **Export Resolution** sets the output dimensions when Override is enabled. If Override is disabled, Stacker inherits the resolution from the first renderable source image.
- **Export Scaling** chooses the resize filter used when an image must be scaled.

**Blending**

- **Blend in Linear** converts supported transfer curves into linear light before blending. Disabling it blends the encoded values directly and disables transfer-curve overrides.
- **Middle Gray** sets the midpoint used by blend modes that need a middle-gray reference. Enable Override to use a custom value.

**Color**

- **Output Curve** chooses the transfer curve used when encoding exported images. Enable Override to force a specific output curve.

**Export cadence and preview**

- **Only export every** writes every nth rendered frame during sequence export.
- **Live Export Preview** updates the viewport while exporting.

Format-specific options:

- **JPG**: Quality, Optimize, Progressive, and Subsampling.
- **PNG**: Compression and Optimize.
- **TIFF**: Compression.
- **BMP**: no save options.

## Projects And Presets

Stacker projects use the `.stack` extension and save the meaningful render state: file list, trims, disabled files, blend settings, export settings, and color handling.

Presets store blend settings and render-mode-specific controls. Built-in presets ship with the app, and user presets live in the `presets` folder.

## Run From Source

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Start Stacker:

```powershell
python main.py
```

## Requirements

- Python 3
- PySide6
- Pillow
- NumPy
- Numba

Dependencies are listed in `requirements.txt`.

## Status

Stacker is currently unreleased and still in active development.

## License

Stacker is licensed under the MIT License.

Third-party license notes are collected in `LICENSES.txt`.
