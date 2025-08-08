import os
import sys
from PIL import Image

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import utils


def test_melhorar_logo_shape(tmp_path):
    img_path = tmp_path / "logo.png"
    Image.new("L", (8, 8), color=255).save(img_path)

    bitmap, largura_bytes, altura = utils.melhorar_logo(str(img_path), largura_desejada=8)

    assert largura_bytes == 1
    assert altura == 8
    assert len(bitmap) == largura_bytes * altura
