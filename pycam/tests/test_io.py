import pytest
import pycam.io_py as io_py

# Test exception thrown for png import bad path
def test_load_picam_png():
    bad_path = "this/doesnt/exist"
    with pytest.raises(FileNotFoundError):
        io_py.load_picam_png(bad_path)
