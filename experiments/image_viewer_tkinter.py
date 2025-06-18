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
        self.min_zoom_level = 0.01  # Allow very small zooms for large images
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

        # --- Info Column State ---
        self.charuco_detected_status = None  # True, False, or None (unknown)
        self.qr_decoded_texts_list = []
        self.CHARUCO_STATUS_INDICATOR_SIZE = 20
        self.CHARUCO_DETECTED_COLOR = "green"
        self.CHARUCO_NOT_DETECTED_COLOR = "red"
        self.CHARUCO_UNKNOWN_COLOR = "grey"
        self.info_column_width = 250 # Width for the new info column

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
        controls_frame.grid(row=0, column=0, columnspan=3, pady=5, sticky=tk.EW) # Span 3 columns

        self.pick_directory_button = ttk.Button(
            controls_frame,
            text="Pick Image Directory",
            command=self.pick_directory_clicked
        )
        # Center the button in the controls_frame
        controls_frame.columnconfigure(0, weight=1)
        self.pick_directory_button.grid(row=0, column=0, padx=5)

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

        # --- Info Column Frame (New) ---
        info_column_frame = ttk.LabelFrame(main_frame, text="Information", padding="5")
        info_column_frame.grid(row=1, column=2, padx=5, pady=5, sticky=(tk.N, tk.S, tk.E, tk.W))
        info_column_frame.rowconfigure(1, weight=0) # Label for ChArUco status
        info_column_frame.rowconfigure(2, weight=0) # Canvas for ChArUco status
        info_column_frame.rowconfigure(3, weight=0) # Separator
        info_column_frame.rowconfigure(4, weight=0) # Label for QR Data
        info_column_frame.rowconfigure(5, weight=1) # Text area for QR Data
        info_column_frame.columnconfigure(0, weight=1)

        ttk.Label(info_column_frame, text="ChArUco Status:").grid(row=0, column=0, sticky=tk.W, pady=(0,2))
        
        # Determine background color for the canvas to match its ttk parent
        style = ttk.Style()
        try:
            # info_column_frame is a ttk.LabelFrame, so we look up its background
            canvas_bg_color = style.lookup('TLabelFrame', 'background')
        except tk.TclError:
            # Fallback to a general TFrame background if TLabelFrame specific lookup fails
            canvas_bg_color = style.lookup('TFrame', 'background')

        self.charuco_status_canvas = tk.Canvas(
            info_column_frame, 
            width=self.CHARUCO_STATUS_INDICATOR_SIZE + 10, 
            height=self.CHARUCO_STATUS_INDICATOR_SIZE + 10, 
            bg=canvas_bg_color, # Use the looked-up background color
            highlightthickness=0
        )
        self.charuco_status_canvas.grid(row=1, column=0, pady=(0,10))

        ttk.Separator(info_column_frame, orient=tk.HORIZONTAL).grid(row=2, column=0, sticky=tk.EW, pady=5)
        
        ttk.Label(info_column_frame, text="QR Decoded Data:").grid(row=3, column=0, sticky=tk.W, pady=(0,2))
        self.qr_data_text = tk.Text(info_column_frame, wrap=tk.WORD, height=10, width=30, state=tk.DISABLED)
        qr_scrollbar = ttk.Scrollbar(info_column_frame, orient=tk.VERTICAL, command=self.qr_data_text.yview)
        self.qr_data_text.config(yscrollcommand=qr_scrollbar.set)
        self.qr_data_text.grid(row=4, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        qr_scrollbar.grid(row=4, column=1, sticky=(tk.N, tk.S))
        info_column_frame.rowconfigure(4, weight=1) # Make text area expand

        # --- Navigation and Zoom Controls Frame ---
        nav_zoom_frame = ttk.Frame(main_frame)
        nav_zoom_frame.grid(row=2, column=0, columnspan=3, pady=5, sticky=tk.EW) # Span 3 columns
        
        button_container = ttk.Frame(nav_zoom_frame) # To center buttons
        button_container.pack(anchor=tk.CENTER)

        self.reset_zoom_button = ttk.Button(button_container, text="Reset Zoom", command=self.on_reset_zoom_click)
        self.reset_zoom_button.pack(side=tk.LEFT, padx=5)

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
        status_bar.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.S)) # Span 3 columns, Stick to S

        # Configure resizing behavior
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1) # Processed image column
        main_frame.columnconfigure(2, weight=0) # Info column, fixed width or less weight
        main_frame.grid_columnconfigure(2, minsize=self.info_column_width)

        main_frame.rowconfigure(1, weight=1) # Image frame row
        images_frame.rowconfigure(0, weight=1) # Row containing image labels/canvas

        self.root.after(100, self._initial_ui_update) # Delay setup that depends on winfo
        logging.info("Tkinter UI initialized.")

    def _initial_ui_update(self):
        """Setup that needs actual canvas dimensions."""
        self._canvas_image_x = self.processed_image_canvas.winfo_width() / 2
        self._canvas_image_y = self.processed_image_canvas.winfo_height() / 2
        self.update_processed_image_display() # Draw placeholder text
        self.update_info_column() # Draw initial info column state

    def update_info_column(self):
        """Updates the ChArUco status indicator and QR data text."""
        # Update ChArUco status indicator
        self.charuco_status_canvas.delete("all")
        status_color = self.CHARUCO_UNKNOWN_COLOR
        if self.charuco_detected_status is True:
            status_color = self.CHARUCO_DETECTED_COLOR
        elif self.charuco_detected_status is False:
            status_color = self.CHARUCO_NOT_DETECTED_COLOR
        
        canvas_w = self.charuco_status_canvas.winfo_width()
        canvas_h = self.charuco_status_canvas.winfo_height()
        # Ensure canvas is realized, use default size if not
        canvas_w = canvas_w if canvas_w > 1 else self.CHARUCO_STATUS_INDICATOR_SIZE + 10
        canvas_h = canvas_h if canvas_h > 1 else self.CHARUCO_STATUS_INDICATOR_SIZE + 10

        x0 = (canvas_w - self.CHARUCO_STATUS_INDICATOR_SIZE) / 2
        y0 = (canvas_h - self.CHARUCO_STATUS_INDICATOR_SIZE) / 2
        x1 = x0 + self.CHARUCO_STATUS_INDICATOR_SIZE
        y1 = y0 + self.CHARUCO_STATUS_INDICATOR_SIZE
        self.charuco_status_canvas.create_oval(x0, y0, x1, y1, fill=status_color, outline=status_color)

        # Update QR data text
        self.qr_data_text.config(state=tk.NORMAL)
        self.qr_data_text.delete("1.0", tk.END)
        if not detect_and_draw_qrcodes and self.current_image_index != -1 : # Module not available but tried to process
            self.qr_data_text.insert(tk.END, "QR detection module not available.\n")
        elif self.qr_decoded_texts_list:
            for i, text in enumerate(self.qr_decoded_texts_list):
                self.qr_data_text.insert(tk.END, f"QR #{i+1}: {text}\n---\n")
        elif self.current_image_index != -1: # Processed, but no QR data
             self.qr_data_text.insert(tk.END, "No QR codes found or decoded.\n")
        else: # Not processed yet or no image loaded
            self.qr_data_text.insert(tk.END, "Load an image to see QR data.\n")
        self.qr_data_text.config(state=tk.DISABLED)

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

        # Reset status for the current processing attempt
        self.charuco_detected_status = False 
        self.qr_decoded_texts_list = []

        if not (0 <= self.current_image_index < len(self.image_paths)):
            logging.warning(f"process_current_image called with invalid index {self.current_image_index} or empty image_paths. Aborting.")
            self.status_var.set("No image selected or index out of bounds for processing.")
            self.raw_processed_image_cv = None
            # self.charuco_detected_status will remain False, qr_decoded_texts_list empty
            # display_image will call update_processed_image_display and update_info_column
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
            # Statuses remain as initialized (False, empty)
            return

        image_with_qrs = loaded_image.copy()
        if detect_and_draw_qrcodes:
            logging.info("Attempting QR code detection...")
            try:
                # detect_and_draw_qrcodes returns (list_of_images, list_of_decoded_texts)
                qr_images, qr_decoded_texts = detect_and_draw_qrcodes(loaded_image)
                if qr_images and len(qr_images) > 0 and qr_images[0] is not None:
                    image_with_qrs = qr_images[0]
                    if qr_decoded_texts:
                        self.qr_decoded_texts_list = qr_decoded_texts
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
                # detect_charuco_board returns (img, charucoCorners, charucoIds, markerCorners, markerIds)
                charuco_img_output, charuco_corners, charuco_ids, marker_corners, marker_ids = detect_charuco_board(
                    image_with_qrs,
                    self.CHARUCO_SQUARES_X, self.CHARUCO_SQUARES_Y,
                    self.CHARUCO_SQUARE_LENGTH_MM, self.CHARUCO_MARKER_LENGTH_MM,
                    self.CHARUCO_DICTIONARY_NAME, display=False
                )
                if charuco_img_output is not None:
                    processed_img_final = charuco_img_output
                    if charuco_ids is not None and len(charuco_ids) > 0:
                        self.charuco_detected_status = True
                        logging.info("ChArUco board detection successful, image updated, status set to True.")
                    else:
                        logging.info("ChArUco board detection ran, image updated, but no ChArUco IDs found.")
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

            # Process the image. This sets self.raw_processed_image_cv, self.charuco_detected_status, self.qr_decoded_texts_list
            # Note: process_current_image no longer calls update_processed_image_display itself.
            self.process_current_image() 

            if self.raw_processed_image_cv is not None:
                img_h, img_w = self.raw_processed_image_cv.shape[:2]
                canvas_w = self.processed_image_canvas.winfo_width()
                canvas_h = self.processed_image_canvas.winfo_height()

                if img_w > 0 and img_h > 0 and canvas_w > 0 and canvas_h > 0:
                    zoom_w_ratio = canvas_w / img_w
                    zoom_h_ratio = canvas_h / img_h
                    self.current_zoom_level = min(zoom_w_ratio, zoom_h_ratio)
                    # Remove min_zoom_level clamp so image always fits
                    self.current_zoom_level = min(self.current_zoom_level, self.max_zoom_level)
                    logging.info(f"Initial fit-to-screen zoom calculated: {self.current_zoom_level:.2f}")

                    # Calculate centered offsets for this zoom level
                    scaled_img_w_at_fit = int(img_w * self.current_zoom_level)
                    scaled_img_h_at_fit = int(img_h * self.current_zoom_level)
                    self.current_offset_x = (canvas_w - scaled_img_w_at_fit) / 2
                    self.current_offset_y = (canvas_h - scaled_img_h_at_fit) / 2
                    logging.info(f"Initial centered offsets: ({self.current_offset_x:.2f}, {self.current_offset_y:.2f})")
                    # Prevent zooming out further than fit-to-canvas
                    self.min_zoom_level = self.current_zoom_level
                else: # Fallback if image/canvas dimensions are zero
                    self.current_zoom_level = 1.0
                    self.current_offset_x = (canvas_w - (img_w if img_w else 0)) / 2 
                    self.current_offset_y = (canvas_h - (img_h if img_h else 0)) / 2
            else: # No raw_processed_image_cv, reset zoom/pan
                self.current_zoom_level = 1.0
                self.current_offset_x = 0
                self.current_offset_y = 0
            
            self.status_var.set(f"Displaying image {index + 1} of {len(self.image_paths)}: {os.path.basename(image_path)}")
            if self.raw_processed_image_cv is not None: # If processing was successful (even if no detections)
                self.status_var.set(f"Displaying: {os.path.basename(image_path)} (Processed)")
            # If raw_processed_image_cv is None, process_current_image would have set an error status or status_var remains.
            
            self.next_image_button.config(state=tk.NORMAL if index < len(self.image_paths) - 1 else tk.DISABLED)
            self.update_processed_image_display() # Render with the new zoom/pan
            self.update_info_column() # Update the info column based on processing results

        else:
            logging.warning(f"display_image called with invalid index: {index}. Image list length: {len(self.image_paths)}.")
            self.raw_processed_image_cv = None # Ensure processed view is cleared
            self.charuco_detected_status = None # Reset to unknown
            self.qr_decoded_texts_list = []
            self.update_processed_image_display()
            self.update_info_column()

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
                    self.charuco_detected_status = None 
                    self.qr_decoded_texts_list = []

                    self.update_processed_image_display()
                    self.update_info_column()
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

    def on_reset_zoom_click(self):
        """Resets zoom and pan so the processed image fits the canvas (fit-to-canvas)."""
        if self.raw_processed_image_cv is None:
            return
        img_h, img_w = self.raw_processed_image_cv.shape[:2]
        canvas_w = self.processed_image_canvas.winfo_width()
        canvas_h = self.processed_image_canvas.winfo_height()
        if img_w > 0 and img_h > 0 and canvas_w > 0 and canvas_h > 0:
            zoom_w_ratio = canvas_w / img_w
            zoom_h_ratio = canvas_h / img_h
            self.current_zoom_level = min(zoom_w_ratio, zoom_h_ratio)
            self.current_zoom_level = min(self.current_zoom_level, self.max_zoom_level)
            scaled_img_w_at_fit = int(img_w * self.current_zoom_level)
            scaled_img_h_at_fit = int(img_h * self.current_zoom_level)
            self.current_offset_x = (canvas_w - scaled_img_w_at_fit) / 2
            self.current_offset_y = (canvas_h - scaled_img_h_at_fit) / 2
            self.min_zoom_level = self.current_zoom_level  # Prevent zooming out further than fit-to-canvas
            self.update_processed_image_display()
            # self.update_info_column() # Info column doesn't change on zoom reset
        else:
            logging.warning("Reset zoom clicked, but image or canvas dimensions are invalid. Cannot reset zoom.")

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
