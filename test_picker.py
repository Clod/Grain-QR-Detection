import flet as ft
import subprocess
import sys
import platform

def main(page: ft.Page):
    page.title = "Directory Picker"
    
    # Status text
    status_text = ft.Text("No directory selected", size=16)
    
    def pick_directory_clicked(e):
        print("Button clicked - using subprocess approach")
        try:
            if platform.system() == "Darwin":  # macOS
                # Use AppleScript for native macOS directory picker
                script = '''
                on run
                    set chosenFolder to choose folder with prompt "Select Directory"
                    return POSIX path of chosenFolder
                end run
                '''
                result = subprocess.run(
                    ['osascript', '-e', script],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    directory = result.stdout.strip()
                    status_text.value = f"Selected: {directory}"
                    print(f"Directory selected: {directory}")
                else:
                    status_text.value = "Selection cancelled"
                    print("Directory selection cancelled")
                    
            else:
                # Fallback for other platforms
                status_text.value = "Platform not supported yet"
                
            page.update()
            
        except subprocess.TimeoutExpired:
            status_text.value = "Selection timeout"
            page.update()
        except Exception as ex:
            print(f"Error: {ex}")
            status_text.value = f"Error: {str(ex)}"
            page.update()
    
    # Platform info
    platform_info = ft.Text(f"Platform: {platform.system()}", size=12, color="grey")
    
    # Button
    pick_button = ft.ElevatedButton(
        "Pick Directory",
        icon=ft.Icons.FOLDER_OPEN,
        on_click=pick_directory_clicked
    )
    
    page.add(
        ft.Column([
            platform_info,
            pick_button,
            ft.Divider(),
            status_text
        ])
    )

ft.app(target=main)
