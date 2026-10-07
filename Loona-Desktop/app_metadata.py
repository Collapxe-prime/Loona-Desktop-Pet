"""Application version and writable state paths, independent from installation assets."""
import os
from pathlib import Path
import re

APP_TITLE='Loona Desktop Pet'
EXE_BASENAME='LoonaDesktopPet'
APP_ID='LoonaDesktopPet.Desktop'

def read_version(base):
    version=(Path(base)/'VERSION').read_text(encoding='utf-8-sig').strip()
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?',version):
        raise ValueError('VERSION must contain one semantic version, e.g. 0.1.0')
    return version

def user_data_directory(base, frozen=False):
    override=os.environ.get('LOONA_DATA_DIR')
    if override:return Path(override).expanduser().resolve()
    if not frozen:return Path(base)
    local=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData/Local')
    return local/'LoonaDesktopPet'
