import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image, ImageTk
import cv2
import numpy as np
import logging
import os
import glob
import platform
import subprocess

# --- File-Level Comment ---
"""
image_viewer_tkinter.py

A Tkinter-based desktop application for viewing images from a directory and processing them
to detect QR codes and ChArUco boards. Includes zoom/pan functionality for the
processed image view.
"""

# --- Optional Imports with Logging ---
try:
    from detect_and_draw_qr import detect_and_draw_qrcodes
except ImportError:
    # This log message is already good.
    logging.error("Failed to import detect_and_draw_qrcodes from detect_and_draw_qr. QR detection will be skipped.")
    detect_and_draw_qrcodes = None

try:
    from charuco_detector import detect_charuco_board
except ImportError:
    logging.error("Failed to import detect_charuco_board from charuco_detector")
    detect_charuco_board = None

# --- Logging Configuration ---
# Ensure logging is configured before any log messages are emitted.
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s' # Added filename and lineno
)


class ImageViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Viewer and Processor")
        # --- Application State Variables ---
        self.image_paths = []  # List of paths to images in the selected directory
        self.current_image_index = -1  # Index of the currently displayed image in image_paths

        # ChArUco board parameters (using defaults)
        self.CHARUCO_SQUARES_X = 5
        self.CHARUCO_SQUARES_Y = 5
        self.CHARUCO_SQUARE_LENGTH_MM = 10.0
        self.CHARUCO_MARKER_LENGTH_MM = 7.0
        self.CHARUCO_DICTIONARY_NAME = "DICT_4X4_100"
        
        logging.info(
            f"ChArUco Parameters: X={self.CHARUCO_SQUARES_X}, Y={self.CHARUCO_SQUARES_Y}, "
            f"SqL={self.CHARUCO_SQUARE_LENGTH_MM}mm, MkL={self.CHARUCO_MARKER_LENGTH_MM}mm, Dict={self.CHARUCO_DICTIONARY_NAME}"
        )

        # Transformation state for the processed image view
        self.current_zoom_level = 1.0
        self.current_offset_x = 0.0
        self.current_offset_y = 0.0
        self.max_zoom_level = 5.0
        self.min_zoom_level = 0.5
        self.zoom_increment = 0.2
        
        # Store PhotoImage objects to prevent garbage collection
        self.original_photo_image = None
        self.processed_photo_image = None
        self.raw_processed_image_cv = None # Store the raw OpenCV image for reprocessing zoom/pan

        # For pan
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._canvas_image_x = 0 # Top-left x of image on canvas
        self._canvas_image_y = 0 # Top-left y of image on canvas

        self.init_ui()

    def init_ui(self):
        """Initializes and lays out the UI elements for the Tkinter application."""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # --- Controls Frame ---
        controls_frame = ttk.Frame(main_frame)
        controls_frame.grid(row=0, column=0, columnspan=2, pady=5, sticky=tk.EW)

        self.pick_directory_button = ttk.Button(
            controls_frame,
            text="Pick Image Directory",
            command=self.pick_directory_clicked
        )
        self.pick_directory_button.pack(side=tk.LEFT, padx=5)

        # --- Image Display Frame ---
        images_frame = ttk.Frame(main_frame)
        images_frame.grid(row=1, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E, tk.N, tk.S))
        images_frame.columnconfigure(0, weight=1)
        images_frame.columnconfigure(1, weight=1)
        images_frame.rowconfigure(0, weight=1) # Changed from 1 to 0 as row 0 contains images

        # Original Image
        original_image_frame = ttk.LabelFrame(images_frame, text="Original Image", padding=5)
        original_image_frame.grid(row=0, column=0, padx=5, pady=5, sticky=(tk.W, tk.E, tk.N, tk.S))
        original_image_frame.columnconfigure(0, weight=1)
        original_image_frame.rowconfigure(0, weight=1)

        self.original_image_label = ttk.Label(original_image_frame, text="Original image will appear here.", anchor=tk.CENTER)
        self.original_image_label.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Processed Image (using Canvas for zoom/pan)
        processed_image_frame = ttk.LabelFrame(images_frame, text="Processed Image (Scroll to zoom, Drag to pan)", padding=5)
        processed_image_frame.grid(row=0, column=1, padx=5, pady=5, sticky=(tk.W, tk.E, tk.N, tk.S))
        processed_image_frame.columnconfigure(0, weight=1)
        processed_image_frame.rowconfigure(0, weight=1)

        self.processed_image_canvas = tk.Canvas(processed_image_frame, width=400, height=400, bg="lightgrey", highlightthickness=0)
        self.processed_image_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.canvas_image_item = None # Store the canvas image item ID

        # Bind events for zoom and pan
        self.processed_image_canvas.bind("<MouseWheel>", self.on_mouse_wheel_zoom) # For Windows/macOS
        self.processed_image_canvas.bind("<Button-4>", self.on_mouse_wheel_zoom) # For Linux (scroll up)
        self.processed_image_canvas.bind("<Button-5>", self.on_mouse_wheel_zoom) # For Linux (scroll down)
        self.processed_image_canvas.bind("<ButtonPress-1>", self.on_canvas_button_press)
        self.processed_image_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.processed_image_canvas.bind("<ButtonRelease-1>", self.on_canvas_button_release)
        self.processed_image_canvas.bind("<Configure>", self.on_canvas_resize)

        # --- Navigation and Zoom Controls Frame ---
        nav_zoom_frame = ttk.Frame(main_frame)
        nav_zoom_frame.grid(row=2, column=0, columnspan=2, pady=5, sticky=tk.EW)
        
        button_container = ttk.Frame(nav_zoom_frame) # To center buttons
        button_container.pack(anchor=tk.CENTER)

        self.zoom_in_button = ttk.Button(button_container, text="Zoom In (+)", command=self.on_zoom_in_click)
        self.zoom_in_button.pack(side=tk.LEFT, padx=5)

        self.zoom_out_button = ttk.Button(button_container, text="Zoom Out (-)", command=self.on_zoom_out_click)
        self.zoom_out_button.pack(side=tk.LEFT, padx=5)

        self.next_image_button = ttk.Button(button_container, text="Next Image", command=self.on_next_image_click, state=tk.DISABLED)
        self.next_image_button.pack(side=tk.LEFT, padx=5)

        # --- Status Bar ---
        self.status_var = tk.StringVar()
        self.status_var.set("Please select a directory.")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.S)) # Stick to S

        # Configure resizing behavior
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1) # Image frame row
        images_frame.rowconfigure(0, weight=1) # Row containing image labels/canvas

        self.root.after(100, self._initial_canvas_setup) # Delay setup that depends on winfo
        logging.info("Tkinter UI initialized.")

    def _initial_canvas_setup(self):
        """Setup that needs actual canvas dimensions."""
        self._canvas_image_x = self.processed_image_canvas.winfo_width() / 2
        self._canvas_image_y = self.processed_image_canvas.winfo_height() / 2
        self.update_processed_image_display() # Draw placeholder text

    def on_canvas_resize(self, event):
        if self.raw_processed_image_cv is not None:
            self.update_processed_image_display()
        else: # If no image, ensure placeholder text is centered
            self.processed_image_canvas.delete("all")
            self.processed_image_canvas.create_text(
                event.width / 2, event.height / 2,
                text="Processed image will appear here.", anchor=tk.CENTER, tags="placeholder"
            )

    def _cv_to_photoimage_resized(self, cv_image, target_width, target_height):
        if cv_image is None: return None
        try:
            h, w = cv_image.shape[:2]
            if w == 0 or h == 0: return None
            scale = min(target_width/w, target_height/h)
            nw, nh = int(w*scale), int(h*scale)
            if nw <=0 or nh <=0: return None
            
            resized_cv_img = cv2.resize(cv_image, (nw, nh), interpolation=cv2.INTER_AREA)
            image_rgb = cv2.cvtColor(resized_cv_img, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(image_rgb)
            return ImageTk.PhotoImage(pil_image)
        except Exception as e:
            logging.error(f"Error converting/resizing OpenCV image for original display: {e}", exc_info=True)
            return None

    def _cv_to_pil_image_for_canvas(self, cv_image, zoom_level):
        if cv_image is None: return None, (0,0)
        img_h, img_w = cv_image.shape[:2]
        scaled_w = int(img_w * zoom_level)
        scaled_h = int(img_h * zoom_level)
        if scaled_w <= 0 or scaled_h <= 0: return None, (0,0)

        pil_img = Image.fromarray(cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB))
        resized_pil_img = pil_img.resize((scaled_w, scaled_h), Image.LANCZOS)
        return ImageTk.PhotoImage(resized_pil_img), (scaled_w, scaled_h)

    def update_processed_image_display(self):
        self.processed_image_canvas.delete("all") # Clear previous drawings

        if self.raw_processed_image_cv is None:
            self.canvas_image_item = None
            self.processed_image_canvas.create_text(
                self.processed_image_canvas.winfo_width() / 2,
                self.processed_image_canvas.winfo_height() / 2,
                text="Processed image will appear here.", anchor=tk.CENTER, tags="placeholder"
            )
            return

        canvas_width = self.processed_image_canvas.winfo_width()
        canvas_height = self.processed_image_canvas.winfo_height()

        self.processed_photo_image, (img_w, img_h) = self._cv_to_pil_image_for_canvas(
            self.raw_processed_image_cv, self.current_zoom_level
        )

        if self.processed_photo_image and img_w > 0 and img_h > 0:
            # Clamp offsets
            max_offset_x = canvas_width - 10 # Allow some part of image to be visible
            min_offset_x = 10 - img_w
            max_offset_y = canvas_height - 10
            min_offset_y = 10 - img_h

            if img_w <= canvas_width : # Center if smaller than canvas
                self.current_offset_x = (canvas_width - img_w) / 2
            else:
                self.current_offset_x = max(min_offset_x, min(max_offset_x, self.current_offset_x))

            if img_h <= canvas_height: # Center if smaller than canvas
                self.current_offset_y = (canvas_height - img_h) / 2
            else:
                self.current_offset_y = max(min_offset_y, min(max_offset_y, self.current_offset_y))

            self.canvas_image_item = self.processed_image_canvas.create_image(
                self.current_offset_x, self.current_offset_y,
                anchor=tk.NW, image=self.processed_photo_image
            )
            self.processed_image_canvas.image = self.processed_photo_image # Keep reference
            logging.info(f"Processed image updated. Zoom: {self.current_zoom_level:.2f}, Offset: ({self.current_offset_x:.2f}, {self.current_offset_y:.2f}), ImgSize: ({img_w}x{img_h})")
        else:
            self.canvas_image_item = None
            self.processed_image_canvas.create_text(
                 canvas_width / 2, canvas_height / 2,
                text="Error displaying processed image.", anchor=tk.CENTER, tags="placeholder"
            )
        self.root.update_idletasks()

    def process_current_image(self):
        """
        Loads the current image specified by `self.current_image_index`, processes it for
        QR codes and ChArUco board detection, and displays the result in the
        processed image view. Updates status text throughout the process.
        """
        logging.info(f"Starting process_current_image for index: {self.current_image_index}")

        if not (0 <= self.current_image_index < len(self.image_paths)):
            logging.warning(f"process_current_image called with invalid index {self.current_image_index} or empty image_paths. Aborting.")
            self.status_var.set("No image selected or index out of bounds for processing.")
            self.raw_processed_image_cv = None
            self.update_processed_image_display()
            return

        img_path = self.image_paths[self.current_image_index]
        logging.info(f"Attempting to load image for processing: {img_path}")
        self.status_var.set(f"Processing: {os.path.basename(img_path)}...")
        self.root.update_idletasks()

        loaded_image = cv2.imread(img_path)
        if loaded_image is None:
            logging.error(f"cv2.imread failed to load image: {img_path}")
            self.raw_processed_image_cv = None
            self.status_var.set(f"Error: Could not load image file: {os.path.basename(img_path)}")
            self.update_processed_image_display()
            return

        image_with_qrs = loaded_image.copy()
        if detect_and_draw_qrcodes:
            logging.info("Attempting QR code detection...")
            try:
                qr_results = detect_and_draw_qrcodes(loaded_image)
                if qr_results and len(qr_results) > 0 and qr_results[0] is not None:
                    image_with_qrs = qr_results[0]
                    # If you need cropped QR images, they are in qr_results[1:]
                    logging.info("QR code detection successful, image updated.")
                else:
                    # image_with_qrs remains loaded_image.copy()
                    logging.info("QR code detection ran, but no QR codes were found or image was not returned.")
            except Exception as e:
                logging.error(f"Exception during QR code detection: {e}", exc_info=True)
                self.status_var.set("Error during QR detection.")
        else:
            logging.warning("QR code detection function is not available. Skipping.")
            current_status = self.status_var.get()
            self.status_var.set(f"{current_status.replace('Processing: ', '')} (QR detection skipped)")

        processed_img_final = image_with_qrs
        if detect_charuco_board:
            logging.info(f"Attempting ChArUco board detection with params: X={self.CHARUCO_SQUARES_X}, Y={self.CHARUCO_SQUARES_Y}, SqL={self.CHARUCO_SQUARE_LENGTH_MM}, MkL={self.CHARUCO_MARKER_LENGTH_MM}, Dict={self.CHARUCO_DICTIONARY_NAME}")
            try:
                charuco_result_image = detect_charuco_board(
                    image_with_qrs,
                    self.CHARUCO_SQUARES_X, self.CHARUCO_SQUARES_Y,
                    self.CHARUCO_SQUARE_LENGTH_MM, self.CHARUCO_MARKER_LENGTH_MM,
                    self.CHARUCO_DICTIONARY_NAME, display=False
                )
                if charuco_result_image is not None:
                    processed_img_final = charuco_result_image
                    logging.info("ChArUco board detection successful, image updated.")
                else:
                    logging.warning("ChArUco board detection ran but returned None. Using image from previous step.")
            except Exception as e:
                logging.error(f"Exception during ChArUco board detection: {e}", exc_info=True)
                self.status_var.set("Error during ChArUco detection.")
        else:
            logging.warning("ChArUco board detection function (detect_charuco_board) is not available. Skipping.")
            current_status = self.status_var.get()
            self.status_var.set(f"{current_status.replace('Processing: ', '').split(' (')[0]} (ChArUco skipped)")

        self.raw_processed_image_cv = processed_img_final
        self.status_var.set(f"Displaying: {os.path.basename(img_path)} (Processed)")
        self.update_processed_image_display()
        logging.info(f"Finished process_current_image for index: {self.current_image_index}.")
    def display_image(self, index: int):
        """
        Displays the image at the given index from `self.image_paths` in the original view,
        resets zoom/pan for the processed view, and triggers processing for the new image.
        Updates UI elements like status text and navigation buttons.

        Args:
            index (int): The index of the image to display from `self.image_paths`.
        """
        logging.info(f"Attempting to display image at index: {index}. Total images available: {len(self.image_paths)}.")

        if 0 <= index < len(self.image_paths):
            self.current_image_index = index
            image_path = self.image_paths[index]

            logging.info(f"Setting original image display to: {image_path}")
            try:
                cv_original_img = cv2.imread(image_path)
                if cv_original_img is not None:
                    # Resize to fit the label (e.g., 400x400 or based on label size)
                    # Assuming original_image_label has a fixed size or we use a default
                    label_w = self.original_image_label.winfo_width() if self.original_image_label.winfo_width() > 1 else 400
                    label_h = self.original_image_label.winfo_height() if self.original_image_label.winfo_height() > 1 else 400
                    self.original_photo_image = self._cv_to_photoimage_resized(cv_original_img, label_w, label_h)

                    if self.original_photo_image:
                        self.original_image_label.config(image=self.original_photo_image, text="")
                        self.original_image_label.image = self.original_photo_image # Keep ref
                    else:
                        self.original_image_label.config(image=None, text=f"Error loading: {os.path.basename(image_path)}")
                else:
                    self.original_image_label.config(image=None, text=f"Cannot load: {os.path.basename(image_path)}")
            except Exception as e:
                logging.error(f"Error displaying original image {image_path}: {e}", exc_info=True)
                self.original_image_label.config(image=None, text=f"Error: {os.path.basename(image_path)}")

            # Reset zoom/pan for processed view
            self.current_zoom_level = 1.0
            # Center the image initially in the canvas
            canvas_width = self.processed_image_canvas.winfo_width()
            canvas_height = self.processed_image_canvas.winfo_height()
            # We don't know the new image size yet, so process_current_image will set initial offset
            # For now, set a temporary one or rely on update_processed_image_display to center if small
            self.current_offset_x = canvas_width / 2 
            self.current_offset_y = canvas_height / 2

            self.status_var.set(f"Displaying image {index + 1} of {len(self.image_paths)}: {os.path.basename(image_path)}")
            self.next_image_button.config(state=tk.NORMAL if index < len(self.image_paths) - 1 else tk.DISABLED)

            self.process_current_image()
        else:
            logging.warning(f"display_image called with invalid index: {index}. Image list length: {len(self.image_paths)}.")

    def pick_directory_clicked(self):
        """
        Handles the click event for the 'Pick Image Directory' button.
        Uses tkinter.filedialog to open a directory dialog.
        Populates `self.image_paths` and displays the first image.
        """
        logging.info("Pick Directory button clicked.")
        directory = filedialog.askdirectory(
            title="Select Image Directory",
            initialdir=os.path.expanduser("~")
        )

        if directory: # Non-empty string if a directory is selected
                logging.info(f"Directory selected: {directory}")
                self.image_paths.clear()
                img_extensions = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif"]
                for ext in img_extensions:
                    self.image_paths.extend(glob.glob(os.path.join(directory, ext)))
                
                self.image_paths = sorted(list(set(self.image_paths)))
                logging.info(f"Found {len(self.image_paths)} images with extensions {img_extensions} in directory: {directory}")

                if self.image_paths:
                    self.current_image_index = -1 # So display_image(0) correctly loads the first
                    self.display_image(0)
                    self.status_var.set(f"Loaded {len(self.image_paths)} images from {os.path.basename(directory)}.")
                    self.next_image_button.config(state=tk.NORMAL if len(self.image_paths) > 1 else tk.DISABLED)
                else:
                    self.current_image_index = -1
                    self.status_var.set(f"No image files found in: {directory}")
                    self.original_image_label.config(image=None, text="No images found.")
                    self.original_image_label.image = None # Clear ref
                    self.raw_processed_image_cv = None
                    self.update_processed_image_display()
                    self.next_image_button.config(state=tk.DISABLED)
        else:
            logging.info("Directory selection was cancelled or no path was returned.")
            self.status_var.set("Directory selection cancelled or no path chosen.")
        self.root.update_idletasks()

    def on_next_image_click(self):
        """Handler for the 'Next Image' button."""
        logging.info(f"Next Image button clicked. Current index: {self.current_image_index}, Total images: {len(self.image_paths)}")
        if self.current_image_index < len(self.image_paths) - 1:
            self.display_image(self.current_image_index + 1)
        else:
            logging.info("Next Image clicked, but already at the last image in the list.")

    def _adjust_zoom(self, factor_change, zoom_center_x=None, zoom_center_y=None):
        if self.raw_processed_image_cv is None: return

        old_scale = self.current_zoom_level
        # Calculate new scale based on factor (e.g., 1.2 for 20% zoom in, 1/1.2 for 20% zoom out)
        new_scale = old_scale * factor_change
        new_scale = round(new_scale, 2)
        new_scale = max(self.min_zoom_level, min(self.max_zoom_level, new_scale))

        if abs(new_scale - old_scale) < 0.001 : # No significant change
            logging.info(f"Zoom: No change, at min/max zoom or increment too small. Current: {old_scale:.2f}")
            return

        canvas_width = self.processed_image_canvas.winfo_width()
        canvas_height = self.processed_image_canvas.winfo_height()

        if zoom_center_x is None: zoom_center_x = canvas_width / 2
        if zoom_center_y is None: zoom_center_y = canvas_height / 2

        # Image point under cursor before zoom:
        # (mouse_x_on_canvas - current_image_offset_x_on_canvas) / old_zoom_scale
        img_point_x_at_cursor = (zoom_center_x - self.current_offset_x) / old_scale
        img_point_y_at_cursor = (zoom_center_y - self.current_offset_y) / old_scale

        # New offset to keep that image point under the cursor:
        # new_offset_x = mouse_x_on_canvas - (img_point_x_at_cursor * new_zoom_scale)
        self.current_offset_x = zoom_center_x - (img_point_x_at_cursor * new_scale)
        self.current_offset_y = zoom_center_y - (img_point_y_at_cursor * new_scale)
        
        self.current_zoom_level = new_scale
        logging.info(f"Zoom: Scale {old_scale:.2f} -> {new_scale:.2f}. Offset -> ({self.current_offset_x:.2f}, {self.current_offset_y:.2f})")
        self.update_processed_image_display()

    def on_zoom_in_click(self):
        """Handler for the 'Zoom In' button."""
        self._adjust_zoom(1 + self.zoom_increment)

    def on_zoom_out_click(self):
        """Handler for the 'Zoom Out' button."""
        self._adjust_zoom(1 / (1 + self.zoom_increment))

    def on_mouse_wheel_zoom(self, event):
        if self.raw_processed_image_cv is None: return
        factor = 0
        if event.num == 4 or event.delta > 0:  # Scroll up (Linux) or positive delta (Windows/macOS)
            factor = 1 + self.zoom_increment
        elif event.num == 5 or event.delta < 0:  # Scroll down (Linux) or negative delta (Windows/macOS)
            factor = 1 / (1 + self.zoom_increment)
        
        if factor != 0:
            self._adjust_zoom(factor, event.x, event.y)

    def on_canvas_button_press(self, event):
        if self.raw_processed_image_cv is None: return
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self.processed_image_canvas.config(cursor="fleur")

    def on_canvas_drag(self, event):
        if self.raw_processed_image_cv is None: return
        dx = event.x - self._drag_start_x
        dy = event.y - self._drag_start_y
        self.current_offset_x += dx
        self.current_offset_y += dy
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self.update_processed_image_display()

    def on_canvas_button_release(self, event):
        self.processed_image_canvas.config(cursor="")

def main():
    """
    Sets up and runs the Flet application.
    Creates an instance of ImageViewerApp and initializes its UI.
    """
    root = tk.Tk()
    # Attempt to set a modern theme if available
    try:
        style = ttk.Style()
        available_themes = style.theme_names()
        logging.info(f"Available themes: {available_themes}")
        if "clam" in available_themes: # 'clam', 'alt', 'default', 'classic'
            style.theme_use("clam")
        elif "vista" in available_themes and platform.system() == "Windows":
             style.theme_use("vista")
    except tk.TclError:
        logging.warning("Could not set ttk theme.")
        pass

    app = ImageViewerApp(root)
    root.mainloop()

if __name__ == "__main__":
    logging.info("Application starting (Tkinter version)...")
    main()
