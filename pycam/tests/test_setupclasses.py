# -*- coding: utf-8 -*-

"""
pycam test module for setupclasses
"""

from pycam.setupclasses import CameraSpecs
import numpy as np

class TestSpecs:
    filename = './test_data/temp_io_test.txt'
    def test_cam_specs_io(self):
        """Test basic IO functionality of the CameraSpecs object"""
        # Instantiate CameraSpecs object
        cam_1 = CameraSpecs()

        # Edit value from default
        cam_1.shutter_speed = 1000

        # Edit another value
        cam_1.framerate = 0.5

        # Attempt to save camera specs
        cam_1.save_specs(self.filename)

        # Reload camera specs
        cam_2 = CameraSpecs(self.filename)

        # Check cam_1 against cam_2 to ensure load and save has been performed as anticipated
        # assert cam_1.__dict__ == cam_2.__dict__
        for key in cam_1.__dict__:
            if isinstance(cam_1.__dict__[key], np.ndarray):
                assert np.array_equal(cam_1.__dict__[key], cam_2.__dict__[key])
            else:
                assert cam_1.__dict__[key] == cam_2.__dict__[key]

    def test_changing_bool(self):
        """Test changing bool value and saving"""
        # Create first CameraSpecs obj
        cam_1 = CameraSpecs()

        # Change auto_ss to False
        cam_1.auto_ss = False

        # Save camera specs
        cam_1.save_specs(self.filename)

        # Load new CameraSpecs
        cam_2 = CameraSpecs(self.filename)

        assert cam_1.auto_ss == cam_2.auto_ss

    def test_incorrect_bool(self):
        """Tests performance if incorrect bool is saved to, and then read from, file"""
        cam_1 = CameraSpecs()

        # Define auto_ss incorrectly
        cam_1.auto_ss = 3

        # Save incorrect definition
        cam_1.save_specs(self.filename)

        # Load specifications (auto_ss should revert to default - True)
        cam_1.load_specs(self.filename)

        # Check auto_ss has reverted to default
        assert cam_1.auto_ss == True


