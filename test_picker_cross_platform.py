import flet as ft
import subprocess
import platform

def main(page: ft.Page):
    page.title = "Directory Picker"
    status_text = ft.Text("No directory selected", size=16)
    
    def pick_directory_clicked(e):
        try:
            system = platform.system()
            
            if system == "Darwin":  # macOS
                # Get POSIX path directly in one step
                script = 'POSIX path of (choose folder with prompt "Select Directory")'
                result = subprocess.run(
                    ['osascript', '-e', script],
                    capture_output=True, text=True, timeout=30
                )
                
                if result.returncode == 0:
                    directory = result.stdout.strip()
                    # Remove trailing slash if present
                    if directory.endswith('/'):
                        directory = directory[:-1]
                else:
                    directory = None
                    
            elif system == "Linux":
                result = subprocess.run(
                    ['zenity', '--file-selection', '--directory'],
                    capture_output=True, text=True
                )
                directory = result.stdout.strip() if result.returncode == 0 else None
                
            else:  # Windows
                import tempfile
                import os
                
                script = '''
                Add-Type -AssemblyName System.Windows.Forms
                $browser = New-Object System.Windows.Forms.FolderBrowserDialog
                $result = $browser.ShowDialog()
                if ($result -eq "OK") { $browser.SelectedPath }
                '''
                
                with tempfile.NamedTemporaryFile(mode='w', suffix='.ps1', delete=False) as f:
                    f.write(script)
                    script_path = f.name
                
                try:
                    result = subprocess.run(
                        ['powershell', '-ExecutionPolicy', 'Bypass', '-File', script_path],
                        capture_output=True, text=True
                    )
                    directory = result.stdout.strip() if result.returncode == 0 else None
                finally:
                    os.unlink(script_path)
            
            # Debug output
            print(f"Return code: {result.returncode}")
            print(f"Directory result: '{directory}'")
            print(f"Raw stdout: '{result.stdout}'")
            if hasattr(result, 'stderr'):
                print(f"Stderr: '{result.stderr}'")
            
            if directory and directory.strip():
                status_text.value = f"Selected: {directory}"
                print(f"Directory selected: {directory}")
            else:
                status_text.value = "Selection cancelled"
                print("Directory selection cancelled or empty result")
                
        except subprocess.TimeoutExpired:
            status_text.value = "Selection timeout"
            print("Dialog timeout")
        except Exception as ex:
            status_text.value = f"Error: {str(ex)}"
            print(f"Exception: {ex}")
            
        page.update()
    
    pick_button = ft.ElevatedButton(
        "Pick Directory", 
        icon=ft.Icons.FOLDER_OPEN,
        on_click=pick_directory_clicked
    )
    
    page.add(ft.Column([
        ft.Text(f"Platform: {platform.system()}", size=12, color="grey"),
        pick_button,
        ft.Divider(),
        status_text
    ]))

ft.app(target=main)
