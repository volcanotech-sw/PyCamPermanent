# -*- coding: utf-8 -*-

"""
pycam test module for utils
"""

from pycam.utils import read_file
from pycam.setupclasses import FileLocator, ConfigInfo

class TestUtils:
    def test_read_config(self):
        """Tests reading of config file using read_file"""
        config = read_file('../conf/config.txt')

        print(config[ConfigInfo.host_ip])