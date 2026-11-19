__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
from pathlib import Path
from PIL import ImageFont
import os

def _tfont(size, weight=400):
    p = Path(os.environ.get('AUTO_EMOJI_ROOT', Path.cwd())) / 'assets/fonts/montserrat.ttf'
    font = ImageFont.truetype(str(p), size)
    try:
        font.set_variation_by_axes([weight])
    except OSError:
        pass
    return font
