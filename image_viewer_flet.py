import flet as ft
import cv2
import numpy as np
import logging
import os
import glob
import platform
import subprocess
import base64

# --- File-Level Comment ---
"""
image_viewer_flet.py

A Flet-based desktop application for viewing images from a directory and processing them
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
# If this script is imported as a module, basicConfig might not have an effect if the root logger is already configured.
# However, for a standalone Flet app, this is generally fine.
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s' # Added filename and lineno
)


class ImageViewerApp:
    def __init__(self, page: ft.Page):
        self.page = page
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
        self.max_zoom_level = 5.0
        self.min_zoom_level = 0.5
        self.zoom_increment = 0.2
        
        self.processed_image_scale = ft.Scale(scale=self.current_zoom_level)
        self.processed_image_offset = ft.Offset(x=0, y=0)

        # UI elements will be initialized in init_ui
        self.original_image_display = None
        self.processed_image_content = None
        self.status_text = None
        self.next_image_button = None
        self.processed_image_container = None
        self.pick_directory_button = None
        self.processed_image_gesture_detector = None
        self.zoom_in_button = None
        self.zoom_out_button = None


    def init_ui(self):
        """Initializes and lays out the UI elements for the application."""
        # --- UI Element Definitions ---
        self.original_image_display = ft.Image(
            width=400, height=400, fit=ft.ImageFit.CONTAIN,
            error_content=ft.Text("Original image will appear here.")
        )
        self.processed_image_content = ft.Image(
            width=400, height=400, fit=ft.ImageFit.CONTAIN,
            error_content=ft.Text("Processed image will appear here.")
        )
        self.status_text = ft.Text("Please select a directory.")
        self.next_image_button = ft.ElevatedButton("Next Image", on_click=self.on_next_image_click, disabled=True)
        
        self.processed_image_container = ft.Container(
            content=self.processed_image_content,
            width=400, height=400,
            scale=self.processed_image_scale,  # Use the ft.Scale object for the scale argument
            offset=self.processed_image_offset, # Use the ft.Offset object for the offset argument
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        self.pick_directory_button = ft.ElevatedButton(
            "Pick Image Directory",
            icon="folder_open",
            on_click=self.pick_directory_clicked, # Changed to a dedicated method
            tooltip="Select a directory containing images"
        )

        # --- Processed Image Interaction ---
        self.processed_image_gesture_detector = ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.MOVE,
            content=self.processed_image_container,
            on_tap_down=self.on_image_tap_down
        )

        # --- Control Buttons ---
        self.zoom_in_button = ft.IconButton("zoom_in", on_click=self.on_zoom_in_click, tooltip="Zoom In")
        self.zoom_out_button = ft.IconButton("zoom_out", on_click=self.on_zoom_out_click, tooltip="Zoom Out")

        # --- Arrange UI elements ---
        self.page.add(
            ft.Column(
                [
                    ft.Row([self.pick_directory_button], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Row(
                        [
                            ft.Column([ft.Text("Original Image"), self.original_image_display], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                            ft.Column([ft.Text("Processed Image (Tap to zoom/center)"), self.processed_image_gesture_detector], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                        vertical_alignment=ft.CrossAxisAlignment.START
                    ),
                    ft.Row(
                        [self.zoom_in_button, self.zoom_out_button, self.next_image_button],
                        alignment=ft.MainAxisAlignment.CENTER
                    ),
                    self.status_text
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=20
            )
        )
        logging.info("Main UI layout constructed and added to page.")
        self.page.update()


    def update_processed_image_transform(self):
        """
        Applies the current scale and offset transformations to the processed image container
        and updates the Flet page to reflect these changes.
        Logs the new transformation values.
        """
        self.processed_image_container.transform = [self.processed_image_scale, self.processed_image_offset]
        current_scale_val = self.processed_image_scale.scale
        if isinstance(current_scale_val, ft.Control): # Should not happen with direct assignment
            current_scale_val = current_scale_val.value
        logging.info(f"Transform updated: Scale={current_scale_val}, Offset=({self.processed_image_offset.x}, {self.processed_image_offset.y})")
        self.page.update(self.processed_image_container)

    def process_current_image(self):
        """
        Loads the current image specified by `self.current_image_index`, processes it for
        QR codes and ChArUco board detection, and displays the result in the
        processed image view. Updates status text throughout the process.
        """
        logging.info(f"Starting process_current_image for index: {self.current_image_index}")

        if not (0 <= self.current_image_index < len(self.image_paths)):
            logging.warning(f"process_current_image called with invalid index {self.current_image_index} or empty image_paths. Aborting.")
            self.status_text.value = "No image selected or index out of bounds for processing."
            self.page.update(self.status_text)
            return

        img_path = self.image_paths[self.current_image_index]
        logging.info(f"Attempting to load image for processing: {img_path}")
        self.status_text.value = f"Processing: {os.path.basename(img_path)}..."
        self.page.update(self.status_text)

        loaded_image = cv2.imread(img_path)
        if loaded_image is None:
            logging.error(f"cv2.imread failed to load image: {img_path}")
            self.processed_image_content.src_base64 = None
            self.status_text.value = f"Error: Could not load image file: {os.path.basename(img_path)}"
            self.page.update(self.processed_image_content, self.status_text)
            return

        image_with_qrs = loaded_image.copy()
        if detect_and_draw_qrcodes:
            logging.info("Attempting QR code detection...")
            try:
                qr_results = detect_and_draw_qrcodes(loaded_image)
                if qr_results and len(qr_results) > 0 and qr_results[0] is not None:
                    image_with_qrs = qr_results[0]
                    logging.info("QR code detection successful, image updated.")
                else:
                    logging.info("QR code detection ran, but no QR codes were found or image was not returned.")
            except Exception as e:
                logging.error(f"Exception during QR code detection: {e}", exc_info=True)
                self.status_text.value = "Error during QR detection."
        else:
            logging.warning("QR code detection function (detect_and_draw_qrcodes) is not available. Skipping QR detection.")
            current_status = self.status_text.value
            self.status_text.value = f"{current_status} (QR detection skipped: module not found)"

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
                self.status_text.value = "Error during ChArUco detection."
        else:
            logging.warning("ChArUco board detection function (detect_charuco_board) is not available. Skipping.")
            current_status = self.status_text.value
            self.status_text.value = f"{current_status} (ChArUco detection skipped: module not found)"

        try:
            success, buffer = cv2.imencode('.png', processed_img_final)
            if not success:
                logging.error(f"cv2.imencode failed for image: {img_path}")
                self.processed_image_content.src_base64 = None
                self.status_text.value = "Error: Could not encode processed image."
                self.page.update(self.processed_image_content, self.status_text)
                return
            base64_image = base64.b64encode(buffer).decode('utf-8')
            self.processed_image_content.src_base64 = base64_image
            logging.info(f"Successfully processed and encoded image '{img_path}' for display.")
            self.status_text.value = f"Displaying: {os.path.basename(img_path)} (Processed)"
        except Exception as e:
            logging.error(f"Exception encoding image to base64: {e}", exc_info=True)
            self.processed_image_content.src_base64 = None
            self.status_text.value = "Error: Could not display processed image."
        
        self.page.update(self.processed_image_content, self.status_text)
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
            self.original_image_display.src = image_path
            self.original_image_display.error_content = ft.Text(f"Error loading: {os.path.basename(image_path)}")
            
            self.processed_image_content.src = None 
            self.processed_image_content.src_base64 = None 
            
            logging.info("Resetting zoom (to 1.0) and pan (to 0,0) for the new processed image.")
            self.current_zoom_level = 1.0
            self.processed_image_scale.scale = self.current_zoom_level
            self.processed_image_offset.x = 0.0
            self.processed_image_offset.y = 0.0
            self.processed_image_container.transform = [self.processed_image_scale, self.processed_image_offset]

            self.status_text.value = f"Displaying image {index + 1} of {len(self.image_paths)}: {os.path.basename(image_path)}"
            self.next_image_button.disabled = (index >= len(self.image_paths) - 1)
            
            self.page.update(self.original_image_display, self.status_text, self.next_image_button, self.processed_image_content, self.processed_image_container)
            logging.info(f"Original image display updated. Current index: {self.current_image_index}, Path: {image_path}. Next button disabled: {self.next_image_button.disabled}")
            
            self.process_current_image()
        else:
            logging.warning(f"display_image called with invalid index: {index}. Image list length: {len(self.image_paths)}.")

    def pick_directory_clicked(self, _e): # _e is Flet event, not used here
        """
        Handles the click event for the 'Pick Image Directory' button.
        Uses platform-specific methods to open a directory dialog.
        Populates `self.image_paths` and displays the first image.
        """
        logging.info("Pick Directory button clicked.")
        directory = None
        system = platform.system()

        try:
            if system == "Darwin":  # macOS
                script = 'POSIX path of (choose folder with prompt "Select Image Directory")'
                result = subprocess.run(
                    ['osascript', '-e', script],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode == 0:
                    directory = result.stdout.strip()
                    if directory.endswith('/'):
                        directory = directory[:-1]
                else:
                    logging.warning(f"macOS directory picker (osascript) failed. Return code: {result.returncode}, Stderr: {result.stderr.strip()}")
                    directory = None
            
            elif system == "Linux":
                result = subprocess.run(
                    ['zenity', '--file-selection', '--directory', '--title=Select Image Directory'],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode == 0:
                    directory = result.stdout.strip()
                else:
                    logging.warning(f"Linux directory picker (zenity) failed. Return code: {result.returncode}, Stderr: {result.stderr.strip()}")
                    directory = None

            elif system == "Windows":
                try:
                    import tkinter as tk
                    from tkinter import filedialog
                    root = tk.Tk()
                    root.withdraw()  # Hide the main tkinter window
                    root.attributes("-topmost", True) # Attempt to bring dialog to front
                    selected_path = filedialog.askdirectory(
                        title="Select Image Directory",
                        initialdir=os.path.expanduser("~")
                    )
                    root.destroy() # Clean up the tkinter root window
                    if selected_path: # askdirectory returns "" on cancel
                        directory = selected_path
                    else:
                        directory = None
                except ImportError:
                    logging.error("Tkinter module not found. Windows directory picker cannot function.")
                    self.status_text.value = "Error: Tkinter module not found for directory picker."
                    self.page.update(self.status_text)
                    return
                except Exception as tk_ex:
                    logging.error(f"Error using Tkinter for directory picker: {tk_ex}", exc_info=True)
                    self.status_text.value = f"Error with Tkinter directory picker: {str(tk_ex)}"
                    self.page.update(self.status_text)
                    return
            else:
                logging.warning(f"Unsupported platform for native directory dialog: {system}.")
                self.status_text.value = f"Directory picking not automatically supported on this OS ({system})."
                self.page.update(self.status_text)
                return

            if directory and directory.strip():
                logging.info(f"Directory selected: {directory}")
                self.image_paths.clear()
                img_extensions = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif"]
                for ext in img_extensions:
                    self.image_paths.extend(glob.glob(os.path.join(directory, ext)))
                
                self.image_paths = sorted(list(set(self.image_paths)))
                logging.info(f"Found {len(self.image_paths)} images with extensions {img_extensions} in directory: {directory}")

                if self.image_paths:
                    self.current_image_index = 0
                    self.display_image(self.current_image_index)
                    self.status_text.value = f"Loaded {len(self.image_paths)} images from {os.path.basename(directory)}."
                else:
                    self.current_image_index = -1
                    self.status_text.value = f"No image files found in: {directory}"
                    self.original_image_display.src = None
                    self.processed_image_content.src = None
                    self.processed_image_content.src_base64 = None
                    self.next_image_button.disabled = True
            else:
                logging.info("Directory selection was cancelled or no path was returned.")
                self.status_text.value = "Directory selection cancelled or no path chosen."
        
        except subprocess.TimeoutExpired:
            logging.error("Directory picker dialog timed out.")
            self.status_text.value = "Selection timeout."
        except FileNotFoundError as fnf_ex:
            logging.error(f"Command for directory picker not found (e.g., zenity, osascript): {fnf_ex}", exc_info=True)
            self.status_text.value = f"Error: Required tool not found ({fnf_ex.filename})."
        except Exception as ex:
            logging.error(f"An unexpected error occurred during directory selection: {ex}", exc_info=True)
            self.status_text.value = f"Error picking directory: {str(ex)}"
        
        self.page.update(self.status_text, self.original_image_display, self.processed_image_content, self.next_image_button)


    def on_next_image_click(self, e):
        """Handler for the 'Next Image' button."""
        logging.info(f"Next Image button clicked. Current index: {self.current_image_index}, Total images: {len(self.image_paths)}")
        if self.current_image_index < len(self.image_paths) - 1:
            self.display_image(self.current_image_index + 1)
        else:
            logging.info("Next Image clicked, but already at the last image in the list.")

    def on_zoom_in_click(self, e):
        """Handler for the 'Zoom In' button."""
        old_scale = self.current_zoom_level
        new_scale = min(self.max_zoom_level, round(self.current_zoom_level + self.zoom_increment, 2))
        if new_scale != self.current_zoom_level:
            self.current_zoom_level = new_scale
            self.processed_image_scale.scale = self.current_zoom_level
            logging.info(f"Zoom In: Scale changed from {old_scale:.2f} to {self.current_zoom_level:.2f}")
            self.update_processed_image_transform()
        else:
            logging.info(f"Zoom In: Already at maximum zoom level ({self.max_zoom_level:.2f}). No change.")

    def on_zoom_out_click(self, e):
        """Handler for the 'Zoom Out' button."""
        old_scale = self.current_zoom_level
        new_scale = max(self.min_zoom_level, round(self.current_zoom_level - self.zoom_increment, 2))
        if new_scale != self.current_zoom_level:
            self.current_zoom_level = new_scale
            self.processed_image_scale.scale = self.current_zoom_level
            logging.info(f"Zoom Out: Scale changed from {old_scale:.2f} to {self.current_zoom_level:.2f}")
            self.update_processed_image_transform()
        else:
            logging.info(f"Zoom Out: Already at minimum zoom level ({self.min_zoom_level:.2f}). No change.")
    
    def on_image_tap_down(self, e: ft.TapEvent):
        """Handler for tap events on the processed image for zoom/center."""
        fixed_zoom_on_click = 2.0
        if self.current_zoom_level == fixed_zoom_on_click: 
            fixed_zoom_on_click = 1.0

        container_width = self.processed_image_container.width
        container_height = self.processed_image_container.height
        tap_x_in_container = e.local_x
        tap_y_in_container = e.local_y

        logging.info(
            f"Processed image tapped at local container coordinates: ({tap_x_in_container:.2f}, {tap_y_in_container:.2f}). "
            f"Current zoom: {self.current_zoom_level:.2f}. Target zoom on click: {fixed_zoom_on_click}."
        )

        old_offset_x, old_offset_y = self.processed_image_offset.x, self.processed_image_offset.y
        self.processed_image_offset.x = (container_width / 2) - (tap_x_in_container * fixed_zoom_on_click)
        self.processed_image_offset.y = (container_height / 2) - (tap_y_in_container * fixed_zoom_on_click)
        
        old_scale = self.current_zoom_level
        self.processed_image_scale.scale = fixed_zoom_on_click
        self.current_zoom_level = fixed_zoom_on_click
        
        logging.info(
            f"Tap zoom/center: Scale changed from {old_scale:.2f} to {self.current_zoom_level:.2f}. "
            f"Offset changed from ({old_offset_x:.2f}, {old_offset_y:.2f}) to ({self.processed_image_offset.x:.2f}, {self.processed_image_offset.y:.2f})."
        )
        self.update_processed_image_transform()

def main(page: ft.Page):
    """
    Sets up and runs the Flet application.
    Creates an instance of ImageViewerApp and initializes its UI.
    """
    page.title = "Image Viewer and Processor"
    page.vertical_alignment = ft.MainAxisAlignment.START 
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    
    # No Flet FilePicker needed here anymore
    logging.info("ImageViewerApp will use custom directory picker.")
    
    app_instance = ImageViewerApp(page) # Pass the picker to the app
    app_instance.init_ui() # Initialize UI elements and layout



if __name__ == "__main__":
    logging.info("Application starting...")
    ft.app(target=main)
