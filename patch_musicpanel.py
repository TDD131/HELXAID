import textwrap

TARGET = r"D:\Software\tididi\Game Launcher\python\MusicPanelWidget.py"

with open(TARGET, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if line.startswith("    def get_prev_index(self, current_index: int) -> int:"):
        skip = True
    elif line.startswith("    def _set_subtitle_style_preset("):
        skip = True
    elif line.startswith("    def _set_subtitle_style_variant("):
        skip = True
    elif line.startswith("    def _show_balance_dialog("):
        skip = True
    elif line.startswith("    def _apply_stereo_mode("):
        skip = True
    elif line.startswith("    def _show_audio_settings("):
        skip = True
    elif line.startswith("    def _show_load_url_dialog("):
        skip = True
        
    if skip and line.startswith("    def "):
        # Check if it's one of the ones we want to skip
        if any(line.startswith(x) for x in [
            "    def get_prev_index(self, current_index: int) -> int:",
            "    def _set_subtitle_style_preset(",
            "    def _set_subtitle_style_variant(",
            "    def _show_balance_dialog(",
            "    def _apply_stereo_mode(",
            "    def _show_audio_settings(",
            "    def _show_load_url_dialog(",
        ]):
            pass # keep skipping
        else:
            skip = False
            
    if not skip:
        new_lines.append(line)

# Now fix the duplicate execution block in _play_resolved_stream
# Lines 5675-5690
final_lines = []
skip_dup = False
import re
for i, line in enumerate(new_lines):
    if skip_dup:
        if "self._update_discord(title, artist, is_playing=True)" in line:
            skip_dup = False
        continue

    # Identify the duplicate artist assignment taking over
    if "        artist = track.get('artist', '')\n" == line and "        self._update_discord(title, artist, is_playing=True)\n" == new_lines[i-1]:
        skip_dup = True
        continue
        
    final_lines.append(line)

with open(TARGET, 'w', encoding='utf-8') as f:
    f.writelines(final_lines)

print("Dead code explicitly removed.")
