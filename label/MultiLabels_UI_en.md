# MultiLabels_UI

## Main Features

- Load an image folder and browse images using a folder tree structure.
- Display whether each image has been labeled.
- View and assign tags for the current image via:
  - text input + add button
  - selecting tags from `global_tag_tree`.
- Support grouped tags with a tree view of all created tags.
- Auto-save JSON when changes occur, or save manually.
- Convert label data into a `.txt` file for each image.
- Quickly copy all tags from the previous image to the current one.
- Remove tags that are not listed in `default_labels.json` from all images.
- Shorten long image paths in the current image label display to avoid breaking the layout.
- Set the folder tree columns to a better ratio between `Name` and `Status`.

## Data Architecture

- Labels are stored in a `labels.json` file located in the root folder of the image set.
- JSON structure:
  - `label_names`: mapping ID → tag name.
  - `list_image`: list of images with `directory`, `image_name`, `labels`.
- `default_labels.json` contains default tag groups and is loaded when the app starts.
- `labels.json` is created or updated when the folder is loaded.

## Requirements for Building the App on Other Platforms

### General Architecture

- The app must check for and load `default_labels.json` during startup.
- When loading an image folder, it must find and load `labels.json` from the same folder.
- If `labels.json` does not exist, the app should create it with current default tags.
- If `labels.json` exists but lacks tags newly added to `default_labels.json`, it should update `labels.json` accordingly.
- Ensure image paths in `labels.json` are normalized to match the current folder.

### Web UI

- Display default tags clearly and avoid hiding default tags behind menus.
- Provide a tree or list of tag groups that is easy to interact with.
- Tag checkboxes or toggles must synchronize with the currently selected image.
- Default tags should always be visible and prioritized in the UI.
- Maintain auto-save / manual save behavior when syncing JSON data.

### Mobile App

- Prioritize showing default tags instead of hiding them in collapsible menus.
- Add search or filtering for tags to make selection easier on small screens.
- Ensure touch-friendly controls for selecting and deselecting tags.
- Default labels should remain highly visible, not hidden behind nested menus.
- Support offline label saving with `labels.json` stored alongside the image set (or equivalent mobile storage), and sync when needed.

### Cross-platform / Desktop

- Desktop apps should support folder selection via a file picker.
- Handle file paths correctly on Windows, macOS, and Linux.
- Keep `labels.json` in the root image folder or a similarly discoverable location.
- Prefer not to use absolute paths if possible, or normalize them when the folder changes.

## Notes on JSON Checking and Loading

- Always verify `default_labels.json` exists before using it.
- Load `labels.json` from the current image folder:
  - if the file exists, parse the JSON.
  - if parsing fails, reinitialize default data to avoid crashes.
- If `default_labels.json` is corrupted or incomplete, the app should fall back safely and notify the user.
- Save `labels.json` after each change if auto-save is enabled, or when the user explicitly saves.

## Default Tag Visibility Priority

- For web or mobile UI, default tags should be displayed openly, not hidden behind advanced options.
- Default tags should be shown clearly by group so users can assign them easily.
- Avoid designs that require tag assignment only through search; direct lists should still be available.
- When custom tags are created, default tags should remain visible alongside them.

## Extension Suggestions

- Add a filter to show images by labeled / unlabeled status.
- Add tag search inside `global_tag_tree`. not Hiden
- Add dark/light theme support for web/mobile.
- Add export options such as CSV or YAML.
